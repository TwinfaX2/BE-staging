import argparse
import logging
import os
import time
import pandas as pd
from datetime import datetime, timedelta
from config.settings import SPREADSHEET_ID, DRIVE_FOLDER_ID_JSON_DB, TOLERANCE
from config.credentials import get_sheets_service, get_drive_service
from utils.drive_data_extractor import DriveDataExtractor
from utils.data_processing_core import (
    parse_korean_datetime,
    process_data,
    calculate_progress_by_category,
    compute_occurrence_rates,
)
from utils.data_processing import get_avg_time_mapping
from utils.json_saver import save_to_json
from utils.visualization import (
    generate_nan_bar_charts,
    generate_nan_trend_graph,
    auto_week_info,
    is_last_friday_in_month,
    upload_to_drive,
    load_json_files_from_drive,
)
from googleapiclient.http import MediaFileUpload
from datetime import datetime

# 로깅 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
stream_handler.setFormatter(formatter)

logger.handlers = []  # 이전 핸들러 제거
logger.addHandler(stream_handler)

logger.info("main_extract.py: Logging configured successfully.")
logger.debug("This is a debug message to test logging.")

# 환경 변수 확인
LIMIT = int(os.getenv("LIMIT", 0))  # 기본값 0
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 10))  # 기본값 10

if not SPREADSHEET_ID:
    logger.critical("SPREADSHEET_ID environment variable not set.")
    raise ValueError("SPREADSHEET_ID environment variable not set.")

# Google Sheets 및 Drive API 서비스 초기화
try:
    sheets_service = get_sheets_service()
    drive_service = get_drive_service()
    logger.info("Successfully initialized Google Sheets and Drive API services.")
except Exception as e:
    logger.error(f"Failed to initialize Google API services: {str(e)}", exc_info=True)
    raise


def sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, pd.Timestamp) and pd.isna(obj):
        return None
    elif pd.isna(obj):
        return None
    elif isinstance(obj, pd.Timestamp):
        return str(obj)
    return obj


def convert_to_treemap_format(progress_summary, task_summary_records):
    progress_treemap = {
        "name": "Progress",
        "children": [
            {"name": category, "value": progress}
            for category, progress in progress_summary.items()
        ],
    }

    task_treemap = {"name": "Tasks", "children": []}
    category_dict = {}
    for record in task_summary_records:
        category = record.get("작업 분류", "기타")
        category_dict.setdefault(category, []).append(record)

    for category, records in category_dict.items():
        category_node = {
            "name": category,
            "children": [
                {"name": record["내용"], "value": record["워킹데이 소요 시간"]}
                for record in records
            ],
        }
        task_treemap["children"].append(category_node)

    return {"progress_treemap": progress_treemap, "task_treemap": task_treemap}


