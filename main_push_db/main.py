import os
import sys

sys.path.append(
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
)  # 프로젝트 루트를 sys.path에 추가
import logging
import json
import psycopg2
from utils.load_json_to_postgres import (
    load_json_to_db,
    create_tables as create_db_tables_from_util,
)

# --- 로깅 설정 ---
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # DEBUG 레벨로 설정

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
stream_handler.setFormatter(formatter)

logger.handlers = []  # 기존 핸들러 제거
logger.addHandler(stream_handler)

logger.info("main_push_db.py: Logging configured.")
logger.debug("This is a debug message to test logging")

# .env 로드 (로컬 개발용)
if os.getenv("RAILWAY_ENVIRONMENT") is None:
    logger.info(
        "RAILWAY_ENVIRONMENT not set. Attempting to load .env for local development."
    )
    try:
        from dotenv import load_dotenv

        if load_dotenv():
            logger.info(".env file loaded successfully.")
        else:
            logger.warning(
                ".env file not found or empty. Using system environment variables if available."
            )
    except ImportError:
        logger.warning("python-dotenv library not found. .env file will not be loaded.")
    except Exception as e:
        logger.error(f"Error loading .env file: {e}", exc_info=True)

# DB 환경 변수 로드 및 검증
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

if not all([DB_USER is not None, DB_HOST, DB_PORT, DB_NAME]):
    logger.critical(
        "FATAL: Database environment variables (DB_USER, DB_HOST, DB_PORT, DB_NAME) are not all set. Exiting."
    )
    logger.debug(
        f"DB_USER: {DB_USER}, DB_HOST: {DB_HOST}, DB_PORT: {DB_PORT}, DB_NAME: {DB_NAME}"
    )
    sys.exit(1)


def get_db_connection():
    try:
        conn = psycopg2.connect(
            dbname=DB_NAME, user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT
        )
        logger.info("Successfully connected to the database.")
        return conn
    except psycopg2.Error as e:
        logger.error(f"Database connection failed: {e}", exc_info=True)
        raise


