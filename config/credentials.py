import os, logging
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SCOPES_SHEETS = ["https://www.googleapis.com/auth/spreadsheets"]
SCOPES_DRIVE = ["https://www.googleapis.com/auth/drive"]


def _load_service_account(path, scopes):
    if not path or not os.path.isfile(path):
        msg = f"Service account key not found: {path}"
        logging.error(msg)
        raise FileNotFoundError(msg)
    return Credentials.from_service_account_file(path, scopes=scopes)


_sheets_service = None
_drive_service = None


def get_sheets_credentials():
    if os.getenv("RAILWAY_ENVIRONMENT"):
        key_path = "config/gst-manegemnet-70faf8ce1bff.json"
    else:
        key_path = os.getenv(
            "SHEETS_JSON_KEY_PATH", "config/gst-manegemnet-70faf8ce1bff.json"
        )
    return _load_service_account(key_path, SCOPES_SHEETS)


def get_drive_credentials():
    if os.getenv("RAILWAY_ENVIRONMENT"):
        key_path = "config/gst-manegemnet-ab8788a05cff.json"
    else:
        key_path = os.getenv(
            "DRIVE_JSON_KEY_PATH", "config/gst-manegemnet-ab8788a05cff.json"
        )
    return _load_service_account(key_path, SCOPES_DRIVE)


def get_sheets_service():
    global _sheets_service
    if _sheets_service is None:
        _sheets_service = build(
            "sheets", "v4", credentials=get_sheets_credentials(), cache_discovery=False
        )
    return _sheets_service


def get_drive_service():
    global _drive_service
    if _drive_service is None:
        _drive_service = build(
            "drive", "v3", credentials=get_drive_credentials(), cache_discovery=False
        )
    return _drive_service
