# config/settings.py

import os
from dotenv import load_dotenv
from datetime import date, time

# ✅ Railway에서는 load_dotenv() 생략 (로컬일 때만 로드)
if os.getenv("RAILWAY_ENVIRONMENT") != "true":
    load_dotenv()

# 이후는 그대로 유지
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")


# 2) 환경변수 파싱 헬퍼
def _bool(env_value: str, default=False) -> bool:
    return (
        str(env_value or "").lower() in ("1", "true", "yes")
        if env_value is not None
        else default
    )


def _int(env_value: str, default=0) -> int:
    try:
        return int(env_value)
    except (TypeError, ValueError):
        return default


if os.getenv("RAILWAY_ENVIRONMENT") == "true":
    FONT_PATHS = ["/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]
else:
    FONT_PATHS = [
        "/Users/kdkyu311/Library/Fonts/NanumGothic.ttf",
        "/System/Library/AssetsV2/com_apple_MobileAsset_Font7/bad9b4bf17cf1669dde54184ba4431c22dcad27b.asset/AssetData/NanumGothic.ttc",
        "/Library/Fonts/NanumGothic.ttf",
        "/System/Library/Fonts/Supplemental/NanumGothic.ttf",
    ]
# 3) 실행 모드 및 처리량 설정
TEST_MODE = _bool(os.getenv("TEST_MODE"), default=False)
LIMIT = _int(os.getenv("LIMIT"), default=1)
BATCH_SIZE = _int(os.getenv("BATCH_SIZE"), default=10)

# 4) Google API 및 스프레드시트
SPREADSHEET_ID = os.getenv(
    "SPREADSHEET_ID", "19dkwKNW6VshCg3wTemzmbbQlbATfq6brAWluaps1Rm0"
)
DRIVE_FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "1Gylm36vhtrl_yCHurZYGgeMlt5U0CliE")
DRIVE_FOLDER_ID_JSON_DB = os.getenv(
    "DRIVE_FOLDER_ID_JSON_DB", "1lnaXdljTfaVLFwykSJSvWbWZ-rFlGN-a"
)
TARGET_SHEET_NAME = os.getenv("TARGET_SHEET_NAME", "월생산물량")
AVG_TIME_SPREADSHEET_ID = os.getenv(
    "AVG_TIME_SPREADSHEET_ID", "1PHKsQ-3kcyaB9HdJqdaLN4siqnHRE8FC7XzGR2pmoLc"
)

# 5) 그래프 생성 요일 목록 (0=월,1=화,…6=일)
raw_days = os.getenv("GRAPH_DAYS", "0,4").split(",")
GRAPH_DAYS = sorted(
    {_int(d.strip(), default=None) for d in raw_days if d.strip().isdigit()}
)

# 6) 이메일 설정
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = _int(os.getenv("SMTP_PORT"), 587)
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "angdredong@gmail.com")
EMAIL_PASS = os.getenv("EMAIL_PASS", "")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL", "kdkyu311@naver.com")

# 7) 카카오톡 API
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
KAKAO_REFRESH_TOKEN = os.getenv("KAKAO_REFRESH_TOKEN", "")

# 8) GitHub
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# 9) 휴일 및 근무 시간
HOLIDAYS = [
    date(2025, 1, 1),
    date(2025, 1, 27),
    date(2025, 1, 28),
    date(2025, 1, 29),
    date(2025, 3, 1),
    date(2025, 5, 5),
    date(2025, 5, 6),
    date(2025, 6, 6),
    date(2025, 8, 15),
    date(2025, 10, 3),
    date(2025, 10, 6),
    date(2025, 10, 7),
    date(2025, 10, 8),
    date(2025, 10, 9),
    date(2025, 12, 25),
]
WORK_START = time(8, 0)
WORK_END = time(20, 0)
MAX_DAILY_HOURS = 12
LUNCH_START, LUNCH_END = time(11, 20), time(12, 20)
DINNER_START, DINNER_END = time(17, 0), time(18, 0)
BREAK_1_START, BREAK_1_END = time(10, 0), time(10, 20)
BREAK_2_START, BREAK_2_END = time(15, 0), time(15, 20)

# 10) 대시보드 모드
DASHBOARD_MODE = os.getenv("DASHBOARD_MODE", "partner")

# OT 허용 범위 설정 (시간 단위)
TOLERANCE = 2  # ±1시간
