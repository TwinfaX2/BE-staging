# utils/google_api.py

import os
import re
import logging
from backoff import on_exception, expo
from googleapiclient.discovery import build # build는 현재 코드에서 직접 사용되지 않음 (필요시 유지)
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from config.credentials import get_sheets_service, get_drive_service # 경로 확인 필요
from config.settings import DRIVE_FOLDER_ID # 경로 확인 필요

# 이 모듈의 로거를 가져옵니다. 실제 설정은 이 모듈을 import하는 스크립트에서 담당.
logger = logging.getLogger(__name__)

# sheets_service와 drive_service는 최초 호출 시 생성되도록 변경하는 것을 고려할 수 있으나,
# 현재는 모듈 로드 시점에 생성하는 것으로 유지합니다. (config.credentials 내부 구현에 따라 다름)
try:
    sheets_service = get_sheets_service()
    drive_service  = get_drive_service()
    logger.info("Google Sheets and Drive services initialized via google_api.py.")
except Exception as e:
    logger.critical(f"Failed to initialize Google services in google_api.py: {e}", exc_info=True)
    # 서비스 초기화 실패 시, 이후 함수 호출에서 문제가 발생하므로,
    # 필요하다면 여기서 sheets_service=None 등으로 설정하고 각 함수에서 확인하도록 할 수 있음.
    # 또는, 프로그램 시작 시점에 확인하고 종료하도록 하는 것이 더 나을 수 있음.
    sheets_service = None 
    drive_service = None


@on_exception(expo, HttpError, max_tries=8, max_time=120,
              giveup=lambda e: getattr(e, 'status_code', None) not in [429, 503])
def api_call_with_backoff(func, *args, **kwargs):
    """
    Exponential Backoff를 적용한 Google API 호출 함수.
    지정된 HTTP 오류 발생 시 재시도를 수행합니다.
    """
    if func is None: # 서비스 초기화 실패 시 func이 None일 수 있음
        raise ConnectionError("Google API service is not initialized.")
    try:
        return func(*args, **kwargs)
    except HttpError as e:
        logger.warning(f"API call failed (will retry if applicable): {e}")
        raise

def fetch_entire_sheet_values(spreadsheet_id, sheet_range):
    """
    주어진 스프레드시트와 범위에서 전체 데이터를 한 번에 가져옵니다.
    """
    logger.debug(f"Fetching entire sheet values for ID: {spreadsheet_id}, Range: {sheet_range}")
    result = api_call_with_backoff(
        sheets_service.spreadsheets().values().get,
        spreadsheetId=spreadsheet_id,
        range=sheet_range
    ).execute()
    values = result.get("values", [])
    logger.debug(f"Fetched {len(values)} rows.")
    return values

def get_sheet_id_by_name(spreadsheet_id, sheet_name):
    """
    스프레드시트의 metadata를 조회하여, 지정한 시트 이름에 해당하는 sheetId를 반환합니다.
    """
    logger.debug(f"Getting sheetId for sheet name: '{sheet_name}' in spreadsheet: {spreadsheet_id}")
    metadata = api_call_with_backoff(
        sheets_service.spreadsheets().get,
        spreadsheetId=spreadsheet_id,
        fields="sheets(properties(sheetId,title))" # 필요한 필드만 요청
    ).execute()
    for sheet in metadata.get("sheets", []):
        if sheet.get("properties", {}).get("title") == sheet_name:
            sheet_id = sheet["properties"]["sheetId"]
            logger.debug(f"Found sheetId: {sheet_id} for sheet name: '{sheet_name}'")
            return sheet_id
    logger.error(f"Sheet '{sheet_name}' not found in spreadsheet: {spreadsheet_id}")
    raise ValueError(f"시트 '{sheet_name}'을(를) 찾을 수 없습니다: {spreadsheet_id}")

def get_spreadsheet_title(spreadsheet_id: str) -> str | None:
    """
    스프레드시트의 제목을 가져옵니다.
    성공 시 제목 문자열, 실패 시 None을 반환합니다.
    """
    logger.debug(f"Attempting to fetch title for spreadsheet ID: {spreadsheet_id}")
    if not sheets_service: # 서비스 초기화 실패 대응
        logger.error("Sheets service not available for get_spreadsheet_title.")
        return None
    try:
        spreadsheet_metadata = api_call_with_backoff(
            sheets_service.spreadsheets().get,
            spreadsheetId=spreadsheet_id,
            fields="properties/title"  # 제목 속성만 요청
        ).execute()
        
        title = spreadsheet_metadata.get("properties", {}).get("title")
        
        if title and isinstance(title, str) and title.strip():
            logger.info(f"Successfully fetched title for spreadsheet ID '{spreadsheet_id}': '{title}'")
            return title.strip()
        else:
            logger.warning(f"Spreadsheet title is empty or not found for ID '{spreadsheet_id}'. API response: {spreadsheet_metadata}")
            return None
    except HttpError as http_err:
        logger.error(f"Google Sheets API HTTP error while fetching title for ID '{spreadsheet_id}': {http_err}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error while fetching title for ID '{spreadsheet_id}': {e}", exc_info=True)
        return None
    
