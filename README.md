# BE-staging (Drive-based extractor)

- main_extract.py: 구글 드라이브 기반 추출 + 파일명(YYMMDD) 날짜 필터 지원 (args/env)
- utils/drive_data_extractor.py: 드라이브 파일 검색/파싱/시트 로딩
- utils/json_saver.py: timestamp 보강 및 파일명에 실행일 부여
- main_push_db/main.py: DB 적재 스크립트 (로컬 비밀번호 빈값 허용)

## Date Range 설정 (우선순위: CLI > env)
- CLI: `--month YYYY-MM` 또는 `--start-date YYYY-MM-DD --end-date YYYY-MM-DD`
- ENV: `EXTRACT_TARGET_MONTH=YYYY-MM` 또는 `EXTRACT_START_DATE`, `EXTRACT_END_DATE`

## 주의사항
- 운영/개인 키, `config/credentials.py` 등 민감정보는 커밋하지 않습니다.
- DB 연결/구글 API는 각 환경 Secrets로 설정하세요.
