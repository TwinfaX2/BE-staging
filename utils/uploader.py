# utils/uploader.py

import os
import logging
import requests
import base64
import mimetypes
from googleapiclient.http import MediaFileUpload

from utils.google_api import api_call_with_backoff, drive_service, sheets_service
from config.settings import DRIVE_FOLDER_ID, GITHUB_TOKEN
from utils.logger import setup_logging

# GitHub 설정 (필요시 .env로 관리)
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "isolhsolfafa")
GITHUB_REPO     = os.getenv("GITHUB_REPO", "PDA_Dashboard")
GITHUB_BRANCH   = os.getenv("GITHUB_BRANCH", "main")

# 로깅 초기화 (루트 로거에 설정)
setup_logging()

def upload_to_drive(file_path: str, folder_id: str = DRIVE_FOLDER_ID) -> str | None:
    if not os.path.isfile(file_path):
        logging.error(f"파일이 존재하지 않습니다: {file_path}")
        return None

    mime_type, _ = mimetypes.guess_type(file_path)
    media = MediaFileUpload(file_path, mimetype=mime_type or "application/octet-stream")
    metadata = {"name": os.path.basename(file_path), "parents": [folder_id]}

    try:
        created = api_call_with_backoff(
            drive_service.files().create,
            body=metadata,
            media_body=media,
            fields="id"
        ).execute()
        file_id = created.get("id")
        api_call_with_backoff(
            drive_service.permissions().create,
            fileId=file_id,
            body={"type": "anyone", "role": "reader"}
        ).execute()

        url = f"https://drive.google.com/uc?export=view&id={file_id}"
        logging.info(f"Drive 업로드 완료: {file_path} -> {url}")
        return url

    except Exception as e:
        logging.error(f"[Drive 업로드 오류] {file_path}: {e}")
        return None


def upload_to_github(file_path: str) -> bool:
    if not GITHUB_TOKEN:
        logging.error("GitHub 토큰이 설정되지 않았습니다.")
        return False
    if not os.path.isfile(file_path):
        logging.error(f"파일이 존재하지 않습니다: {file_path}")
        return False

    try:
        with open(file_path, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        file_name = os.path.basename(file_path)
        url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{file_name}"
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }

        resp = requests.get(url, headers=headers)
        sha = resp.json().get("sha") if resp.status_code == 200 else None

        data = {
            "message": f"자동 업로드: {file_name}",
            "content": content,
            "branch": GITHUB_BRANCH
        }
        if sha:
            data["sha"] = sha

        put_resp = requests.put(url, headers=headers, json=data)
        if put_resp.status_code in (200, 201):
            logging.info(f"GitHub 업로드 성공: {file_name}")
            return True
        else:
            logging.error(f"GitHub 업로드 실패 ({put_resp.status_code}): {put_resp.text}")
            return False

    except Exception as e:
        logging.error(f"[GitHub 업로드 오류] {file_path}: {e}")
        return False


def _batch_update(spreadsheet_id: str, requests_list: list[dict]) -> None:
    if not requests_list:
        return
    api_call_with_backoff(
        sheets_service.spreadsheets().batchUpdate,
        spreadsheetId=spreadsheet_id,
        body={"requests": requests_list}
    ).execute()


def update_spreadsheet_with_product_name(
    spreadsheet_id: str,
    order_no: str,
    product_name: str,
    sheet_values: list[list[str]],
    target_sheet_id: int
) -> None:
    if not product_name or product_name == "NoValue":
        logging.warning(f"제품명이 비어 있습니다 (Order: {order_no})")
        return
    if not sheet_values:
        logging.error("스프레드시트 데이터가 없습니다.")
        return

    reqs = []
    for idx, row in enumerate(sheet_values[1:], start=2):
        if row and row[0].strip().lower() == order_no.strip().lower():
            reqs.append({
                "updateCells": {
                    "range": {
                        "sheetId": target_sheet_id,
                        "startRowIndex": idx-1,
                        "endRowIndex": idx,
                        "startColumnIndex": 3,
                        "endColumnIndex": 4
                    },
                    "rows": [{"values": [{"userEnteredValue": {"stringValue": product_name}}]}],
                    "fields": "userEnteredValue"
                }
            })
    _batch_update(spreadsheet_id, reqs)
    if reqs:
        logging.info(f"Order '{order_no}' 제품명 업데이트 완료: {product_name}")


def update_spreadsheet_with_total_time(
    spreadsheet_id: str,
    order_no: str,
    total_time: str,
    sheet_values: list[list[str]],
    target_sheet_id: int
) -> None:
    if not sheet_values:
        logging.error("스프레드시트 데이터가 없습니다.")
        return

    reqs = []
    for idx, row in enumerate(sheet_values[1:], start=2):
        if row and row[0].strip().lower() == order_no.strip().lower():
            reqs.append({
                "updateCells": {
                    "range": {
                        "sheetId": target_sheet_id,
                        "startRowIndex": idx-1,
                        "endRowIndex": idx,
                        "startColumnIndex": 22,
                        "endColumnIndex": 23
                    },
                    "rows": [{"values": [{"userEnteredValue": {"stringValue": total_time}}]}],
                    "fields": "userEnteredValue"
                }
            })
    _batch_update(spreadsheet_id, reqs)
    if reqs:
        logging.info(f"Order '{order_no}' 총 소요시간 업데이트 완료: {total_time}")


def update_spreadsheet_with_category_time(
    spreadsheet_id: str,
    order_no: str,
    category: str,
    time_value: str,
    sheet_values: list[list[str]],
    target_sheet_id: int,
    column_index: int
) -> None:
    if not sheet_values:
        logging.error("스프레드시트 데이터가 없습니다.")
        return

    reqs = []
    for idx, row in enumerate(sheet_values[1:], start=2):
        if row and row[0].strip().lower() == order_no.strip().lower():
            reqs.append({
                "updateCells": {
                    "range": {
                        "sheetId": target_sheet_id,
                        "startRowIndex": idx-1,
                        "endRowIndex": idx,
                        "startColumnIndex": column_index,
                        "endColumnIndex": column_index+1
                    },
                    "rows": [{"values": [{"userEnteredValue": {"stringValue": time_value}}]}],
                    "fields": "userEnteredValue"
                }
            })
    _batch_update(spreadsheet_id, reqs)
    if reqs:
        logging.info(f"Order '{order_no}' {category} 소요시간 업데이트 완료: {time_value}")


def update_spreadsheet_with_graph_link(
    spreadsheet_id: str,
    order_no: str,
    link: str | None,
    sheet_values: list[list[str]],
    target_sheet_id: int,
    column_index: int,
    label: str
) -> str | None:
    if not link:
        return None
    if not sheet_values:
        logging.error("스프레드시트 데이터가 없습니다.")
        return link

    formula = f'=HYPERLINK("{link}", "{label}")'
    reqs = []
    for idx, row in enumerate(sheet_values[1:], start=2):
        if row and row[0].strip().lower() == order_no.strip().lower():
            reqs.append({
                "updateCells": {
                    "range": {
                        "sheetId": target_sheet_id,
                        "startRowIndex": idx-1,
                        "endRowIndex": idx,
                        "startColumnIndex": column_index,
                        "endColumnIndex": column_index+1
                    },
                    "rows": [{"values": [{"userEnteredValue": {"stringValue": formula}}]}],
                    "fields": "userEnteredValue"
                }
            })
    _batch_update(spreadsheet_id, reqs)
    if reqs:
        logging.info(f"Order '{order_no}' {label} 링크 업데이트 완료")
    return link