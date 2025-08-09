import os
import logging
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import seaborn as sns
import numpy as np
import json
from datetime import datetime, timedelta
from calendar import monthrange
from config.settings import FONT_PATHS, DRIVE_FOLDER_ID
from config.credentials import get_drive_service
from googleapiclient.http import MediaFileUpload
from utils.logger import setup_logging

# 로깅 및 폰트 설정
setup_logging()

# 한글 폰트 설정
plt.rcParams['font.family'] = 'NanumGothic'
plt.rcParams['axes.unicode_minus'] = False  # 마이너스 기호 깨짐 방지

def setup_fonts():
    """
    FONT_PATHS에 등록된 경로 중 실제로 존재하는 NanumGothic 폰트를 찾아
    matplotlib 전역 설정에 적용합니다.
    """
    font_path = next((p for p in FONT_PATHS if os.path.exists(p)), None)
    if font_path:
        logging.info(f"NanumGothic 폰트 적용: {font_path}")
        font_prop = fm.FontProperties(fname=font_path)
        plt.rc('font', family=font_prop.get_name())
    else:
        logging.warning("NanumGothic 폰트를 찾을 수 없습니다. 기본 폰트로 진행합니다.")
    plt.rcParams['axes.unicode_minus'] = False

# 모듈 임포트 시 한 번만 폰트 설정
setup_fonts()

# Google Drive 서비스 초기화
drive_service = get_drive_service()

# 캐싱 변수
_cached_json_data = None

