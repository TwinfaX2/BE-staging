# BE-staging (Complete Backend for Data Pipeline Testing)

## 🎯 Purpose
클라우드 환경에서 구글 드라이브 → PostgreSQL 데이터 파이프라인을 안전하게 테스트하기 위한 스테이징 백엔드

## 📁 Structure
```
├── main_extract.py              # 구글 드라이브 기반 데이터 추출 (날짜 필터링 포함)
├── main_push_db/
│   └── main.py                  # PostgreSQL 데이터 적재
├── config/
│   ├── settings.py              # 환경 설정 (SPREADSHEET_ID, TOLERANCE 등)
│   └── credentials.py           # Google API 인증 서비스
├── utils/
│   ├── drive_data_extractor.py  # 드라이브 파일 검색/추출 (YYMMDD 필터링)
│   ├── data_processing_core.py  # 데이터 처리 핵심 로직
│   ├── data_processing.py       # 평균 시간 매핑
│   ├── visualization.py         # 차트 생성/업로드
│   ├── google_api.py           # API 호출 백오프
│   ├── json_saver.py           # JSON 저장 (timestamp 처리)
│   └── load_json_to_postgres.py # DB 적재 (NaT→NULL 변환)
└── requirements.txt
```

## 🚀 Usage
### 1. 데이터 추출
```bash
# 특정 월 추출
python main_extract.py --month 2025-07

# 날짜 범위 추출  
python main_extract.py --start-date 2025-07-30 --end-date 2025-07-31

# 환경변수 방식 (CI/CD용)
EXTRACT_TARGET_MONTH=2025-07 python main_extract.py
```

### 2. DB 적재
```bash
python main_push_db/main.py output/result_20250805.json
```

## 🔧 Environment Variables
### 필수 설정
```bash
# Google API
GOOGLE_CREDENTIALS_JSON=<서비스계정JSON>
DRIVE_FOLDER_ID=<드라이브폴더ID>
SPREADSHEET_ID=<메타데이터시트ID>

# Database
DB_HOST=<호스트>
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=<비밀번호>
DB_NAME=railway

# 추출 옵션
EXTRACT_TARGET_MONTH=2025-07        # 월 단위 (권장)
# 또는
EXTRACT_START_DATE=2025-07-30       # 정확한 날짜 범위
EXTRACT_END_DATE=2025-07-31

# 처리 옵션  
TOLERANCE=1.5
BATCH_SIZE=10
```

## 📊 Expected Output
- JSON 파일: `output/result_YYYYMMDD.json`
- DB 테이블: `documents`, `info`, `worksheet`, `task_summary`, `progress_summary`, `stats`, `partner_stats`, `additional_info`, `treemap_data`

## ✅ 검증 방법
1. 로그에서 추출된 스프레드시트 수량 확인
2. pgAdmin에서 `info` 테이블 레코드 수 확인  
3. `progress_summary`, `task_summary` 데이터 무결성 확인