def manage_processed_files_table(conn, operation, file_name=None, files_to_save=None):
    """Helper function to manage processed_files table operations."""
    cursor = None
    try:
        cursor = conn.cursor()
        if operation == "create_table":
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS processed_files (
                    id SERIAL PRIMARY KEY,
                    file_name VARCHAR(255) UNIQUE NOT NULL
                );
            """
            )
            logger.info("processed_files table checked/created.")
        elif operation == "load_files":
            cursor.execute("SELECT file_name FROM processed_files")
            files = [row[0] for row in cursor.fetchall()]
            logger.info(f"Loaded {len(files)} processed file names from DB.")
            return files
        elif operation == "save_files" and files_to_save:
            args_list = [(fname,) for fname in files_to_save]
            if args_list:
                psycopg2.extras.execute_values(
                    cursor,
                    "INSERT INTO processed_files (file_name) VALUES %s ON CONFLICT (file_name) DO NOTHING",
                    args_list,
                )
                logger.info(
                    f"Attempted to save/update {len(files_to_save)} file names in processed_files table."
                )
        elif operation == "remove_file" and file_name:
            cursor.execute(
                "DELETE FROM processed_files WHERE file_name = %s", (file_name,)
            )
            logger.info(f"Removed file '{file_name}' from processed_files table.")
        conn.commit()
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(
            f"Error during processed_files table operation '{operation}': {e}",
            exc_info=True,
        )
        raise
    finally:
        if cursor:
            cursor.close()


def delete_existing_data(conn, serial_number, title_number=None):
    cursor = None
    logger.info(
        f"Attempting to delete existing data for S/N='{serial_number}', Title='{title_number or 'N/A'}'"
    )
    try:
        cursor = conn.cursor()
        if title_number:
            cursor.execute(
                "SELECT document_id FROM info WHERE serial_number = %s AND title_number = %s",
                (serial_number, title_number),
            )
        else:
            cursor.execute(
                "SELECT document_id FROM info WHERE serial_number = %s",
                (serial_number,),
            )

        document_ids = [row[0] for row in cursor.fetchall()]

        if document_ids:
            logger.info(
                f"Found {len(document_ids)} document_id(s) for S/N='{serial_number}': {document_ids}. Proceeding with deletion."
            )
            for doc_id in document_ids:
                cursor.execute(
                    "DELETE FROM documents WHERE document_id = %s", (doc_id,)
                )
            logger.info(
                f"Successfully deleted data related to S/N='{serial_number}' (via documents table and CASCADE)."
            )
        else:
            logger.info(
                f"No existing data (document_ids) found in 'info' table to delete for S/N='{serial_number}'."
            )
        conn.commit()
    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        logger.error(
            f"Error deleting existing data for S/N='{serial_number}': {e}",
            exc_info=True,
        )
        raise
    finally:
        if cursor:
            cursor.close()


def main():
    logger.info("main_push_db.py: Main process started.")
    # LIMIT 완전 제거 - 모든 데이터 처리
    LIMIT = None
    logger.info(f"🔧 LIMIT 제거 완료: {LIMIT} (모든 데이터 처리)")

    logger.info(
        f"Database settings: User=****, Host={DB_HOST}, Port={DB_PORT}, DBName={DB_NAME}"
    )

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    output_dir = os.path.join(project_root, "output")

    logger.info(f"Looking for JSON files in: {output_dir}")
    if not os.path.isdir(output_dir):
        logger.error(
            f"Output directory '{output_dir}' does not exist or is not a directory. Exiting."
        )
        return

    conn = None
    successfully_processed_files_this_run = []

    try:
        conn = get_db_connection()
        create_db_tables_from_util(conn)
        manage_processed_files_table(conn, "create_table")

        db_already_processed_files = manage_processed_files_table(conn, "load_files")
        logger.info(
            f"Files previously marked as processed in DB: {db_already_processed_files}"
        )

        # 🔄 Railway/Staging 환경에서는 processed_files 테이블 기준으로 처리
        if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("DB_HOST") == "switchyard.proxy.rlwy.net":
            # 클라우드 환경: DB 테이블 기준
            json_files = db_already_processed_files
            logger.info(f"🌐 클라우드 환경: processed_files 테이블 기준으로 {len(json_files)}개 파일 처리")
        else:
            # 로컬 환경: 파일시스템 기준
            try:
                json_files = [
                    f
                    for f in os.listdir(output_dir)
                    if f.endswith(".json") and os.path.isfile(os.path.join(output_dir, f))
                ]
                logger.info(f"💻 로컬 환경: 파일시스템 기준으로 {len(json_files)}개 파일 발견")
            except OSError as e:
                logger.error(
                    f"Error listing files in output directory '{output_dir}': {e}",
                    exc_info=True,
                )
                return

        if not json_files:
            logger.warning("처리할 JSON 파일이 없습니다.")
            return
        
        logger.info(f"📋 최종 처리 대상: {json_files}")

        for json_file_name in json_files:
            full_json_file_path = os.path.join(output_dir, json_file_name)
            logger.info(f"--- Starting processing for file: {json_file_name} ---")

            # 클라우드 환경에서는 파일 존재 여부 확인
            if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("DB_HOST") == "switchyard.proxy.rlwy.net":
                if not os.path.exists(full_json_file_path):
                    logger.warning(f"🌐 클라우드 환경: 파일 '{json_file_name}'이 존재하지 않습니다. 건너뜁니다.")
                    continue

            if json_file_name in db_already_processed_files:
                logger.info(
                    f"File '{json_file_name}' was previously processed. Re-processing as per logic."
                )

            file_processing_outcome_successful = False
            try:
                logger.info(f"Reading JSON data from: {full_json_file_path}")
                with open(full_json_file_path, "r", encoding="utf-8") as f:
                    json_data_content = json.load(f)

                documents_in_file = json_data_content.get("documents", [])
                if not documents_in_file:
                    logger.warning(
                        f"No 'documents' array found or empty in file '{json_file_name}'. Skipping this file."
                    )
                    continue

                # Progress Change Detection 시스템이 변동 감지를 담당하므로 사전 삭제 로직 제거
                logger.info(
                    f"Found {len(documents_in_file)} documents in '{json_file_name}'. Progress Change Detection 시스템이 변동 감지를 수행합니다."
                )

                logger.info(
                    f"Calling load_json_to_db for file '{json_file_name}' (LIMIT={LIMIT} will be applied inside)."
                )
                load_json_to_db(full_json_file_path, LIMIT)

                file_processing_outcome_successful = True
                logger.info(
                    f"Successfully processed and initiated loading from file '{json_file_name}'."
                )

            except FileNotFoundError:
                logger.error(f"File not found: {full_json_file_path}", exc_info=True)
            except json.JSONDecodeError:
                logger.error(
                    f"JSON decode error for file: {full_json_file_path}", exc_info=True
                )
            except KeyError as e:
                logger.error(
                    f"KeyError processing file '{json_file_name}'. Missing key: {e}",
                    exc_info=True,
                )
            except Exception as e:
                logger.error(
                    f"Failed to process file '{json_file_name}'. Error: {e}",
                    exc_info=True,
                )

            if file_processing_outcome_successful:
                successfully_processed_files_this_run.append(json_file_name)
            logger.info(f"--- Finished processing for file: {json_file_name} ---")

        if successfully_processed_files_this_run:
            manage_processed_files_table(
                conn, "save_files", files_to_save=successfully_processed_files_this_run
            )

    except psycopg2.Error as db_err:
        logger.critical(
            f"Database critical error during main processing: {db_err}", exc_info=True
        )
    except Exception as e:
        logger.critical(
            f"An unexpected critical error occurred in main processing: {e}",
            exc_info=True,
        )
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed at the end of main process.")
        logger.info(
            f"main_push_db.py: Main process finished. Attempted to process {len(json_files)} file(s). Successfully initiated loading for {len(successfully_processed_files_this_run)} file(s)."
        )


if __name__ == "__main__":
    logger.info("main_push_db.py script execution started directly.")
    try:
        main()
    except SystemExit:
        logger.warning(
            "main_push_db.py: Script exited due to missing critical configuration or other sys.exit()."
        )
    except Exception as e:
        logger.critical(
            f"Unhandled exception in main_push_db.py __main__ block: {e}", exc_info=True
        )
    logger.info("main_push_db.py script execution finished.")
