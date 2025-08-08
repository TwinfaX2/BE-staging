# utils/data_processing.py
import logging
import pandas as pd
import numpy as np
import re
from datetime import datetime
import pytz
from config.settings import AVG_TIME_SPREADSHEET_ID
from utils.google_api import api_call_with_backoff, sheets_service
from utils.task_classifier import classify_task
from utils.time_utils import calculate_working_hours_with_holidays
from utils.logger import setup_logging

setup_logging()


def parse_korean_datetime(dt_input):
    if isinstance(dt_input, (int, float)):
        try:
            return pd.to_datetime(dt_input, unit="D", origin="1899-12-30")
        except Exception as e:
            logging.error(f"날짜 파싱 실패 (숫자 입력): {dt_input}, {e}")
            return pd.NaT
    elif isinstance(dt_input, str):
        s = dt_input.strip()
        if not s:
            return pd.NaT
        if re.match(r"^\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\s*$", s):
            s += " 00:00:00"
        s = s.replace("오전", "AM").replace("오후", "PM")
        fmt = (
            "%Y. %m. %d %p %I:%M:%S"
            if ("AM" in s or "PM" in s)
            else "%Y. %m. %d %H:%M:%S"
        )
        return pd.to_datetime(s, format=fmt, errors="coerce")
    return pd.NaT


def fetch_data_from_sheets(spreadsheet_id, sheet_range):
    """Google Sheets에서 데이터 가져오기."""
    try:
        result = api_call_with_backoff(
            sheets_service.spreadsheets().values().get,
            spreadsheetId=spreadsheet_id,
            range=sheet_range,
        ).execute()
        values = result.get("values", [])
        if not values or len(values) <= 7:
            raise ValueError(f"'{sheet_range}'에 충분한 데이터가 없습니다.")
        header = values[6]
        data = values[7:]
        max_cols = max(len(header), max((len(row) for row in data), default=0))
        if max_cols > len(header):
            header.extend([""] * (max_cols - len(header)))
        adjusted_data = [
            (
                row + [""] * (max_cols - len(row))
                if len(row) < max_cols
                else row[:max_cols]
            )
            for row in data
        ]
        df_raw = pd.DataFrame(adjusted_data, columns=header[:max_cols])
        needed_cols = ["내용", "시작 시간", "완료 시간", "진행율"]
        if not all(col in df_raw.columns for col in needed_cols):
            raise ValueError(
                f"필요한 컬럼 {needed_cols}이(가) '{sheet_range}'에 없습니다."
            )
        df_use = df_raw[needed_cols].copy()
        df_use["시작 시간"] = df_use["시작 시간"].apply(parse_korean_datetime)
        df_use["완료 시간"] = df_use["완료 시간"].apply(parse_korean_datetime)
        df_use["진행율"] = (
            df_use["진행율"]
            .astype(str)
            .str.replace("%", "")
            .str.strip()
            .replace("", np.nan)
            .astype(float)
        )
        return df_use[df_use["내용"].notna()]
    except Exception as e:
        logging.error(f"데이터 가져오기 실패: {spreadsheet_id} -> {e}")
        return pd.DataFrame()


def fetch_info_board_extended(spreadsheet_id):
    """정보판 데이터 가져오기."""
    ranges = [
        ("정보판!D4", "model_name"),
        ("정보판!B5", "mech_partner"),
        ("정보판!D5", "elec_partner"),
    ]
    batch_request = (
        sheets_service.spreadsheets()
        .values()
        .batchGet(
            spreadsheetId=spreadsheet_id,
            ranges=[rng for rng, _ in ranges],
            valueRenderOption="FORMATTED_VALUE",
        )
    )
    result = api_call_with_backoff(batch_request.execute)
    results = {}
    for (rng, key), response in zip(ranges, result.get("valueRanges", [])):
        values = response.get("values", [[]])
        results[key] = (
            values[0][0].strip() if values and values[0] and values[0][0] else "미정"
        )
    logging.info(
        f"모델명: {results['model_name']}, 기구협력사: {results['mech_partner']}, 전장협력사: {results['elec_partner']}"
    )
    return (
        results["model_name"] or "NoValue",
        results["mech_partner"],
        results["elec_partner"],
    )


