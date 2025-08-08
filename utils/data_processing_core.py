import pandas as pd
import re
import logging
from utils.task_classifier import classify_task
from utils.time_utils import calculate_working_hours_with_holidays

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def parse_korean_datetime(dt_input):
    try:
        if isinstance(dt_input, (int, float)):
            return pd.to_datetime(dt_input, unit="D", origin="1899-12-30")
        elif isinstance(dt_input, str):
            s = dt_input.strip()
            if not s:
                return pd.NaT

            # "4월 4일" 형식 처리
            month_day_pattern = r"^(?P<month>\d{1,2})월\s*(?P<day>\d{1,2})일$"
            match = re.match(month_day_pattern, s)
            if match:
                month = int(match.group("month"))
                day = int(match.group("day"))
                year = 2025
                s = f"{year}-{month:02d}-{day:02d} 00:00:00"
                return pd.to_datetime(s, format="%Y-%m-%d %H:%M:%S", errors="coerce")

            s = s.replace("오전", "AM").replace("오후", "PM")
            formats = [
                (
                    "%Y. %m. %d %p %I:%M:%S",
                    r"^\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\s+(?:AM|PM)\s+\d{1,2}:\d{2}:\d{2}$",
                ),
                (
                    "%Y. %m. %d %H:%M:%S",
                    r"^\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\s+\d{1,2}:\d{2}:\d{2}$",
                ),
                ("%Y/%m/%d %H:%M:%S", r"^\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}:\d{2}$"),
                ("%Y-%m-%d %H:%M:%S", r"^\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}:\d{2}$"),
                ("%Y. %m. %d", r"^\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\s*$"),
                ("%Y/%m/%d", r"^\d{4}/\d{1,2}/\d{1,2}$"),
                ("%Y-%m-%d", r"^\d{4}-\d{1,2}-\d{1,2}$"),
            ]

            for fmt, pattern in formats:
                if re.match(pattern, s):
                    if " " not in s:
                        s += " 00:00:00"
                    return pd.to_datetime(s, format=fmt, errors="coerce")

            logging.warning(f"지원되지 않는 날짜 포맷: {s}")
            return pd.NaT
        return pd.NaT
    except Exception as e:
        logging.error(f"날짜 파싱 실패: 입력={dt_input}, 오류={e}")
        return pd.NaT


def format_hours(hours):
    """시간 포맷팅."""
    try:
        hours = float(hours)
        h = int(hours)
        m = int((hours - h) * 60)
        return f"{h}시간 {m}분" if m > 0 else f"{h}시간"
    except (ValueError, TypeError) as e:
        logging.error(f"시간 포맷팅 실패: 입력={hours}, 오류={e}")
        return "0시간"


def process_data(df, model_name, info):
    try:
        df = df.copy()
        logging.info(
            f"[디버깅] process_data 입력 데이터: {df.head(5).to_dict(orient='records')}"
        )
        logging.info(f"[디버깅] process_data 입력 데이터 행 수: {len(df)}")

        df["작업 분류"] = df["내용"].apply(
            lambda x: classify_task(x, model_name) or "기타"
        )

        # 완료된 작업만 필터링
        df_complete = df.dropna(subset=["시작 시간", "완료 시간"])
        logging.info(f"[디버깅] df_complete 행 수 (NaT 필터링 후): {len(df_complete)}")

        if df_complete.empty:
            logging.info("[디버깅] 워킹데이 소요 시간 계산 결과: []")
            logging.info("작업 데이터 처리 완료: 0개 작업 요약")
            return pd.DataFrame(
                columns=[
                    "내용",
                    "작업 분류",
                    "워킹데이 소요 시간",
                    "총 워킹 소요 시간 (시간:분)",
                ]
            )

        logging.info(
            f"[디버깅] 열 생성 전 df_complete columns: {df_complete.columns.tolist()}"
        )

        # df_complete가 슬라이스일 경우 복사본 생성
        df_complete = df_complete.copy()
        # 워킹데이 소요 시간 계산
        df_complete["워킹데이 소요 시간"] = df_complete.apply(
            lambda row: calculate_working_hours_with_holidays(
                row["시작 시간"], row["완료 시간"]
            ),
            axis=1,
        )
        logging.info(
            f"[디버깅] 열 생성 후 df_complete columns: {df_complete.columns.tolist()}"
        )
        # 동일 작업의 소요 시간 누적
        df_summary = (
            df_complete.groupby("내용")
            .agg({"작업 분류": "first", "워킹데이 소요 시간": "sum"})
            .reset_index()
        )

        # 소요 시간 포맷팅
        df_summary["총 워킹 소요 시간 (시간:분)"] = df_summary[
            "워킹데이 소요 시간"
        ].apply(
            lambda x: (
                f"{int(x // 1)}시간 {int((x % 1) * 60)}분"
                if pd.notna(x) and x >= 0.0167
                else f"{int(x * 60)}초" if pd.notna(x) else "0시간 0분"
            )
        )

        result = df_summary[
            ["내용", "작업 분류", "워킹데이 소요 시간", "총 워킹 소요 시간 (시간:분)"]
        ]
        logging.info(
            f"[디버깅] 워킹데이 소요 시간 계산 결과: {result.to_dict('records')}"
        )
        logging.info(f"작업 데이터 처리 완료: {len(result)}개 작업 요약")
        return result

    except Exception as e:
        logging.error(f"작업 데이터 처리 실패: {e}")
        return pd.DataFrame(
            columns=[
                "내용",
                "작업 분류",
                "워킹데이 소요 시간",
                "총 워킹 소요 시간 (시간:분)",
            ]
        )


