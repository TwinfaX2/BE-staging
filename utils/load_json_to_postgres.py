import json
import psycopg2
from psycopg2.extras import Json
import logging
import os
import time
from datetime import datetime
from config.settings import DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME

# 로깅 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # DEBUG 레벨로 설정

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
stream_handler.setFormatter(formatter)

logger.handlers = []  # 기존 핸들러 제거
logger.addHandler(stream_handler)

logger.info("Logging setup completed for load_json_to_postgres.py")


# 헬퍼 함수들 정의
def connect_to_db():
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT
        )
        logger.info("✅ Database connection successful")
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}", exc_info=True)
        raise


def create_tables(conn):
    cursor = None
    try:
        cursor = conn.cursor()
        # ----- documents -----
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                document_id SERIAL PRIMARY KEY,
                execution_date DATE,
                timestamp TIMESTAMP
            );
        """
        )
        # ----- info -----
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS info (
                info_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                serial_number VARCHAR(128),
                model_name VARCHAR(128),
                mech_partner VARCHAR(50),
                elec_partner VARCHAR(50),
                customer VARCHAR(50),
                sales_order VARCHAR(50),
                line VARCHAR(50),
                quantity VARCHAR(10), 
                manufacturing_start TIMESTAMP,
                manufacturing_end TIMESTAMP,
                test_start TIMESTAMP,
                test_end TIMESTAMP,
                semi_product_start TIMESTAMP,
                module_outsourcing VARCHAR(50),
                product_code VARCHAR(50),
                title_number VARCHAR(255), 
                spreadsheet_link VARCHAR(512),
                CONSTRAINT uq_info_document_sn UNIQUE (document_id, serial_number)
            );
        """
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_info_serial_number ON info (serial_number);"
        )
        # ----- worksheet -----
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS worksheet (
                worksheet_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                task_name TEXT, 
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                task_category VARCHAR(50)
            );
        """
        )
        # ----- task_summary -----
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS task_summary (
                task_summary_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                serial_number VARCHAR(128),
                task_name VARCHAR(255), 
                task_category VARCHAR(50),
                working_hours DOUBLE PRECISION, 
                total_working_time VARCHAR(20),
                title_number VARCHAR(255) 
            );
        """
        )
        # ----- ot_details -----
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ot_details (
                ot_details_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                task_name VARCHAR(255), 
                duration DOUBLE PRECISION
            );
        """
        )
        # ----- progress_summary -----
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS progress_summary (
                progress_summary_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                serial_number VARCHAR(128),
                category VARCHAR(50),
                progress DOUBLE PRECISION, 
                CONSTRAINT unique_progress UNIQUE (document_id, serial_number, category)
            );
        """
        )
        # ----- stats -----
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS stats (
                stats_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                category VARCHAR(50),
                total_count INTEGER,
                nan_count INTEGER,
                completed_count INTEGER,
                nan_tasks JSONB,
                ot_count INTEGER
            );
        """
        )
        # ----- partner_stats -----
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS partner_stats (
                partner_stats_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                partner_type VARCHAR(50),
                nan_count INTEGER,
                ot_count INTEGER,
                name VARCHAR(100) 
            );
        """
        )
        # ----- additional_info -----
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS additional_info (
                additional_info_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                model_name VARCHAR(128),
                mech_partner VARCHAR(100),
                elec_partner VARCHAR(100)
            );
        """
        )
        # ----- treemap_data -----
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS treemap_data (
                treemap_data_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                progress_treemap JSONB,
                task_treemap JSONB
            );
        """
        )
        conn.commit()
        logger.info("✅ All application tables checked/created successfully.")
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Error creating tables: {e}", exc_info=True)
        raise
    finally:
        if cursor:
            cursor.close()


