import os
import re
import logging
import pandas as pd
from googleapiclient.errors import HttpError
from dotenv import load_dotenv
from utils.google_api import (
    get_order_no,
    get_linked_spreadsheet_ids,
    get_sheets_service
)
from utils.data_processing_core import parse_korean_datetime

# 로깅 설정
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
stream_handler.setFormatter(formatter)

logger.handlers = []  # 기존 핸들러 제거
logger.addHandler(stream_handler)

logger.info("sheet_extractor.py: Logging configured.")
logger.debug("This is a debug message to test logging")

# .env 로드 (main_extract.py에서 로드하지 않은 경우 대비)
load_dotenv()
TARGET_SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')
TARGET_SHEET_NAME = os.getenv('TARGET_SHEET_NAME')
LIMIT = int(os.getenv('LIMIT', 0))  # 0이면 모든 ID 처리
BATCH_SIZE = int(os.getenv('BATCH_SIZE', 10))

if not TARGET_SPREADSHEET_ID:
    logger.critical("Environment variable SPREADSHEET_ID is not set. sheet_extractor initialization failed.")
    raise ValueError("Environment variable SPREADSHEET_ID is not set.")
if not TARGET_SHEET_NAME:
    logger.critical("Environment variable TARGET_SHEET_NAME is not set. sheet_extractor initialization failed.")
    raise ValueError("Environment variable TARGET_SHEET_NAME is not set.")

def extract_hyperlink(cell_value):
    """Extract hyperlink URL from cell."""
    if isinstance(cell_value, dict) and 'hyperlink' in cell_value:
        return cell_value['hyperlink']
    return cell_value

def fetch_info_metadata(spreadsheet_id: str):
    logger.info(f"Fetching info metadata for Spreadsheet ID: {spreadsheet_id}")
    try:
        title_number_candidate = get_order_no(spreadsheet_id)
        if title_number_candidate is None:
            logger.error(f"Could not retrieve valid title_number for Spreadsheet ID: {spreadsheet_id}. Skipping.")
            return pd.DataFrame(), {}

        title_number = title_number_candidate
        logger.info(f"Successfully extracted Title Number: '{title_number}' for Spreadsheet ID: {spreadsheet_id}")

        info_range = "정보판!A3:F7"
        data = get_sheets_service().spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=info_range,
            valueRenderOption="FORMATTED_VALUE"
        ).execute().get('values', [])

        if not data or len(data) < 5:
            logger.warning(f"Insufficient info data (required 5 rows, got {len(data)}) for Spreadsheet ID: {spreadsheet_id}")
            return pd.DataFrame(), {}

        info_dict = {
            '판매오더': data[0][1] if len(data[0]) > 1 else None,
            '고객사': data[0][3] if len(data[0]) > 3 else None,
            '라인': data[0][5] if len(data[0]) > 5 else None,
            '제품코드': data[1][1] if len(data[1]) > 1 else None,
            'MODEL': data[1][3] if len(data[1]) > 3 else None,
            '수량': data[1][5] if len(data[1]) > 5 else None,
            '기구외주': data[2][1] if len(data[2]) > 1 else None,
            '전장외주': data[2][3] if len(data[2]) > 3 else None,
            '모듈외주': data[2][5] if len(data[2]) > 5 else None,
            '제조시작': parse_korean_datetime(data[3][1] if len(data[3]) > 1 else None),
            '제조종료': parse_korean_datetime(data[3][3] if len(data[3]) > 3 else None),
            'S/N': data[3][5] if len(data[3]) > 5 else None,
            '테스트시작': parse_korean_datetime(data[4][1] if len(data[4]) > 1 else None),
            '테스트종료': parse_korean_datetime(data[4][3] if len(data[4]) > 3 else None),
            '반제품시작': parse_korean_datetime(data[4][5] if len(data[4]) > 5 else None),
        }

        logger.debug(f"Info parsed (ID: {spreadsheet_id}): {info_dict}")

        sn = info_dict.get('S/N')
        if not sn:
            logger.warning(f"No S/N found in info data for Spreadsheet ID: {spreadsheet_id}. Skipping.")
            return pd.DataFrame(), {}

        model_name_val = info_dict.get('MODEL', '미정')
        if not model_name_val:
            logger.warning(f"No MODEL found for Spreadsheet ID: {spreadsheet_id}, S/N: {sn}. Using '미정'.")

        additional_info = {
            'model_name': model_name_val,
            'mech_partner': info_dict.get('기구외주', '미정'),
            'elec_partner': info_dict.get('전장외주', '미정')
        }

        spreadsheet_link = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        
        df_data = {
            'S/N': sn,
            'title number': title_number,
            'Model Name': model_name_val,
            'Mech Partner': additional_info['mech_partner'],
            'Elec Partner': additional_info['elec_partner'],
            '고객사': info_dict.get('고객사'),
            '판매오더': info_dict.get('판매오더'),
            '라인': info_dict.get('라인'),
            '수량': info_dict.get('수량'),
            '제조시작': info_dict.get('제조시작'),
            '제조종료': info_dict.get('제조종료'),
            '테스트시작': info_dict.get('테스트시작'),
            '테스트종료': info_dict.get('테스트종료'),
            '반제품시작': info_dict.get('반제품시작'),
            '모듈외주': info_dict.get('모듈외주'),
            '제품코드': info_dict.get('제품코드'),
            'spreadsheet_link': spreadsheet_link
        }
        df = pd.DataFrame([df_data])

        logger.info(f"Info DataFrame created for Spreadsheet ID: {spreadsheet_id}, S/N: {sn}")
        return df, additional_info

    except HttpError as e:
        logger.error(f"Google Sheets API error (info extraction, ID: {spreadsheet_id}): {e}", exc_info=True)
        return pd.DataFrame(), {}
    except Exception as e:
        logger.error(f"Unexpected error during info extraction (ID: {spreadsheet_id}): {e}", exc_info=True)
        return pd.DataFrame(), {}