def load_json_files_from_drive(latest_only=True, local_json_path=None, drive_folder_id=DRIVE_FOLDER_ID):
    """
    Google Drive 폴더 내 'result_'가 포함된 JSON 파일을 로드.
    Args:
        latest_only (bool): 최신 JSON 파일만 로드할지 여부 (기본값: True).
        local_json_path (str, optional): 로컬 JSON 파일 경로.
        drive_folder_id (str, optional): Google Drive 폴더 ID (기본값: DRIVE_FOLDER_ID).
    Returns:
        list: 로드된 데이터 리스트.
    """
    global _cached_json_data
    if _cached_json_data is not None:
        logging.info("캐싱된 JSON 데이터 사용")
        return _cached_json_data

    # 1. Google Drive에서 로드 시도
    try:
        logging.info(f"Google Drive 조회 - 폴더 ID: {drive_folder_id}")
        files = drive_service.files().list(
            q=f"'{drive_folder_id}' in parents and name contains 'result_'",
            fields="files(id, name, modifiedTime)",
            orderBy="modifiedTime desc"
        ).execute().get("files", [])
        if not files:
            logging.warning("Google Drive에서 로드할 JSON 파일이 없습니다.")
        else:
            if latest_only:
                files = [files[0]]
                logging.info(f"Google Drive에서 최신 JSON 파일 로드: {files[0]['name']}")
            else:
                logging.info(f"Google Drive에서 총 {len(files)}개의 JSON 파일 로드")
    except Exception as e:
        logging.error(f"Google Drive API 호출 실패: {str(e)}")
        files = []

    # Google Drive에서 로드 성공 시
    if files:
        data_list = []
        for file in files:
            file_id = file["id"]
            file_name = file["name"]
            logging.info(f"JSON 파일 로드 중: {file_name}")
            request = drive_service.files().get_media(fileId=file_id)
            content = request.execute().decode("utf-8")
            data = json.loads(content)
            for doc in data["documents"]:
                doc["timestamp"] = data["timestamp"]
                # worksheet의 시작 시간에서 가장 이른 날짜를 별도로 저장
                if doc.get("worksheet"):
                    start_times = [pd.to_datetime(w["시작 시간"]) for w in doc["worksheet"] if "시작 시간" in w and w["시작 시간"] is not None]
                    doc["worksheet_start_date"] = min(start_times).date().isoformat() if start_times else doc["execution_date"]
                else:
                    doc["worksheet_start_date"] = doc["execution_date"]
            data_list.extend(data["documents"])
        
        _cached_json_data = data_list
        logging.info(f"Google Drive에서 총 {len(data_list)}개의 로그 데이터를 로드했습니다.")
        return data_list

    # 2. Google Drive에서 실패 시 로컬 파일 로드 시도
    if local_json_path and os.path.exists(local_json_path):
        try:
            logging.info(f"Google Drive에서 JSON 로드 실패, 로컬 파일 로드 시도: {local_json_path}")
            with open(local_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data_list = data["documents"]
            for doc in data_list:
                doc["timestamp"] = data["timestamp"]
                if doc.get("worksheet"):
                    start_times = [pd.to_datetime(w["시작 시간"]) for w in doc["worksheet"] if "시작 시간" in w and w["시작 시간"] is not None]
                    doc["worksheet_start_date"] = min(start_times).date().isoformat() if start_times else doc["execution_date"]
                else:
                    doc["worksheet_start_date"] = doc["execution_date"]
            _cached_json_data = data_list
            logging.info(f"로컬에서 총 {len(data_list)}개의 로그 데이터를 로드했습니다.")
            return data_list
        except Exception as e:
            logging.error(f"로컬 JSON 파일 로드 실패: {str(e)}")
            return []
    
    # 3. 모두 실패 시
    logging.warning("JSON 데이터를 로드할 수 없습니다.")
    return []

def auto_week_info(local_json_path=None):
    """
    JSON 파일들에서 execution_date를 기준으로 
    가장 최신 날짜를 기준으로 해당 주의 week_number와 월요일~금요일 date_range를 계산합니다.
    Args:
        local_json_path (str, optional): 로컬 JSON 파일 경로.
    Returns:
        tuple: (week_number, (start_date, end_date)).
    """
    all_data = load_json_files_from_drive(local_json_path=local_json_path)
    if not all_data:
        logging.warning("JSON 데이터를 로드할 수 없습니다.")
        return None, None
    times = [pd.to_datetime(item["execution_date"]) for item in all_data]
    latest_date = max(times)
    week_number = latest_date.isocalendar().week
    start_date = latest_date - timedelta(days=latest_date.weekday())  # 월요일
    end_date = start_date + timedelta(days=4)  # 금요일
    logging.info(f"자동 계산 주간 정보: week_number={week_number}, date_range=({start_date}, {end_date})")
    return week_number, (start_date, end_date)

def is_last_friday_in_month(local_json_path=None):
    """
    월간 그래프 생성 조건:
    1. 해당 월의 마지막 주에 금요일 데이터가 존재하거나,
    2. 현재 실행 날짜가 해당 달의 마지막 날일 경우 True 반환.
    Args:
        local_json_path (str, optional): 로컬 JSON 파일 경로.
    Returns:
        bool: 조건 충족 시 True.
    """
    all_data = load_json_files_from_drive(local_json_path=local_json_path)
    if not all_data:
        return False
    df = pd.DataFrame([{
        "execution_date": d["execution_date"],
        "date": pd.to_datetime(d["execution_date"])
    } for d in all_data])
    df["month"] = df["date"].dt.month
    df["week"] = df["date"].dt.isocalendar().week
    df["weekday"] = df["date"].dt.weekday

    now = datetime.now()
    current_month = now.month
    current_year = now.year
    current_day = now.day
    _, last_day_of_current_month = monthrange(current_year, current_month)
    is_last_day_of_month = (current_day == last_day_of_current_month)
    logging.info(f"현재 날짜: {now.date()}, 현재 달의 마지막 날: {last_day_of_current_month}, 마지막 날 여부: {is_last_day_of_month}")

    result = {}
    for month, group in df.groupby("month"):
        max_week = group["week"].max()
        last_week_data = group[group["week"] == max_week]
        has_friday_in_last_week = (4 in last_week_data["weekday"].values)
        logging.info(f"월: {month}, 마지막 주: {max_week}, 금요일 데이터 존재: {has_friday_in_last_week}")

        if month == current_month:
            result[month] = has_friday_in_last_week or is_last_day_of_month
        else:
            result[month] = has_friday_in_last_week

    return result.get(current_month, False)

def ratio_calc(stats, key="nan_count", total_key="total_count"):
    """
    비율 계산 함수.
    Args:
        stats (dict): 통계 데이터.
        key (str): 계산할 항목 (nan_count 또는 ot_count).
        total_key (str): 전체 항목 (total_count).
    Returns:
        float: 비율 (%).
    """
    total = stats.get(total_key, 0)
    count = stats.get(key, 0)
    return (count / total * 100) if total > 0 else 0

def generate_nan_trend_graph(
    period="weekly",
    chart_type="heatmap",
    quarterly_targets=None,
    week_number=None,
    date_range=None,
    days_per_week="auto",
    group_by="partner",
    visualize_ot=True
):
    """
    주간 또는 월간 NaN 비율 추이를 시각화합니다.
    - 주간: 자동으로 해당 주의 데이터를 사용하며, days_per_week 자동 감지 가능.
    - 월간: 금요일 데이터만 사용 (마지막 주 금요일 데이터가 존재할 때만 생성).
    - visualize_ot: OT 비율을 시각화할지 여부를 결정 (True면 OT 표시, False면 표시 안 함).
    Returns:
        str: 생성된 파일 이름 (또는 None).
    """
    if quarterly_targets is None:
        quarterly_targets = {1: 40, 2: 30, 3: 20, 4: 0}
    all_data = load_json_files_from_drive()
    if not all_data:
        logging.warning("데이터를 로드할 수 없습니다.")
        return None
    df_data = []
    for d in all_data:
        info = d["info"][0]
        partner_stats = d.get("partner_stats", {})
        stats = d.get("stats", {})
        execution_date = d["execution_date"]
        mech_partner = partner_stats.get("mech", {}).get("name", "").strip().upper()
        elec_partner = partner_stats.get("elec", {}).get("name", "").strip().upper()
        entry = {
            "date": execution_date,  # execution_date 사용
            "model_name": info.get("Model Name", ""),
            "mech_partner": mech_partner,
            "elec_partner": elec_partner,
            "bat_nan_ratio": 0.0,
            "fni_nan_ratio": 0.0,
            "tms_m_nan_ratio": 0.0,
            "cna_nan_ratio": 0.0,
            "pns_nan_ratio": 0.0,
            "tms_e_nan_ratio": 0.0,
            "tms_semi_nan_ratio": 0.0,
            "bat_ot_ratio": 0.0,
            "fni_ot_ratio": 0.0,
            "tms_m_ot_ratio": 0.0,
            "cna_ot_ratio": 0.0,
            "pns_ot_ratio": 0.0,
            "tms_e_ot_ratio": 0.0,
            "tms_semi_ot_ratio": 0.0
        }
        if mech_partner == "BAT":
            target = stats.get("기구", {})
            entry["bat_nan_ratio"] = ratio_calc(target, key="nan_count")
            entry["bat_ot_ratio"] = ratio_calc(target, key="ot_count")
        elif mech_partner == "FNI":
            target = stats.get("기구", {})
            entry["fni_nan_ratio"] = ratio_calc(target, key="nan_count")
            entry["fni_ot_ratio"] = ratio_calc(target, key="ot_count")
        elif mech_partner == "TMS":
            target = stats.get("기구", {})
            entry["tms_m_nan_ratio"] = ratio_calc(target, key="nan_count")
            entry["tms_m_ot_ratio"] = ratio_calc(target, key="ot_count")
        if elec_partner == "C&A":
            target = stats.get("전장", {})
            entry["cna_nan_ratio"] = ratio_calc(target, key="nan_count")
            entry["cna_ot_ratio"] = ratio_calc(target, key="ot_count")
        elif elec_partner == "P&S":
            target = stats.get("전장", {})
            entry["pns_nan_ratio"] = ratio_calc(target, key="nan_count")
            entry["pns_ot_ratio"] = ratio_calc(target, key="ot_count")
        elif elec_partner == "TMS":
            target = stats.get("전장", {})
            entry["tms_e_nan_ratio"] = ratio_calc(target, key="nan_count")
            entry["tms_e_ot_ratio"] = ratio_calc(target, key="ot_count")
        tms_semi_stats = stats.get("TMS_반제품", {})
        entry["tms_semi_nan_ratio"] = ratio_calc(tms_semi_stats, key="nan_count")
        entry["tms_semi_ot_ratio"] = ratio_calc(tms_semi_stats, key="ot_count")
        df_data.append(entry)
    
    df = pd.DataFrame(df_data)
    df["date"] = pd.to_datetime(df["date"])
    
    # 인덱스를 date로 설정
    df.set_index("date", inplace=True)
    logging.info(f"[디버깅] df.index type after set_index: {type(df.index)}")
    logging.info(f"[디버깅] df.index sample: {df.index[:5]}")
    
    df["quarter"] = df.index.quarter
    df["week"] = df.index.isocalendar().week

    now = datetime.now()
    current_month = now.month
    current_year = now.year
    current_day = now.day
    _, last_day_of_current_month = monthrange(current_year, current_month)
    is_last_day_of_month = (current_day == last_day_of_current_month)

    if week_number is not None:
        df = df[df["week"] == week_number]
        if df.empty:
            logging.warning(f"{week_number}주차 데이터가 없습니다.")
            return None
    if date_range is not None:
        start_date, end_date = date_range
        start_date = pd.to_datetime(start_date)
        end_date = pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        if df.empty:
            logging.warning(f"{start_date} ~ {end_date} 사이의 데이터가 없습니다.")
            return None
        else:
            logging.info("포함된 날짜: %s", pd.Series(df.index.date).unique())
    else:
        # date_range가 없으면 현재 실행 날짜를 기준으로 필터링
        today = pd.to_datetime(now.date())
        df = df[df.index.date == today.date()]
        if df.empty:
            logging.warning(f"현재 날짜 {today.date()}에 해당하는 데이터가 없습니다.")
            return None
        logging.info("포함된 날짜: %s", pd.Series(df.index.date).unique())

    if period == "weekly":
        if days_per_week == "auto":
            unique_weekdays = set(df.index.weekday.unique())
            if set(range(5)).issubset(unique_weekdays):
                days_per_week = "5days"
            elif {0, 2, 4}.issubset(unique_weekdays) and len(unique_weekdays) == 3:
                days_per_week = "3days"
            else:
                days_per_week = "mixed"
            logging.info(f"자동 감지된 days_per_week: {days_per_week}")
        if days_per_week == "3days":
            df = df[df.index.weekday.isin([0, 2, 4])]
        elif days_per_week == "5days":
            df = df[df.index.weekday.isin([0, 1, 2, 3, 4])]
        else:
            logging.info("mixed days_per_week: 필터 미적용")
    elif period == "monthly":
        df_fridays = df[df.index.weekday == 4]
        if is_last_day_of_month:
            df = df[df.index.month == current_month]
            if df_fridays.empty:
                logging.info("해당 월의 금요일 데이터가 없음. 모든 데이터를 사용합니다.")
            else:
                df = df_fridays
                logging.info("해당 월의 금요일 데이터를 사용합니다.")
        else:
            df = df_fridays
            if df.empty:
                logging.warning("월간 데이터: 금요일 데이터가 없습니다.")
                return None
    if df.empty:
        logging.warning("필터링 후 데이터가 없습니다.")
        return None
    partner_categories = [
        ("bat_nan_ratio", "BAT", "blue"),
        ("fni_nan_ratio", "FNI", "cyan"),
        ("tms_m_nan_ratio", "TMS(m)", "orange"),
        ("cna_nan_ratio", "C&A", "green"),
        ("pns_nan_ratio", "P&S", "red"),
        ("tms_e_nan_ratio", "TMS(e)", "purple"),
        ("tms_semi_nan_ratio", "TMS_반제품", "magenta")
    ]
    if visualize_ot:
        logging.info("OT 비율 시각화 활성화")
        partner_categories.extend([
            ("bat_ot_ratio", "BAT (OT)", "lightblue"),
            ("fni_ot_ratio", "FNI (OT)", "lightcyan"),
            ("tms_m_ot_ratio", "TMS(m) (OT)", "lightorange"),
            ("cna_ot_ratio", "C&A (OT)", "lightgreen"),
            ("pns_ot_ratio", "P&S (OT)", "lightred"),
            ("tms_e_ot_ratio", "TMS(e) (OT)", "lightpurple"),
            ("tms_semi_ot_ratio", "TMS_반제품 (OT)", "lightmagenta")
        ])
    else:
        logging.info("OT 비율 시각화 비활성화 (데이터는 계산됨)")
    if period == "weekly":
        df = df.sort_index()
        df["day"] = df.index.date
        if group_by == "partner":
            df_grouped = df.groupby("day").mean(numeric_only=True)
        elif group_by == "model":
            df_grouped = df.groupby(["day", "model_name"]).mean(numeric_only=True).reset_index()
            categories = [
                (row["model_name"], row["model_name"], "blue")
                for _, row in df_grouped[["model_name"]].drop_duplicates().iterrows()
            ]
            df_grouped = df_grouped.pivot(index="day", columns="model_name", values=[col[0] for col in partner_categories])
            df_grouped.columns = [col[1] for col in df_grouped.columns]
        else:
            raise ValueError("group_by는 'partner' 또는 'model'이어야 합니다.")
        labels = [f"{d.month}월{d.day}일" for d in df_grouped.index]
        title = f"주간 NaN 비율 추이 ({days_per_week})"
        xlabel = "측정 날짜"
    elif period == "monthly":
        if group_by == "partner":
            df_grouped = df.groupby(df.index.to_period("M")).mean(numeric_only=True)
            categories = partner_categories
            labels = [p.strftime("%Y-%m") for p in df_grouped.index]
        elif group_by == "model":
            df_grouped = df.groupby([df.index.to_period("M"), "model_name"]).mean(numeric_only=True).reset_index()
            categories = [
                (row["model_name"], row["model_name"], "blue")
                for _, row in df_grouped[["model_name"]].drop_duplicates().iterrows()
            ]
            df_grouped = df_grouped.pivot(index="date", columns="model_name", values=[col[0] for col in partner_categories])
            df_grouped.columns = [col[1] for col in df_grouped.columns]
            labels = [p.strftime("%Y-%m") for p in df_grouped.index]
        else:
            raise ValueError("group_by는 'partner' 또는 'model'이어야 합니다.")
        title = "월간 NaN 비율 추이 (금요일 기준)"
        xlabel = "월"
    else:
        raise ValueError("period는 'weekly' 또는 'monthly'이어야 합니다.")

    if chart_type == "heatmap":
        if group_by == "partner":
            heatmap_data = df_grouped[[cat[0] for cat in partner_categories]].T
            heatmap_data.index = [cat[1] for cat in partner_categories]
            y_label = "협력사"
        else:
            heatmap_data = df_grouped.groupby(axis=1, level=0).mean().T
            y_label = "모델"
        sns.heatmap(heatmap_data, annot=True, fmt=".1f", cmap="YlOrRd", cbar_kws={'label': '비율 (%)'})
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(y_label)
        plt.xticks(ticks=np.arange(len(labels)) + 0.5, labels=labels, rotation=45, ha="right")
        filename = f"{period}_{group_by}_trend_{chart_type}_{datetime.now().strftime('%Y%m%d')}.png"
        plt.savefig(filename, bbox_inches='tight')
        plt.close()
        logging.info(f"히트맵 생성 완료: {filename}")
        return filename
    elif chart_type == "stacked_bar":
        bottom = np.zeros(len(df_grouped))
        for category, label, color in partner_categories:
            if category in df_grouped.columns:
                plt.bar(df_grouped.index, df_grouped[category], bottom=bottom, label=label, color=color)
                for i, (x, y) in enumerate(zip(df_grouped.index, df_grouped[category])):
                    if y >= 30:
                        plt.text(x, bottom[i] + y/2, f"{y:.1f}%", ha="center", va="center", color="black")
                bottom += df_grouped[category].fillna(0)
        for quarter, target in quarterly_targets.items():
            valid_quarter = df_grouped["quarter"].dropna().unique()
            if quarter in valid_quarter:
                plt.axhline(y=target, color="black", linestyle="--", label=f"{quarter}분기 목표 ({target}%)", alpha=0.5)
    else:
        for category, label, color in partner_categories:
            if category in df_grouped.columns:
                plt.plot(df_grouped.index, df_grouped[category], label=label, marker="o", color=color)
                for x, y in zip(df_grouped.index, df_grouped[category]):
                    if y >= 30:
                        plt.text(x, y, f"{y:.1f}%", ha="center", va="bottom", color=color)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("비율 (%)")
    plt.legend()
    plt.grid(True)
    plt.ylim(0, 100)
    plt.xticks(ticks=np.arange(len(labels)) + 0.5, labels=labels, rotation=45, ha="right")
    filename = f"{period}_{group_by}_trend_{chart_type}_{datetime.now().strftime('%Y%m%d')}.png"
    plt.savefig(filename, bbox_inches='tight')
    plt.close()
    logging.info(f"추이 그래프 생성 완료: {filename}")
    return filename

def generate_nan_bar_charts(all_results):
    """
    NaN 발생 비율 그래프 생성 (일일 모니터링용).
    - 협력사별 작업 수 대비 NaN 비율을 막대그래프로,
    - 전체 NaN 건수 대비 비율을 파이차트로 저장합니다.
    Returns:
        tasks_file (str) 또는 None
        total_file (str) 또는 None
    """
    # 1) 집계용 dict 준비
    aggregated_stats = {}

    for _, _, mech_partner, elec_partner, occurrence_stats, partner_stats_individual, *_ in all_results:
        # 기구 협력사
        mech_nan = partner_stats_individual.get("mech", {}).get("nan_count", 0)
        mech_total = occurrence_stats.get("기구", {}).get("total_count", 0)
        aggregated_stats.setdefault(mech_partner, {"nan_count": 0, "total_tasks": 0})
        aggregated_stats[mech_partner]["nan_count"] += mech_nan
        aggregated_stats[mech_partner]["total_tasks"] += mech_total

        # TMS 반제품
        tms_nan = occurrence_stats.get("TMS_반제품", {}).get("nan_count", 0)
        tms_total = occurrence_stats.get("TMS_반제품", {}).get("total_count", 0)
        if tms_total > 0:
            aggregated_stats.setdefault("TMS_반제품", {"nan_count": 0, "total_tasks": 0})
            aggregated_stats["TMS_반제품"]["nan_count"] += tms_nan
            aggregated_stats["TMS_반제품"]["total_tasks"] += tms_total

        # 전장 협력사
        elec_nan = partner_stats_individual.get("elec", {}).get("nan_count", 0)
        elec_total = occurrence_stats.get("전장", {}).get("total_count", 0)
        aggregated_stats.setdefault(elec_partner, {"nan_count": 0, "total_tasks": 0})
        aggregated_stats[elec_partner]["nan_count"] += elec_nan
        aggregated_stats[elec_partner]["total_tasks"] += elec_total

    # 2) 그래프 생성 전 체크
    labels = list(aggregated_stats.keys())
    nan_counts = [aggregated_stats[p]["nan_count"] for p in labels]
    total_tasks = [aggregated_stats[p]["total_tasks"] for p in labels]
    total_nan = sum(nan_counts)

    if total_nan == 0:
        logging.info("NaN 건수 없음, 그래프 생성 생략")
        return None, None

    # 3) 작업 수 대비 NaN 비율 막대그래프
    nan_ratios = [
        (nan_counts[i] / total_tasks[i] * 100) if total_tasks[i] > 0 else 0
        for i in range(len(labels))
    ]
    colors = plt.cm.Paired.colors[:len(labels)]
    plt.figure(figsize=(10, 6))
    bars = plt.bar(labels, nan_ratios, color=colors)
    plt.title("협력사별 NaN 발생 비율 (작업 수 대비)", fontsize=14, pad=10)
    plt.xlabel("협력사", fontsize=12)
    plt.ylabel("NaN 발생 비율 (%)", fontsize=12)
    plt.xticks(rotation=45, ha="right")
    for i, bar in enumerate(bars):
        height = bar.get_height()
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            height,
            f"{height:.1f}%\n({nan_counts[i]}/{total_tasks[i]})",
            ha="center",
            va="bottom",
            fontsize=10
        )
    plt.tight_layout()
    tasks_file = "NaN_Summary_by_Tasks.png"
    plt.savefig(tasks_file, bbox_inches='tight')
    plt.close('all')

    # 4) 전체 NaN 건수 대비 비율 파이차트
    plt.figure(figsize=(8, 8))
    plt.pie(
        nan_counts,
        labels=labels,
        autopct=lambda pct: f"{pct:.1f}% ({int(total_nan * pct / 100)})",
        startangle=90,
        colors=colors
    )
    plt.axis('equal')
    plt.title("협력사별 NaN 발생 비율 (전체 NaN 건수 대비)", fontsize=14, pad=10)
    total_file = "NaN_Summary_by_Total.png"
    plt.savefig(total_file, bbox_inches='tight')
    plt.close('all')

    logging.info(f"NaN 그래프 생성 완료: {tasks_file}, {total_file}")
    return tasks_file, total_file

def upload_to_drive(filename):
    """
    생성된 그래프 파일을 Google Drive에 업로드합니다.
    Args:
        filename (str): 업로드할 파일 이름.
    Returns:
        str: 업로드된 파일의 URL.
    """
    file_metadata = {"name": filename, "parents": [DRIVE_FOLDER_ID]}
    media = MediaFileUpload(filename, mimetype="image/png")
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    file_id = file.get('id')
    drive_service.permissions().create(fileId=file_id, body={'type': 'anyone', 'role': 'reader'}).execute()
    image_url = f"https://drive.google.com/uc?export=view&id={file_id}"
    logging.info(f"그래프 파일 구글 드라이브 업로드 완료: {filename}, 파일 ID: {file_id}")
    os.remove(filename)
    logging.info(f"로컬 파일 삭제 완료: {filename}")
    return image_url