def insert_document(conn, document, timestamp):
    cursor = None
    target_serial_number = None
    try:
        cursor = conn.cursor()
        if (
            "info" in document
            and isinstance(document["info"], list)
            and len(document["info"]) > 0
        ):
            info_entry = document["info"][0]
            if isinstance(info_entry, dict):
                candidate_sn = info_entry.get("S/N")
                if (
                    candidate_sn
                    and isinstance(candidate_sn, str)
                    and candidate_sn.strip()
                ):
                    target_serial_number = candidate_sn.strip()

        if target_serial_number:
            cursor.execute(
                "SELECT document_id FROM info WHERE serial_number = %s ORDER BY info_id DESC LIMIT 1",
                (target_serial_number,),
            )
            result = cursor.fetchone()
            if result:
                logger.info(
                    f"Reusing existing document_id: {result[0]} for S/N='{target_serial_number}'."
                )
                return result[0]

        cursor.execute(
            "INSERT INTO documents (execution_date, timestamp) VALUES (%s, %s) RETURNING document_id",
            (document.get("execution_date"), timestamp),
        )
        new_document_id = cursor.fetchone()[0]
        logger.info(
            f"Created new document_id: {new_document_id} (S/N for context: '{target_serial_number or 'N/A'}')"
        )
        return new_document_id
    except KeyError as e:
        logger.error(
            f"KeyError during document insertion (S/N: '{target_serial_number or 'N/A'}'): Missing key {e}. Doc keys: {document.keys()}",
            exc_info=True,
        )
        raise
    except psycopg2.Error as e:
        logger.error(
            f"Database error during document insertion (S/N: '{target_serial_number or 'N/A'}'): {e}",
            exc_info=True,
        )
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error during document insertion (S/N: '{target_serial_number or 'N/A'}'): {e}",
            exc_info=True,
        )
        raise
    finally:
        if cursor:
            cursor.close()


def safe_datetime_value(value):
    """NaT 값을 None으로 변환하여 PostgreSQL 호환성 보장"""
    if value is None:
        return None
    if str(value).strip().lower() in ["nat", "none", ""]:
        return None
    # pandas NaT 객체 체크
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except:
        pass
    return value