def calculate_progress_by_category(df, model_name):
    df = df.copy()
    df["작업 분류"] = df["내용"].apply(lambda x: classify_task(x, model_name) or "기타")

    # 중복 작업 처리: 동일한 '내용'과 '작업 분류'에 대해 진행률 최대값 선택
    df["진행율"] = df.apply(
        lambda row: (
            100.0 if pd.notna(row["시작 시간"]) and pd.notna(row["완료 시간"]) else 0.0
        ),
        axis=1,
    )
    df_max = df.groupby(["내용", "작업 분류"])["진행율"].max().reset_index()

    categories = df_max["작업 분류"].unique()
    progress_summary = {}

    for category in categories:
        category_df = df_max[df_max["작업 분류"] == category]
        total_tasks = len(category_df)
        completed_tasks = len(category_df[category_df["진행율"] == 100.0])
        progress_summary[category] = round(
            (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0.0, 1
        )

    return progress_summary


def compute_occurrence_rates(
    df,
    task_summary_df,
    avg_mapping,
    model_name,
    tolerance=2,
    mech_partner=None,
    elec_partner=None,
):
    df = df.copy()
    df["작업 분류"] = df["내용"].apply(lambda x: classify_task(x, model_name) or "기타")

    # 완료된 작업 추출 (main_extract.py에서 진행율 계산 후 df에 반영됨)
    # 진행율이 100 이상이거나 시작 시간과 완료 시간이 모두 있는 경우 완료로 간주
    completed_tasks = set(
        df[(df["시작 시간"].notna() & df["완료 시간"].notna())]["내용"]
    )

    occurrence_stats = {}
    for category in df["작업 분류"].unique():
        occurrence_stats[category] = {
            "total_count": 0,
            "nan_count": 0,
            "completed_count": 0,
            "nan_tasks": [],
        }

    # NaN 카운트 계산 (Pda_rev 로직 적용)
    nan_task_checked = set()
    for _, row in df.iterrows():
        task_name = row["내용"]
        category = row["작업 분류"]
        occurrence_stats[category]["total_count"] += 1

        # NaN 조건: 시작 시간 또는 완료 시간이 없음
        is_nan = pd.isna(row["시작 시간"]) or pd.isna(row["완료 시간"])
        if is_nan:
            if task_name in completed_tasks:
                continue
            if (task_name, category) in nan_task_checked:
                continue
            occurrence_stats[category]["nan_count"] += 1
            occurrence_stats[category]["nan_tasks"].append(task_name)
            nan_task_checked.add((task_name, category))

    # completed_count 계산 및 partner_stats 생성
    partner_stats = {"mech": {"nan_count": 0}, "elec": {"nan_count": 0}}
    for category in occurrence_stats:
        occurrence_stats[category]["completed_count"] = (
            occurrence_stats[category]["total_count"]
            - occurrence_stats[category]["nan_count"]
        )
        if category == "기구":
            partner_stats["mech"]["nan_count"] = occurrence_stats[category]["nan_count"]
        elif category == "전장":
            partner_stats["elec"]["nan_count"] = occurrence_stats[category]["nan_count"]

    return occurrence_stats, partner_stats