def process_data(df, model_name):
    """
    작업 데이터 처리: 유효한 작업들에 대해 워킹데이 소요시간 계산 및 분류 후 요약 테이블 반환
    (그래프용: 내용별 groupby + 시간합계 + 분 단위 포맷)
    """
    if df.empty or "내용" not in df.columns:
        logging.warning("No valid data or missing '내용' column")
        return pd.DataFrame(
            columns=[
                "내용",
                "워킹데이 소요 시간",
                "총 워킹 소요 시간 (시간:분)",
                "작업 분류",
            ]
        )

    df_complete = df.dropna(subset=["시작 시간", "완료 시간"]).copy()

    # 1) 작업시간 계산 (휴일/점심/주말 고려)
    df_complete["워킹데이 소요 시간"] = df_complete.apply(
        lambda row: calculate_working_hours_with_holidays(
            row["시작 시간"], row["완료 시간"]
        ),
        axis=1,
    )

    # 2) 작업 분류
    df_complete["작업 분류"] = df_complete["내용"].apply(
        lambda x: classify_task(x, model_name)
    )

    # 3) 내용별 총 소요시간 요약 테이블
    task_total_time = (
        df_complete.groupby(["내용", "작업 분류"])["워킹데이 소요 시간"]
        .sum()
        .reset_index()
    )
    task_total_time["총 워킹 소요 시간 (시간:분)"] = task_total_time[
        "워킹데이 소요 시간"
    ].apply(format_hours)

    return task_total_time.sort_values("워킹데이 소요 시간", ascending=True)


def compute_occurrence_rates(
    df,
    task_total_time,
    avg_mapping,
    model_name,
    tolerance=2,
    mech_partner=None,
    elec_partner=None,
):
    """NaN 및 OT 발생률 계산."""
    categories = ["기구", "TMS_반제품", "전장", "검사", "마무리", "기타"]
    occurrence_stats = {
        cat: {
            "total_count": 0,
            "nan_count": 0,
            "ot_count": 0,
            "nan_tasks": [],
            "ot_task_details": [],
        }
        for cat in categories
    }
    partner_stats = {
        "mech": {"nan_count": 0, "ot_count": 0},
        "elec": {"nan_count": 0, "ot_count": 0},
    }
    df["진행율"] = pd.to_numeric(df["진행율"], errors="coerce")
    completed_tasks = set(
        df[
            (pd.to_numeric(df["진행율"], errors="coerce") >= 100)
            | (df["시작 시간"].notna() & df["완료 시간"].notna())
        ]["내용"]
    )
    nan_task_checked = set()
    for _, row in df.iterrows():
        task_name = row["내용"]
        category = classify_task(task_name, model_name)
        occurrence_stats[category]["total_count"] += 1
        is_nan = (
            pd.isna(row["시작 시간"])
            or pd.isna(row["완료 시간"])
            or pd.isna(row["진행율"])
        )
        if is_nan:
            if task_name in completed_tasks:
                continue
            if (task_name, category) in nan_task_checked:
                continue
            occurrence_stats[category]["nan_count"] += 1
            occurrence_stats[category]["nan_tasks"].append(task_name)
            nan_task_checked.add((task_name, category))
            if category == "기구":
                partner_stats["mech"]["nan_count"] += 1
            elif category == "전장":
                partner_stats["elec"]["nan_count"] += 1
    for _, row in task_total_time.iterrows():
        task_name = row["내용"]
        actual_hours = row["워킹데이 소요 시간"]
        category = classify_task(task_name, model_name)
        if (
            task_name in avg_mapping
            and actual_hours > avg_mapping[task_name] + tolerance
        ):
            occurrence_stats[category]["ot_count"] += 1
            occurrence_stats[category]["ot_task_details"].append(
                (task_name, actual_hours)
            )
            if category == "기구":
                partner_stats["mech"]["ot_count"] += 1
            elif category == "전장":
                partner_stats["elec"]["ot_count"] += 1
    return occurrence_stats, partner_stats