def main():
    parser = argparse.ArgumentParser(description="PDA 데이터 추출 및 처리")
    parser.add_argument(
        "--output", type=str, default="output/output.json", help="JSON 출력 파일 경로"
    )
    parser.add_argument("--start-date", type=str, help="시작일 (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="종료일 (YYYY-MM-DD)")
    parser.add_argument("--month", type=str, help="특정 월 (YYYY-MM, 예: 2025-07)")
    args = parser.parse_args()

    logger.info(
        f"Environment configuration: LIMIT={LIMIT}, BATCH_SIZE={BATCH_SIZE}, SPREADSHEET_ID={SPREADSHEET_ID}"
    )

    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Created output directory: {output_dir}")

    try:
        logger.info("Starting data extraction from Google Drive")

        # 📅 날짜 범위 설정 (환경변수 + argparse 방식)
        date_range = None

        # 우선순위 1: 커맨드라인 인자
        if args.start_date and args.end_date:
            start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
            end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
            date_range = (start_date, end_date)
            logger.info(
                f"📅 사용자 지정 날짜 범위: {args.start_date} ~ {args.end_date}"
            )
        elif args.month:
            year, month = map(int, args.month.split("-"))
            start_date = datetime(year, month, 1)
            if month == 12:
                end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = datetime(year, month + 1, 1) - timedelta(days=1)
            date_range = (start_date, end_date)
            logger.info(
                f"📅 월 단위 설정: {args.month} ({start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})"
            )

        # 우선순위 2: 환경변수 (CI/CD용)
        elif os.getenv("EXTRACT_TARGET_MONTH") and os.getenv(
            "EXTRACT_TARGET_MONTH"
        ).lower() not in ["false", "none", ""]:
            target_month = os.getenv("EXTRACT_TARGET_MONTH")  # "2025-07" 형식
            year, month = map(int, target_month.split("-"))
            start_date = datetime(year, month, 1)
            if month == 12:
                end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = datetime(year, month + 1, 1) - timedelta(days=1)
            date_range = (start_date, end_date)
            logger.info(
                f"📅 환경변수 설정: {target_month} ({start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})"
            )
        elif os.getenv("EXTRACT_START_DATE") and os.getenv("EXTRACT_END_DATE"):
            start_date = datetime.strptime(os.getenv("EXTRACT_START_DATE"), "%Y-%m-%d")
            end_date = datetime.strptime(os.getenv("EXTRACT_END_DATE"), "%Y-%m-%d")
            date_range = (start_date, end_date)
            logger.info(
                f"📅 환경변수 날짜 범위: {os.getenv('EXTRACT_START_DATE')} ~ {os.getenv('EXTRACT_END_DATE')}"
            )

        # 우선순위 3: 기본값 (안전장치)
        else:
            now = datetime.now()
            start_date = datetime(now.year, now.month, 1)
            end_date = datetime(now.year, now.month, 8)
            date_range = (start_date, end_date)
            logger.info(
                f"📅 기본 안전 범위: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')} (현재 월 1~8일)"
            )

        # 새로운 드라이브 추출 방식 사용
        extractor = DriveDataExtractor()
        all_data = extractor.extract_all_data_from_drive(
            limit=LIMIT, date_range=date_range
        )

        if not all_data:
            logger.warning("No data to process.")
            return

        logger.info(
            f"Extracted data from {len(all_data)} spreadsheets from Google Drive."
        )

        final_records = []
        for idx, (info_df, worksheet_df, additional_info) in enumerate(all_data, 1):
            logger.info(f"Processing spreadsheet #{idx}")

            if info_df.empty:
                logger.warning("Empty info dataframe. Skipping.")
                continue
            logger.debug(
                f"Info data: {info_df[['S/N', 'Model Name']].to_dict(orient='records')}"
            )

            if worksheet_df.empty:
                logger.warning("Empty worksheet data. Skipping.")
                continue

            worksheet_df = worksheet_df[["내용", "시작 시간", "완료 시간"]].copy()
            logger.debug(
                f"Worksheet NaT counts: "
                f"Start Time NaT={worksheet_df['시작 시간'].isna().sum()}, "
                f"End Time NaT={worksheet_df['완료 시간'].isna().sum()}"
            )

            model_name = additional_info.get("model_name")
            mech_partner = additional_info.get("mech_partner")
            elec_partner = additional_info.get("elec_partner")
            avg_time_mapping = get_avg_time_mapping(model_name)
            logger.debug(f"Average time mapping (hours): {avg_time_mapping}")

            avg_time_mapping = {
                task: time * 60 for task, time in avg_time_mapping.items()
            }
            logger.debug(f"Average time mapping (minutes): {avg_time_mapping}")

            info_records = info_df.to_dict(orient="records")[0]
            task_summary_df = process_data(worksheet_df, model_name, info_records)

            task_summary_dict = task_summary_df.set_index("내용")["작업 분류"].to_dict()
            worksheet_df["작업 분류"] = worksheet_df["내용"].map(task_summary_dict)

            occurrence_stats, partner_stats = compute_occurrence_rates(
                worksheet_df,
                task_summary_df,
                avg_time_mapping,
                model_name,
                tolerance=TOLERANCE,
                mech_partner=mech_partner,
                elec_partner=elec_partner,
            )

            for category in occurrence_stats:
                occurrence_stats[category]["ot_count"] = 0
            for partner in partner_stats:
                partner_stats[partner]["ot_count"] = 0

            ot_details_dict = {}

            tolerance_minutes = TOLERANCE * 60

            task_summary_dict = task_summary_df.set_index("내용").to_dict()
            duration_dict = task_summary_dict["워킹데이 소요 시간"]
            duration_str_dict = task_summary_dict["총 워킹 소요 시간 (시간:분)"]

            for task_name in task_summary_df["내용"].unique():
                duration_hours = duration_dict.get(task_name)
                duration_str = duration_str_dict.get(task_name)
                if duration_hours is None or duration_str is None:
                    logger.warning(f"No duration data for task: {task_name}")
                    continue

                duration_minutes = duration_hours * 60
                avg_time = avg_time_mapping.get(task_name)
                logger.debug(
                    f"Task: {task_name}, Duration: {duration_minutes:.2f} min, "
                    f"Average Time: {avg_time} min"
                )
                if avg_time is not None and duration_minutes > (
                    avg_time + tolerance_minutes
                ):
                    category = task_summary_dict.get(task_name, "")
                    if category in occurrence_stats:
                        occurrence_stats[category]["ot_count"] = (
                            occurrence_stats[category].get("ot_count", 0) + 1
                        )
                        logger.info(
                            f"OT detected: Task={task_name}, Duration={duration_minutes:.2f} min, "
                            f"Average={avg_time} min, Tolerance={avg_time + tolerance_minutes} min"
                        )
                    if category == "기구" and "mech" in partner_stats:
                        partner_stats["mech"]["ot_count"] = (
                            partner_stats["mech"].get("ot_count", 0) + 1
                        )
                    elif category == "전장" and "elec" in partner_stats:
                        partner_stats["elec"]["ot_count"] = (
                            partner_stats["elec"].get("ot_count", 0) + 1
                        )
                    elif category == "TMS_반제품" and "tms_semi" in partner_stats:
                        partner_stats["tms_semi"]["ot_count"] = (
                            partner_stats["tms_semi"].get("ot_count", 0) + 1
                        )
                    ot_details_dict[task_name] = {
                        "task_name": task_name,
                        "duration": duration_str,
                    }

            ot_details = list(ot_details_dict.values())

            if "mech" in partner_stats and "name" not in partner_stats["mech"]:
                partner_stats["mech"]["name"] = mech_partner
            if "elec" in partner_stats and "name" not in partner_stats["elec"]:
                partner_stats["elec"]["name"] = elec_partner
            if "tms_semi" in partner_stats and "name" not in partner_stats["tms_semi"]:
                partner_stats["tms_semi"]["name"] = "TMS"

            info_records = sanitize_for_json(info_df.to_dict(orient="records"))
            worksheet_records = sanitize_for_json(
                worksheet_df.to_dict(orient="records")
            )
            task_summary_records = sanitize_for_json(
                task_summary_df.to_dict(orient="records")
            )

            task_summary_records_with_sn = []
            for record in task_summary_records:
                record["S/N"] = info_records[0]["S/N"]
                task_summary_records_with_sn.append(record)
                logger.debug(f"Added S/N to task_summary: {record}")
            task_summary_records = task_summary_records_with_sn

            progress_summary = calculate_progress_by_category(worksheet_df, model_name)

            treemap_data = convert_to_treemap_format(
                progress_summary, task_summary_records
            )

            record = {
                "info": info_records,
                "worksheet": worksheet_records,
                "task_summary": task_summary_records,
                "progress_summary": progress_summary,
                "stats": occurrence_stats,
                "partner_stats": partner_stats,
                "additional_info": additional_info,
                "treemap_data": treemap_data,
                "execution_date": datetime.now().date().isoformat(),
                "ot_details": ot_details,
            }
            final_records.append(record)
            logger.info(f"Processed spreadsheet #{idx}, OT details: {ot_details}")

        try:
            saved_file = save_to_json(
                {"documents": final_records}, output_path=args.output
            )
            logger.info(
                f"JSON saved successfully: {saved_file}, {len(final_records)} spreadsheets processed."
            )
        except Exception as e:
            logger.error(f"Failed to save JSON: {str(e)}", exc_info=True)
            raise

        try:
            file_metadata = {
                "name": os.path.basename(saved_file),
                "parents": [DRIVE_FOLDER_ID_JSON_DB],
            }
            media = MediaFileUpload(saved_file, mimetype="application/json")
            file = (
                drive_service.files()
                .create(body=file_metadata, media_body=media, fields="id")
                .execute()
            )
            file_id = file.get("id")
            drive_service.permissions().create(
                fileId=file_id, body={"type": "anyone", "role": "reader"}
            ).execute()
            json_url = f"https://drive.google.com/uc?export=view&id={file_id}"
            logger.info(f"JSON uploaded to Google Drive: {saved_file}, URL: {json_url}")
        except Exception as e:
            logger.error(f"Failed to upload to Google Drive: {str(e)}", exc_info=True)
            raise

        all_results = [
            (
                doc["info"],
                doc["worksheet"],
                doc["additional_info"]["mech_partner"],
                doc["additional_info"]["elec_partner"],
                doc["stats"],
                doc["partner_stats"],
                doc["task_summary"],
                doc["progress_summary"],
                doc["treemap_data"],
            )
            for doc in final_records
        ]
        # NOTE: NaN 그래프 생성 로직 제거 (불필요한 그래프)
        # 필요한 경우 dashboards/partner.py에서만 사용
        logger.info("Skipping NaN visualization charts generation.")

        logger.info("Waiting 10 seconds for Google Drive sync")
        time.sleep(10)

        json_data = load_json_files_from_drive(
            latest_only=True,
            local_json_path=saved_file,
            drive_folder_id=DRIVE_FOLDER_ID_JSON_DB,
        )
        if not json_data:
            logger.warning("Failed to load JSON data. Skipping heatmap generation.")
        else:
            quarterly_targets = {1: 40, 2: 30, 3: 20, 4: 0}
            auto_week, auto_range = auto_week_info(local_json_path=saved_file)
            if auto_week is not None and auto_range is not None:
                week_number = auto_week
                date_range = (
                    auto_range[0].strftime("%Y-%m-%d"),
                    auto_range[1].strftime("%Y-%m-%d"),
                )
                weekly_heatmap = generate_nan_trend_graph(
                    period="weekly",
                    chart_type="heatmap",
                    quarterly_targets=quarterly_targets,
                    week_number=week_number,
                    date_range=date_range,
                    days_per_week="auto",
                    group_by="partner",
                    visualize_ot=False,
                )
                if weekly_heatmap:
                    weekly_heatmap_url = upload_to_drive(weekly_heatmap)
                    logger.info(f"Weekly heatmap uploaded: {weekly_heatmap_url}")

                if is_last_friday_in_month(local_json_path=saved_file):
                    monthly_heatmap = generate_nan_trend_graph(
                        period="monthly",
                        chart_type="heatmap",
                        quarterly_targets=quarterly_targets,
                        group_by="partner",
                        visualize_ot=False,
                    )
                    if monthly_heatmap:
                        monthly_heatmap_url = upload_to_drive(monthly_heatmap)
                        logger.info(f"Monthly heatmap uploaded: {monthly_heatmap_url}")

        logger.info(
            "Main process completed: JSON generation, chart creation, and Google Drive upload."
        )

    except Exception as e:
        logger.error(f"Main process failed: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    logger.info("Running main_extract.py directly")
    main()