def insert_info(conn, document_id, info_data_list):
    cursor = None
    try:
        cursor = conn.cursor()
        if not info_data_list or not isinstance(info_data_list, list):
            logger.warning(
                f"No valid info_data (list) to insert for document_id={document_id}."
            )
            return

        values_to_insert = []
        for info_item in info_data_list:
            if not isinstance(info_item, dict):
                logger.warning(
                    f"Item in info_data_list is not a dict for doc_id={document_id}. Item: {info_item}"
                )
                continue

            values_to_insert.append(
                (
                    document_id,
                    info_item.get("S/N", "N/A")[:128],
                    info_item.get("Model Name", "")[:128],
                    info_item.get("Mech Partner", "")[:50],
                    info_item.get("Elec Partner", "")[:50],
                    info_item.get("고객사", "")[:50],
                    info_item.get("판매오더", "")[:50],
                    info_item.get("라인", "")[:50],
                    info_item.get("수량", "")[:10],
                    safe_datetime_value(info_item.get("제조시작")),
                    safe_datetime_value(info_item.get("제조종료")),
                    safe_datetime_value(info_item.get("테스트시작")),
                    safe_datetime_value(info_item.get("테스트종료")),
                    safe_datetime_value(info_item.get("반제품시작")),
                    info_item.get("모듈외주", "")[:50],
                    info_item.get("제품코드", "N/A")[:50],
                    info_item.get("title number", "N/A")[:255],
                    info_item.get("spreadsheet_link", ""),
                )
            )

        if not values_to_insert:
            logger.warning(
                f"No valid info items to insert for document_id={document_id} after processing list."
            )
            return

        sql_insert_info = """
            INSERT INTO info (
                document_id, serial_number, model_name, mech_partner, elec_partner,
                customer, sales_order, line, quantity, manufacturing_start,
                manufacturing_end, test_start, test_end, semi_product_start, module_outsourcing,
                product_code, title_number, spreadsheet_link
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(sql_insert_info, values_to_insert)
        logger.info(
            f"Prepared to insert {len(values_to_insert)} info record(s) for document_id={document_id}"
        )
    except psycopg2.Error as e:
        logger.error(
            f"Database error preparing info insert for document_id={document_id}: {str(e)}",
            exc_info=True,
        )
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error preparing info insert for document_id={document_id}: {str(e)}",
            exc_info=True,
        )
        raise
    finally:
        if cursor:
            cursor.close()


def insert_worksheet(conn, document_id, worksheet_data):
    cursor = None
    try:
        cursor = conn.cursor()
        if not worksheet_data:
            logger.warning(
                f"No data to insert into worksheet for document_id={document_id}."
            )
            return

        # 디버깅: worksheet_data 타입 확인
        logger.debug(
            f"insert_worksheet: worksheet_data type={type(worksheet_data)}, length={len(worksheet_data) if hasattr(worksheet_data, '__len__') else 'N/A'}"
        )

        # 문자열로 전달된 경우 JSON 파싱 시도
        if isinstance(worksheet_data, str):
            import json

            try:
                worksheet_data = json.loads(worksheet_data)
                logger.info(
                    f"Successfully parsed worksheet_data from string to {type(worksheet_data)}"
                )
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse worksheet_data string: {e}")
                return

        values_to_insert = []
        for worksheet_item in worksheet_data:
            if not isinstance(worksheet_item, dict):
                logger.warning(
                    f"Item in worksheet_data is not a dict for doc_id={document_id}. Item: {worksheet_item}"
                )
                continue
            values_to_insert.append(
                (
                    document_id,
                    worksheet_item.get("내용"),
                    safe_datetime_value(worksheet_item.get("시작 시간")),
                    safe_datetime_value(worksheet_item.get("완료 시간")),
                    worksheet_item.get("작업 분류"),
                )
            )

        if not values_to_insert:
            logger.warning(
                f"No valid worksheet items to insert for document_id={document_id} after preparing."
            )
            return

        cursor.executemany(
            """
            INSERT INTO worksheet (document_id, task_name, start_time, end_time, task_category)
            VALUES (%s, %s, %s, %s, %s)
            """,
            values_to_insert,
        )
        logger.info(
            f"Prepared to insert {len(values_to_insert)} worksheet records for document_id={document_id}"
        )
    except Exception as e:
        logger.error(
            f"Error inserting worksheet for doc_id={document_id}: {str(e)}",
            exc_info=True,
        )
        raise
    finally:
        if cursor:
            cursor.close()


def insert_task_summary(conn, document_id, task_summary_data, info_data_list):
    cursor = None
    try:
        cursor = conn.cursor()
        if not task_summary_data:
            logger.warning(
                f"No data to insert into task_summary for document_id={document_id}."
            )
            return

        title_number_from_info = "N/A"
        if (
            info_data_list
            and isinstance(info_data_list, list)
            and len(info_data_list) > 0
        ):
            if isinstance(info_data_list[0], dict):
                title_number_from_info = info_data_list[0].get("title number", "N/A")[
                    :255
                ]

        values_to_insert = []
        for task_item in task_summary_data:
            if not isinstance(task_item, dict):
                logger.warning(
                    f"Item in task_summary_data is not a dict for doc_id={document_id}. Item: {task_item}"
                )
                continue
            serial_number = task_item.get("S/N")
            if not serial_number:
                logger.warning(
                    f"S/N missing in task_summary_data for doc_id={document_id}, task: {task_item.get('내용', 'Unknown Task')}. Skipping."
                )
                continue
            values_to_insert.append(
                (
                    document_id,
                    serial_number[:128],
                    task_item.get("내용", "")[:255],
                    task_item.get("작업 분류", "")[:50],
                    task_item.get("워킹데이 소요 시간"),
                    task_item.get("총 워킹 소요 시간 (시간:분)", "")[:20],
                    title_number_from_info,
                )
            )

        if not values_to_insert:
            logger.warning(
                f"No valid task_summary items to insert for document_id={document_id} after filtering."
            )
            return

        cursor.executemany(
            """
            INSERT INTO task_summary (
                document_id, serial_number, task_name, task_category, working_hours, total_working_time, title_number
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            values_to_insert,
        )
        logger.info(
            f"Prepared to insert {len(values_to_insert)} task_summary records for document_id={document_id}"
        )
    except KeyError as e:
        logger.error(
            f"Key missing in task_summary data for doc_id={document_id}: {str(e)}",
            exc_info=True,
        )
        raise
    except Exception as e:
        logger.error(
            f"Error inserting task_summary for doc_id={document_id}: {str(e)}",
            exc_info=True,
        )
        raise
    finally:
        if cursor:
            cursor.close()