def get_order_no(spreadsheet_id: str) -> str | None:
    """
    스프레드시트 제목을 가져와서 "날짜/주문번호/SN" 형식인지 검증 후 반환합니다.
    유효하지 않거나 가져오기 실패 시 None을 반환합니다.
    """
    title = get_spreadsheet_title(spreadsheet_id)
    
    if title is None:
        # get_spreadsheet_title 내부에서 이미 로깅했으므로 여기서는 추가 로깅 불필요
        return None 

    # "YYMMDD/OrderNo/SN" 형식 검증 (예: 250507/5575/5604)
    # \d{6} : 숫자 6개 (YYMMDD)
    # \d{4} : 숫자 4개 (Order No, SN)
    # YYMMDD / 4‑digit Order No / 4‑digit SN
    if re.match(r"^\d{6}/\d{4}/\d{4}$", title):
        logger.info(f"Valid title format for get_order_no (ID: {spreadsheet_id}): '{title}'")
        return title
    else:
        logger.warning(f"Fetched spreadsheet title '{title}' (ID: {spreadsheet_id}) does not match expected 'Date/Order/SN' format.")
        return None # 형식이 맞지 않으면 None 반환

def upload_to_drive(file_path, folder_id=DRIVE_FOLDER_ID):
    """
    지정한 파일을 Google Drive에 업로드하고, 외부에서 접근 가능한 공개 URL을 반환합니다.
    """
    logger.info(f"Attempting to upload '{file_path}' to Drive folder ID: {folder_id}")
    if not drive_service: # 서비스 초기화 실패 대응
        logger.error("Drive service not available for upload_to_drive.")
        return None
    if not folder_id:
        logger.error("DRIVE_FOLDER_ID is not set. Cannot upload to Drive.")
        return None

    try:
        file_name = os.path.basename(file_path)
        file_metadata = {'name': file_name, 'parents': [folder_id]}
        
        mime_type = 'application/octet-stream' # 기본값
        if file_path.endswith('.json'):
            mime_type = 'application/json'
        elif file_path.endswith('.html'):
            mime_type = 'text/html'
        elif file_path.endswith('.png'):
            mime_type = 'image/png'
        
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True) # resumable 추가
        
        file_resource = api_call_with_backoff(
            drive_service.files().create,
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        file_id = file_resource.get('id')
        if not file_id:
            logger.error(f"Failed to get file_id after Drive upload for '{file_path}'.")
            return None

        logger.info(f"File '{file_name}' uploaded to Drive with ID: {file_id}. Setting permissions.")
        # 파일 권한을 'anyone' 읽기 가능으로 설정
        api_call_with_backoff(
            drive_service.permissions().create,
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()
        
        public_url = f"https://drive.google.com/uc?export=view&id={file_id}"
        logger.info(f"Drive upload successful: '{file_path}' -> {public_url}")
        return public_url
    except HttpError as http_err:
        logger.error(f"Google Drive API HTTP error during upload of '{file_path}': {http_err}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during Drive upload of '{file_path}': {e}", exc_info=True)
        return None

def batch_update_spreadsheet(spreadsheet_id, requests_body): # 변수명 requests -> requests_body (Python 키워드와 충돌 방지)
    """
    주어진 스프레드시트에 대해 Batch Update 요청을 수행합니다.
    requests_body는 [{"updateOneSheet": {...}}, ...] 형태의 리스트여야 합니다.
    """
    if not sheets_service: # 서비스 초기화 실패 대응
        logger.error("Sheets service not available for batch_update_spreadsheet.")
        return
    logger.debug(f"Batch updating spreadsheet ID: {spreadsheet_id} with {len(requests_body)} requests.")
    body = {"requests": requests_body}
    api_call_with_backoff(
        sheets_service.spreadsheets().batchUpdate,
        spreadsheetId=spreadsheet_id,
        body=body
    ).execute()
    logger.info(f"Successfully batch updated spreadsheet ID: {spreadsheet_id}")


def get_linked_spreadsheet_ids(spreadsheet_id, sheet_name):
    """
    지정한 시트의 A열에서 HYPERLINK 함수로 연결된 스프레드시트 ID들을 추출합니다.
    """
    logger.debug(f"Getting linked spreadsheet IDs from '{sheet_name}'!A:A in spreadsheet: {spreadsheet_id}")
    pmmd_hyperlink_range = f"'{sheet_name}'!A:A" # 시트 이름에 공백이나 특수문자 있어도 처리
    
    try:
        result = api_call_with_backoff(
            sheets_service.spreadsheets().values().get,
            spreadsheetId=spreadsheet_id,
            range=pmmd_hyperlink_range,
            valueRenderOption="FORMULA" # 수식 자체를 가져옴
        ).execute()
    except Exception as e: # API 호출 자체의 실패
        logger.error(f"Failed to fetch formulas from sheet '{sheet_name}' in spreadsheet '{spreadsheet_id}': {e}", exc_info=True)
        return []

    formulas = result.get("values", [])
    ids = []
    if not formulas:
        logger.warning(f"No formulas found in range '{pmmd_hyperlink_range}' for spreadsheet '{spreadsheet_id}'.")
        return ids

    for row_idx, row_data in enumerate(formulas):
        if not row_data: # 빈 행일 수 있음
            continue
        for cell_formula in row_data:
            if isinstance(cell_formula, str) and cell_formula.upper().startswith("=HYPERLINK("):
                # Google Sheets URL에서 스프레드시트 ID 추출하는 정규식
                # 예: =HYPERLINK("https://docs.google.com/spreadsheets/d/1bYkVAUDaW.../edit", "Link Text")
                match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', cell_formula)
                if match:
                    ids.append(match.group(1))
                else:
                    logger.warning(f"Could not parse spreadsheet ID from HYPERLINK formula in '{spreadsheet_id}' sheet '{sheet_name}', row {row_idx+1}: '{cell_formula}'")
            # else: # HYPERLINK가 아닌 셀은 무시 (로깅 필요시 추가)
            #    logger.debug(f"Cell in '{spreadsheet_id}' sheet '{sheet_name}', row {row_idx+1} is not a HYPERLINK: '{cell_formula}'")

    logger.info(f"Found {len(ids)} linked spreadsheet IDs from '{spreadsheet_id}' sheet '{sheet_name}'.")
    return ids