def fetch_worksheet_data(spreadsheet_id: str):
    logger.info(f"Fetching worksheet data for Spreadsheet ID: {spreadsheet_id}")
    try:
        worksheet_range = "Worksheet!A1:G"
        resp_data = get_sheets_service().spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=worksheet_range,
            valueRenderOption="FORMATTED_VALUE"
        ).execute()
        data = resp_data.get('values', [])

        if not data or len(data) < 7:
            logger.warning(f"Insufficient WORKSHEET data or no header found for Spreadsheet ID: {spreadsheet_id}")
            return pd.DataFrame()

        header = data[6]
        rows = data[7:] if len(data) > 7 else []

        if not rows:
            logger.warning(f"No data rows in WORKSHEET (only header) for Spreadsheet ID: {spreadsheet_id}")
            return pd.DataFrame()

        max_cols = len(header)
        adjusted_rows = [row[:max_cols] + [''] * (max_cols - len(row)) if len(row) < max_cols else row[:max_cols] for row in rows]
        
        df = pd.DataFrame(adjusted_rows, columns=header)

        column_mapping = {
            '내용': ['내용', '작업 내용', 'Task'],
            '시작 시간': ['시작 시간', '시작시간', 'Start Time'],
            '완료 시간': ['완료 시간', '완료시간', 'End Time']
        }
        renamed_cols = {}
        current_columns = df.columns.tolist()
        for expected_col, possible_names in column_mapping.items():
            for p_name in possible_names:
                if p_name in current_columns:
                    renamed_cols[p_name] = expected_col
                    break

        df.rename(columns=renamed_cols, inplace=True)
        
        needed_cols = ['내용', '시작 시간', '완료 시간']
        missing_cols = [col for col in needed_cols if col not in df.columns]
        if missing_cols:
            logger.error(f"Missing required columns in WORKSHEET for Spreadsheet ID: {spreadsheet_id}: {missing_cols}. Skipping.")
            return pd.DataFrame()

        df = df[needed_cols]

        for col in ['시작 시간', '완료 시간']:
            if col in df.columns:
                df[col] = df[col].apply(extract_hyperlink)

        df['시작 시간'] = df['시작 시간'].apply(parse_korean_datetime)
        df['완료 시간'] = df['완료 시간'].apply(parse_korean_datetime)
        df = df[df['내용'].astype(str).str.strip().notna() & (df['내용'].astype(str).str.strip() != '')]

        if df.empty:
            logger.warning(f"No valid data in WORKSHEET for Spreadsheet ID: {spreadsheet_id} (all contents empty).")
            return pd.DataFrame()

        logger.info(f"WORKSHEET data extracted successfully for Spreadsheet ID: {spreadsheet_id}, rows: {len(df)}")
        return df

    except HttpError as e:
        logger.error(f"Google Sheets API error (WORKSHEET extraction, ID: {spreadsheet_id}): {e}", exc_info=True)
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Unexpected error during WORKSHEET extraction (ID: {spreadsheet_id}): {e}", exc_info=True)
        return pd.DataFrame()