def parse_duration(duration_str: str) -> float | None:
    if not duration_str or not isinstance(duration_str, str):
        logger.warning(f"Invalid or empty duration string received: {duration_str}")
        return None
    try:
        parts = duration_str.replace("시간", "").replace("분", "").split()
        hours = int(parts[0]) if parts and parts[0] else 0
        minutes = int(parts[1]) if len(parts) > 1 and parts[1] else 0
        return hours + (minutes / 60.0)
    except ValueError as ve:
        logger.error(
            f"ValueError parsing duration string: '{duration_str}' - Error: {str(ve)}",
            exc_info=True,
        )
        return None
    except Exception as e:
        logger.error(
            f"Failed to parse duration string: '{duration_str}' - Error: {str(e)}",
            exc_info=True,
        )
        return None


def insert_ot_details(conn, document_id, ot_details_data):
    cursor = None
    try:
        cursor = conn.cursor()
        if not ot_details_data:
            logger.warning(
                f"No data to insert into ot_details for document_id={document_id}."
            )
            return

        values_to_insert = []
        for ot_item in ot_details_data:
            if not isinstance(ot_item, dict) or "duration" not in ot_item:
                logger.warning(
                    f"Invalid ot_detail item for doc_id={document_id}: {ot_item}. Skipping."
                )
                continue

            duration_float = parse_duration(ot_item["duration"])
            if duration_float is None:
                logger.warning(
                    f"Skipping ot_detail item due to duration parsing error for doc_id={document_id}, task='{ot_item.get('task_name')}'. Duration string: '{ot_item['duration']}'"
                )
                continue
            values_to_insert.append(
                (document_id, ot_item.get("task_name", "")[:255], duration_float)
            )

        if not values_to_insert:
            logger.warning(
                f"No valid ot_details items to insert for document_id={document_id} after parsing/filtering."
            )
            return

        cursor.executemany(
            """
            INSERT INTO ot_details (document_id, task_name, duration)
            VALUES (%s, %s, %s)
            """,
            values_to_insert,
        )
        logger.info(
            f"Prepared to insert {len(values_to_insert)} ot_details records for document_id={document_id}"
        )
    except Exception as e:
        logger.error(
            f"Error inserting ot_details for doc_id={document_id}: {str(e)}",
            exc_info=True,
        )
        raise
    finally:
        if cursor:
            cursor.close()