def calculate_progress_by_category(df, model_name):
    df = df.copy()
    df["작업 분류"] = df["내용"].apply(lambda x: classify_task(x, model_name))
    df["진행율"] = df.apply(
        lambda row: (
            100.0
            if pd.isna(row["진행율"])
            and pd.notna(row["시작 시간"])
            and pd.notna(row["완료 시간"])
            else row["진행율"]
        ),
        axis=1,
    )
    df_valid = df.dropna(subset=["내용"])
    df_max = df_valid.groupby(["내용", "작업 분류"])["진행율"].max().reset_index()
    progress_summary = {}
    for category in ["기구", "전장", "TMS_반제품"]:
        df_cat = df_max[df_max["작업 분류"] == category]
        total_tasks = len(df_cat)
        completed = df_cat[df_cat["진행율"] == 100.0]
        progress = (len(completed) / total_tasks * 100) if total_tasks > 0 else 0
        progress_summary[category] = round(progress, 1)
    return progress_summary


def format_hours(hours):
    """시간 포맷팅."""
    hours = float(hours)
    h = int(hours)
    m = int((hours - h) * 60)
    return f"{h}시간 {m}분" if m > 0 else f"{h}시간"


def parse_avg_time_string(s):
    s = s.lower().strip()
    match = re.match(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?", s)
    hours = int(match.group(1)) if match and match.group(1) else 0
    minutes = int(match.group(2)) if match and match.group(2) else 0
    return hours + minutes / 60.0


def get_avg_time_mapping(model_name):
    """
    주어진 모델 이름의 평균 작업 시간을 Google Sheets에서 가져와
    {작업명: 평균시간} 딕셔너리로 반환합니다.
    """
    sheet_range = f"'{model_name.strip()}'!A:B"
    try:
        avg_values = (
            sheets_service.spreadsheets()
            .values()
            .get(
                spreadsheetId=AVG_TIME_SPREADSHEET_ID,
                range=sheet_range,
                valueRenderOption="FORMATTED_VALUE",
            )
            .execute()
            .get("values", [])
        )
        if len(avg_values) <= 1:
            return {}
        return {
            row[0].strip(): (
                parse_avg_time_string(row[1])
                if "h" in row[1].lower() or "m" in row[1].lower()
                else float(row[1])
            )
            for row in avg_values[1:]
            if len(row) >= 2
        }

    except Exception as e:
        logging.error(f"[오류] AVDATA에서 '{model_name}' 시트를 읽는 중 오류 발생: {e}")
        return {}


def get_mech_start_date(spreadsheet_url):
    """기구 시작일 가져오기."""
    try:
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", spreadsheet_url)
        if not match:
            return pd.NaT
        spreadsheet_id = match.group(1)
        result = api_call_with_backoff(
            sheets_service.spreadsheets().values().get,
            spreadsheetId=spreadsheet_id,
            range="정보판!B6",
            valueRenderOption="FORMATTED_VALUE",
        ).execute()
        raw_date = result.get("values", [[]])[0][0]
        return pd.to_datetime(raw_date, errors="coerce")
    except Exception as e:
        logging.error(f"[오류] 기구 시작일 가져오기 실패: {e}")
        return pd.NaT


def sort_all_results_by_mech_start(all_results):
    """기구 시작일 기준 정렬."""

    def extract_start_date(entry):
        spreadsheet_url = entry[7]
        return get_mech_start_date(spreadsheet_url)

    return sorted(all_results, key=extract_start_date)