def extract_all_data_for_spreadsheet(spreadsheet_id: str):
    logger.info(f"Extracting all data for single spreadsheet ID: {spreadsheet_id}")
    info_df, additional_info = fetch_info_metadata(spreadsheet_id)
    
    if info_df.empty:
        logger.warning(f"Empty info_df for Spreadsheet ID: {spreadsheet_id}. Skipping.")
        return None, None, None

    worksheet_df = fetch_worksheet_data(spreadsheet_id)
    
    if worksheet_df.empty:
        logger.warning(f"Empty worksheet_df for Spreadsheet ID: {spreadsheet_id}. Skipping.")
        return None, None, None

    logger.info(f"Successfully extracted data for spreadsheet ID: {spreadsheet_id}: info_df {len(info_df)} rows, worksheet_df {len(worksheet_df)} rows.")
    return info_df, worksheet_df, additional_info

def extract_all_data():
    logger.info("Starting extract_all_data process.")
    if not TARGET_SPREADSHEET_ID or not TARGET_SHEET_NAME:
        logger.error("TARGET_SPREADSHEET_ID or TARGET_SHEET_NAME not set. Cannot proceed with data extraction.")
        return []

    try:
        linked_ids = get_linked_spreadsheet_ids(TARGET_SPREADSHEET_ID, TARGET_SHEET_NAME)
    except ValueError as e:
        logger.error(f"Could not find sheet '{TARGET_SHEET_NAME}' to retrieve linked IDs: {e}")
        return []
    except Exception as e:
        logger.error(f"Error retrieving linked spreadsheet IDs: {e}", exc_info=True)
        return []

    if not linked_ids:
        logger.warning(f"No linked spreadsheet IDs found in sheet '{TARGET_SHEET_NAME}'.")
        return []

    if LIMIT > 0:
        logger.info(f"Applying LIMIT: {LIMIT}. Original number of linked IDs: {len(linked_ids)}")
        linked_ids = linked_ids[:LIMIT]
    
    logger.info(f"Processing {len(linked_ids)} linked spreadsheets (LIMIT={LIMIT}, BATCH_SIZE={BATCH_SIZE})")

    all_extracted_data = []
    for i in range(0, len(linked_ids), BATCH_SIZE):
        batch_ids = linked_ids[i:i + BATCH_SIZE]
        logger.info(f"Processing batch #{i//BATCH_SIZE + 1}: {len(batch_ids)} spreadsheet IDs.")
        for spreadsheet_id in batch_ids:
            logger.info(f"Extracting data from spreadsheet ID: {spreadsheet_id}")
            try:
                info_df, worksheet_df, additional_info = extract_all_data_for_spreadsheet(spreadsheet_id)
                
                if info_df is None or worksheet_df is None or additional_info is None:
                    logger.warning(f"No valid data extracted for spreadsheet ID: {spreadsheet_id}. Skipping.")
                    continue
                
                if 'S/N' not in info_df.columns or info_df['S/N'].iloc[0] is None or str(info_df['S/N'].iloc[0]).strip() == "":
                    logger.warning(f"No valid S/N in info data for spreadsheet ID: {spreadsheet_id}. Skipping.")
                    continue

                all_extracted_data.append((info_df, worksheet_df, additional_info))
                logger.info(f"Successfully added data for spreadsheet ID: {spreadsheet_id}")
            except Exception as e:
                logger.error(f"Top-level exception processing spreadsheet ID: {spreadsheet_id}: {e}", exc_info=True)
                continue
    
    logger.info(f"Finished extract_all_data process. Extracted data for {len(all_extracted_data)} spreadsheets.")
    return all_extracted_data

if __name__ == "__main__":
    logger.info("sheet_extractor.py executed directly for testing.")
    results = extract_all_data()
    logger.info(f"Test run: Extracted data for {len(results)} spreadsheets.")
    for idx, (info_df, worksheet_df, additional_info) in enumerate(results):
        logger.debug(f"--- Result #{idx+1} ---")
        logger.debug(f"Info DF head:\n{info_df.head().to_string()}")
        logger.debug(f"Worksheet DF head:\n{worksheet_df.head().to_string()}")
        logger.debug(f"Additional Info: {additional_info}")
        if idx >= 2 and len(results) > 3:
            logger.debug("...(omitting further detailed results for brevity)...")
            break