def insert_progress_summary(conn, document_id, progress_data):
    cursor = None
    logger.debug(
        f"Attempting insert_progress_summary for doc_id={document_id}. Data type: {type(progress_data)}, Preview: {str(progress_data)[:200]}"
    )
    try:
        cursor = conn.cursor()

        serial_number_for_document = None
        cursor.execute(
            "SELECT serial_number FROM info WHERE document_id = %s ORDER BY info_id DESC LIMIT 1",
            (document_id,),
        )
        sn_row = cursor.fetchone()
        serial_number_for_document = sn_row[0] if sn_row else None

        if not serial_number_for_document:
            logger.error(
                f"Serial number not found in 'info' table for document_id={document_id}. Cannot insert progress_summary."
            )
            return

        try:
            cursor.execute(
                "DELETE FROM progress_summary WHERE document_id = %s", (document_id,)
            )
            logger.debug(
                f"Cleared existing progress_summary rows for document_id={document_id}"
            )
        except Exception as del_err:
            logger.error(
                f"Failed to clear old progress_summary rows for document_id={document_id}: {del_err}",
                exc_info=True,
            )
            raise

        items_to_insert = []
        if isinstance(progress_data, dict):
            for category_key, progress_value in progress_data.items():
                try:
                    items_to_insert.append(
                        {
                            "S/N": serial_number_for_document,
                            "category": str(category_key)[:50],
                            "progress": float(progress_value),
                        }
                    )
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid progress value for category '{category_key}' (doc_id={document_id}, S/N={serial_number_for_document}): {progress_value}. Skipping."
                    )

        elif isinstance(progress_data, list):
            for item in progress_data:
                if not isinstance(item, dict):
                    logger.warning(
                        f"Progress_summary item is not a dict for doc_id={document_id}: {item}. Skipping."
                    )
                    continue
                sn_from_item = item.get("S/N")
                cat_from_item = item.get("category")
                try:
                    prog_val = float(item.get("progress", 0.0))
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid progress value for S/N='{sn_from_item}', category='{cat_from_item}' (doc_id={document_id}): {item.get('progress')}. Setting to 0.0."
                    )
                    prog_val = 0.0

                if sn_from_item and cat_from_item:
                    final_sn = (
                        sn_from_item[:128]
                        if sn_from_item
                        else serial_number_for_document[:128]
                    )
                    if not final_sn:
                        logger.warning(
                            f"S/N missing or unobtainable for progress_summary item (doc_id={document_id}): {item}. Skipping."
                        )
                        continue
                    items_to_insert.append(
                        {
                            "S/N": final_sn,
                            "category": str(cat_from_item)[:50],
                            "progress": prog_val,
                        }
                    )
                else:
                    logger.warning(
                        f"S/N or category missing in progress_summary list item for doc_id={document_id}: {item}. Skipping."
                    )
        else:
            if progress_data:
                logger.error(
                    f"Invalid type for progress_data for document_id={document_id}: {type(progress_data)}. Expected dict or list. Skipping."
                )
            else:
                logger.warning(
                    f"No data to insert into progress_summary for document_id={document_id} (data is None or empty)."
                )
            return

        if not items_to_insert:
            logger.warning(
                f"No valid progress_summary items to insert for document_id={document_id} after processing."
            )
            return

        for item_data in items_to_insert:
            cursor.execute(
                """
                INSERT INTO progress_summary (document_id, serial_number, category, progress)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (document_id, serial_number, category) DO UPDATE SET progress = EXCLUDED.progress 
                """,
                (
                    document_id,
                    item_data["S/N"],
                    item_data["category"],
                    item_data["progress"],
                ),
            )
        logger.info(
            f"Prepared to insert/update {len(items_to_insert)} progress_summary records for document_id={document_id}"
        )
    except psycopg2.Error as e:
        logger.error(
            f"Database error inserting/updating progress_summary for doc_id={document_id}: {str(e)}",
            exc_info=True,
        )
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error inserting/updating progress_summary for doc_id={document_id}: {str(e)}",
            exc_info=True,
        )
        raise
    finally:
        if cursor:
            cursor.close()


def insert_stats(conn, document_id, stats_data):
    cursor = None
    try:
        cursor = conn.cursor()
        if not stats_data or not isinstance(stats_data, dict):
            logger.warning(
                f"No valid stats_data (dict) to insert for document_id={document_id}."
            )
            return

        values_to_insert = []
        for category, stat_item in stats_data.items():
            if not isinstance(stat_item, dict):
                logger.warning(
                    f"Stat for category '{category}' is not a dict for document_id={document_id}. Skipping: {stat_item}"
                )
                continue
            values_to_insert.append(
                (
                    document_id,
                    str(category)[:50],
                    stat_item.get("total_count"),
                    stat_item.get("nan_count"),
                    stat_item.get("completed_count"),
                    Json(stat_item.get("nan_tasks", [])),
                    stat_item.get("ot_count"),
                )
            )

        if not values_to_insert:
            logger.warning(
                f"No valid stat items to insert for document_id={document_id} after filtering."
            )
            return

        cursor.executemany(
            """
            INSERT INTO stats (document_id, category, total_count, nan_count, completed_count, nan_tasks, ot_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            values_to_insert,
        )
        logger.info(
            f"Prepared to insert {len(values_to_insert)} stats records for document_id={document_id}"
        )
    except Exception as e:
        logger.error(
            f"Error inserting stats for doc_id={document_id}: {str(e)}", exc_info=True
        )
        raise
    finally:
        if cursor:
            cursor.close()


def insert_partner_stats(conn, document_id, partner_stats_data):
    cursor = None
    try:
        cursor = conn.cursor()
        if not isinstance(partner_stats_data, dict):
            logger.warning(
                f"partner_stats_data is not a dict for document_id={document_id}. Skipping. Data: {partner_stats_data}"
            )
            return

        values_to_insert = []
        for partner_type, stat_item in partner_stats_data.items():
            if not isinstance(stat_item, dict):
                logger.warning(
                    f"Stat for partner_type '{partner_type}' is not a dict for document_id={document_id}. Skipping: {stat_item}"
                )
                continue
            values_to_insert.append(
                (
                    document_id,
                    str(partner_type)[:50],
                    stat_item.get("nan_count"),
                    stat_item.get("ot_count"),
                    stat_item.get("name", "")[:100],
                )
            )

        if not values_to_insert:
            logger.warning(
                f"No valid partner_stat items to insert for document_id={document_id} after filtering."
            )
            return

        cursor.executemany(
            """
            INSERT INTO partner_stats (document_id, partner_type, nan_count, ot_count, name)
            VALUES (%s, %s, %s, %s, %s)
            """,
            values_to_insert,
        )
        logger.info(
            f"Prepared to insert {len(values_to_insert)} partner_stats records for document_id={document_id}"
        )
    except Exception as e:
        logger.error(
            f"Error inserting partner_stats for doc_id={document_id}: {str(e)}",
            exc_info=True,
        )
        raise
    finally:
        if cursor:
            cursor.close()


def insert_additional_info(conn, document_id, additional_info_data):
    cursor = None
    try:
        cursor = conn.cursor()
        if not additional_info_data or not isinstance(additional_info_data, dict):
            logger.warning(
                f"No valid additional_info_data (dict) to insert for document_id={document_id}."
            )
            return
        cursor.execute(
            """
            INSERT INTO additional_info (document_id, model_name, mech_partner, elec_partner)
            VALUES (%s, %s, %s, %s)
            """,
            (
                document_id,
                additional_info_data.get("model_name", "")[:128],
                additional_info_data.get("mech_partner", "")[:100],
                additional_info_data.get("elec_partner", "")[:100],
            ),
        )
        logger.info(f"Prepared to insert additional_info for document_id={document_id}")
    except Exception as e:
        logger.error(
            f"Error inserting additional_info for doc_id={document_id}: {str(e)}",
            exc_info=True,
        )
        raise
    finally:
        if cursor:
            cursor.close()


def insert_treemap_data(conn, document_id, treemap_data):
    cursor = None
    try:
        cursor = conn.cursor()
        if not treemap_data or not isinstance(treemap_data, dict):
            logger.warning(
                f"No valid treemap_data (dict) to insert for document_id={document_id}."
            )
            return
        cursor.execute(
            """
            INSERT INTO treemap_data (document_id, progress_treemap, task_treemap)
            VALUES (%s, %s, %s)
            """,
            (
                document_id,
                Json(treemap_data.get("progress_treemap", {})),
                Json(treemap_data.get("task_treemap", {})),
            ),
        )
        logger.info(f"Prepared to insert treemap_data for document_id={document_id}")
    except Exception as e:
        logger.error(
            f"Error inserting treemap_data for doc_id={document_id}: {str(e)}",
            exc_info=True,
        )
        raise
    finally:
        if cursor:
            cursor.close()


def verify_data(conn, document_id):
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM documents WHERE document_id = %s", (document_id,)
        )
        doc_count = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM info WHERE document_id = %s", (document_id,)
        )
        info_count = cursor.fetchone()[0]
        logger.info(
            f"Verification for document_id {document_id}: documents rows = {doc_count}, info rows = {info_count}"
        )
    except Exception as e:
        logger.error(
            f"Error during data verification for document_id {document_id}: {e}",
            exc_info=True,
        )
    finally:
        if cursor:
            cursor.close()


def load_json_to_db(json_file_path, LIMIT):
    start_total = time.time()
    logger.info(f"Starting load_json_to_db for file: {json_file_path}, LIMIT: {LIMIT}")

    if not os.path.exists(json_file_path):
        logger.error(f"File {json_file_path} does not exist.")
        raise FileNotFoundError(f"File {json_file_path} does not exist.")

    try:
        with open(json_file_path, "r", encoding="utf-8") as f:
            raw_data = f.read()
            logger.info(
                f"Read {len(raw_data)} bytes from {json_file_path}. Preview: {raw_data[:200]}"
            )
            data = json.loads(raw_data)
            logger.info(
                f"Successfully parsed JSON from {json_file_path}. Top-level type: {type(data)}"
            )
    except json.JSONDecodeError as e:
        logger.error(
            f"JSON parsing failed for file {json_file_path}: {e}", exc_info=True
        )
        raise
    except Exception as e:
        logger.error(f"Error reading file {json_file_path}: {e}", exc_info=True)
        raise

    if not isinstance(data, dict):
        logger.error(f"❌ Top-level JSON object is not a dict. Type: {type(data)}")
        raise TypeError("Top-level JSON object must be a dict.")
    if "documents" not in data or not isinstance(data.get("documents"), list):
        logger.error(
            f"❌ 'documents' key missing or not a list. Keys: {list(data.keys())}, Type: {type(data.get('documents'))}"
        )
        raise KeyError("'documents' key (list type) must be present in the JSON data.")
    if "timestamp" not in data:
        logger.error(f"❌ 'timestamp' key missing from JSON.")
        raise KeyError("'timestamp' key must be present for insert_document.")

    conn = None
    try:
        conn = connect_to_db()
        create_tables(conn)

        documents_to_process = data["documents"][:LIMIT]
        num_documents_to_process = len(documents_to_process)
        logger.info(
            f"Preparing to process {num_documents_to_process} documents based on LIMIT={LIMIT}."
        )

        BATCH_SIZE = int(os.getenv("BATCH_SIZE", 1))
        logger.info(f"Using BATCH_SIZE={BATCH_SIZE}")
        total_batches = (
            (num_documents_to_process + BATCH_SIZE - 1) // BATCH_SIZE
            if BATCH_SIZE > 0
            else (1 if num_documents_to_process > 0 else 0)
        )

        for i in range(0, num_documents_to_process, BATCH_SIZE):
            current_batch_number = (i // BATCH_SIZE) + 1
            batch_documents = documents_to_process[i : i + BATCH_SIZE]
            num_in_batch = len(batch_documents)

            logger.info(
                f"Starting batch {current_batch_number}/{total_batches} with {num_in_batch} documents."
            )
            start_batch_time = time.time()

            try:
                for doc_idx, document_data in enumerate(batch_documents):
                    if not isinstance(document_data, dict):
                        logger.error(
                            f"❌ Document item at index {i+doc_idx} is not a dict. Type: {type(document_data)}. Skipping."
                        )
                        continue

                    current_sn_for_log = "UNKNOWN_SN"
                    doc_info_list = document_data.get("info")
                    if (
                        doc_info_list
                        and isinstance(doc_info_list, list)
                        and len(doc_info_list) > 0
                        and isinstance(doc_info_list[0], dict)
                    ):
                        current_sn_for_log = doc_info_list[0].get("S/N", "UNKNOWN_SN")

                    logger.info(
                        f"  Processing document {doc_idx+1}/{num_in_batch} in batch {current_batch_number} (S/N: {current_sn_for_log})."
                    )

                    document_id = insert_document(
                        conn, document_data, data["timestamp"]
                    )

                    insert_info(conn, document_id, document_data.get("info", []))
                    insert_worksheet(
                        conn, document_id, document_data.get("worksheet", [])
                    )
                    insert_task_summary(
                        conn,
                        document_id,
                        document_data.get("task_summary", []),
                        document_data.get("info", []),
                    )
                    insert_ot_details(
                        conn, document_id, document_data.get("ot_details", [])
                    )
                    insert_progress_summary(
                        conn, document_id, document_data.get("progress_summary", {})
                    )
                    insert_stats(conn, document_id, document_data.get("stats", {}))
                    insert_partner_stats(
                        conn, document_id, document_data.get("partner_stats", {})
                    )
                    insert_additional_info(
                        conn, document_id, document_data.get("additional_info", {})
                    )
                    insert_treemap_data(
                        conn, document_id, document_data.get("treemap_data", {})
                    )

                    verify_data(conn, document_id)
                    logger.info(
                        f"  Successfully processed document {doc_idx+1}/{num_in_batch} (S/N: {current_sn_for_log}, DocID: {document_id})."
                    )

                conn.commit()
                logger.info(
                    f"Batch {current_batch_number}/{total_batches} committed successfully. Time: {time.time() - start_batch_time:.2f}s."
                )

            except Exception as batch_processing_error:
                logger.error(
                    f"Error processing batch {current_batch_number}. Rolling back. Error: {batch_processing_error}",
                    exc_info=True,
                )
                if conn:
                    conn.rollback()
                raise

        logger.info(
            f"✅ All {total_batches} batches processed successfully for file '{json_file_path}'."
        )

    except Exception as main_error:
        logger.error(
            f"Main processing loop failed for file '{json_file_path}': {main_error}",
            exc_info=True,
        )
        if conn:
            try:
                conn.rollback()
            except Exception as rollback_err:
                logger.error(
                    f"Error during final rollback for '{json_file_path}': {rollback_err}",
                    exc_info=True,
                )
        raise
    finally:
        if conn:
            conn.close()
            logger.info(f"Database connection closed for file '{json_file_path}'.")
        logger.info(
            f"Total execution time for load_json_to_db (file: '{json_file_path}'): {time.time() - start_total:.2f} seconds."
        )


if __name__ == "__main__":
    logger.info("Running load_json_to_postgres.py directly for testing.")
    # 테스트 환경 변수 설정
    os.environ["DB_USER"] = os.getenv("DB_USER", "testuser")
    os.environ["DB_PASS"] = os.getenv("DB_PASS", "testpass")
    os.environ["DB_HOST"] = os.getenv("DB_HOST", "localhost")
    os.environ["DB_PORT"] = os.getenv("DB_PORT", "5432")
    os.environ["DB_NAME"] = os.getenv("DB_NAME", "testdb")
    os.environ["BATCH_SIZE"] = os.getenv("BATCH_SIZE", "1")

    logger.info(
        f"Test DB: User={os.getenv('DB_USER')}, Host={os.getenv('DB_HOST')}, DB={os.getenv('DB_NAME')}"
    )
    logger.info(f"Test BATCH_SIZE: {os.getenv('BATCH_SIZE')}")

    sample_json_path = "test_sample_data_postgres.json"
    sample_data = {
        "timestamp": datetime.now().isoformat(),
        "documents": [
            {
                "execution_date": "2025-06-02",
                "info": [
                    {
                        "S/N": "TEST123",
                        "Model Name": "ModelX",
                        "title number": "TITLE001",
                    }
                ],
                "worksheet": [{"내용": "Task1", "작업 분류": "기구"}],
                "task_summary": [
                    {
                        "S/N": "TEST123",
                        "내용": "Task1",
                        "작업 분류": "기구",
                        "워킹데이 소요 시간": 2.5,
                    }
                ],
                "ot_details": [{"task_name": "OT1", "duration": "2시간 30분"}],
                "progress_summary": {"기구": 50.0},
                "stats": {
                    "기구": {
                        "total_count": 10,
                        "nan_count": 2,
                        "completed_count": 8,
                        "nan_tasks": [],
                        "ot_count": 1,
                    }
                },
                "partner_stats": {
                    "mech": {"nan_count": 2, "ot_count": 1, "name": "MechPartner"}
                },
                "additional_info": {
                    "model_name": "ModelX",
                    "mech_partner": "MechPartner",
                    "elec_partner": "ElecPartner",
                },
                "treemap_data": {"progress_treemap": {}, "task_treemap": {}},
            }
        ],
    }
    try:
        with open(sample_json_path, "w", encoding="utf-8") as f:
            json.dump(sample_data, f, indent=4, ensure_ascii=False)
        logger.info(f"Sample test JSON created: {sample_json_path}")
        load_json_to_db(sample_json_path, LIMIT=len(sample_data["documents"]))
        logger.info("Test run of load_json_to_db completed successfully.")
    except FileNotFoundError:
        logger.error(f"Test JSON file '{sample_json_path}' not found.")
    except psycopg2.Error as db_err:
        logger.error(f"Database error during test run: {db_err}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error during test run: {e}", exc_info=True)
    finally:
        if os.path.exists(sample_json_path):
            logger.info(f"Test finished. You can manually delete '{sample_json_path}'.")
