# utils/drive_data_extractor.py
"""
구글 드라이브 기반 데이터 추출기
기존 하이퍼링크 방식과 100% 동일한 데이터 구조 반환
"""

import os
import re
import time
import logging
import pandas as pd
from datetime import datetime, timedelta
from googleapiclient.errors import HttpError
from utils.google_api import drive_service, api_call_with_backoff, get_sheets_service
from utils.data_processing_core import parse_korean_datetime
from config.settings import DRIVE_FOLDER_ID

logger = logging.getLogger(__name__)


class DriveDataExtractor:
    def __init__(self, drive_folder_id=DRIVE_FOLDER_ID):
        self.drive_folder_id = drive_folder_id
        self.sn_pattern = re.compile(r"(GB[A-Z]{2}-\d{4})")  # GBWS-1234 형태

    def find_spreadsheets_in_drive(
        self, days_back=30, sn_patterns=None, date_range=None
    ):
        """
        구글 드라이브에서 스프레드시트 파일 검색

        Args:
            days_back: 최근 N일 내 수정된 파일만 검색
            sn_patterns: S/N 패턴 리스트 (예: ['GBWS-', 'GBUS-'])
            date_range: 특정 날짜 범위 (start_date, end_date) 튜플

        Returns:
            list: 검색된 파일 정보 [{id, name, modifiedTime}...]
        """
        # 월 prefix 추출 (기본 검색용 - 전체적인 범위)
        if date_range:
            start_date, end_date = date_range
            # 시작 날짜의 월을 기준으로 검색 (예: 7월 15일~20일 → "2507"로 검색)
            year = str(start_date.year)[2:]  # 25
            month = f"{start_date.month:02d}"  # 07
            month_prefix = year + month  # 2507
        else:
            # 기본값: 현재 월
            now = datetime.now()
            year = str(now.year)[2:]
            month = f"{now.month:02d}"
            month_prefix = year + month

        # 기본 쿼리 (파일명 기준 + 수정시간은 넓은 범위로)
        query = (
            f"'{self.drive_folder_id}' in parents and "
            f"mimeType='application/vnd.google-apps.spreadsheet' and "
            f"name contains '{month_prefix}'"
        )

        logger.info(f"🎯 검색 대상 월: {month_prefix} (파일명 기준)")

        files = []
        page_token = None

        logger.info(f"🔍 드라이브 검색 쿼리: {query}")

        try:
            while True:
                result = api_call_with_backoff(
                    drive_service.files().list,
                    q=query,
                    fields="nextPageToken, files(id, name, modifiedTime)",
                    orderBy="modifiedTime desc",
                    pageSize=100,
                    pageToken=page_token,
                ).execute()

                batch_files = result.get("files", [])
                files.extend(batch_files)

                page_token = result.get("nextPageToken")
                if not page_token:
                    break

                logger.debug(
                    f"페이지 로드: {len(batch_files)}개 파일 추가 (누적: {len(files)}개)"
                )

        except HttpError as e:
            logger.error(f"드라이브 검색 실패: {e}")
            return []

        # 파일명 기준 날짜 필터링 적용
        filtered_files = []
        for file_info in files:
            # 파일명에서 날짜 추출 및 범위 확인
            if date_range and not self.is_file_in_date_range(
                file_info["name"], date_range
            ):
                continue  # 날짜 범위 밖이면 제외

            # 파일명에서 추정 S/N 시도
            estimated_sn = self.extract_sn_from_filename(file_info["name"])
            file_info["estimated_sn"] = estimated_sn  # 추정값, 실제와 다를 수 있음
            filtered_files.append(file_info)

        logger.info(f"🎯 총 {len(filtered_files)}개 스프레드시트 발견 (날짜 필터링 후)")
        return filtered_files

    def extract_sn_from_filename(self, filename):
        """
        파일명에서 S/N 추출 시도 (실제 S/N은 정보판에서 추출)
        """
        # 1. GBWS-1234 형태 직접 매칭
        match = self.sn_pattern.search(filename)
        if match:
            return match.group(1)

        # 2. YYMMDD/Order/SerialNumber 형태 파싱
        parts = filename.split("/")
        if len(parts) == 3:
            yymmdd, order_no, serial_no = parts
            # Serial Number를 임시 S/N으로 사용 (나중에 정보판에서 실제 S/N 추출)
            return f"TMP-{serial_no}"  # 임시 표시

        # 3. 기타 형태는 파일명 자체를 사용
        return f"FILE-{filename.replace('/', '-')}"

    def is_file_in_date_range(self, filename, date_range):
        """
        파일명에서 날짜를 추출하여 지정된 날짜 범위에 포함되는지 확인
        파일명 형태: YYMMDD/order/serial (예: 250730/5919/5939)
        """
        try:
            start_date, end_date = date_range

            # 파일명에서 YYMMDD 부분 추출
            parts = filename.split("/")
            if len(parts) >= 1:
                date_part = parts[0]  # "250730"

                # YYMMDD → YYYY-MM-DD 변환
                if len(date_part) == 6 and date_part.isdigit():
                    year = 2000 + int(date_part[:2])  # 25 → 2025
                    month = int(date_part[2:4])  # 07 → 7
                    day = int(date_part[4:6])  # 30 → 30

                    file_date = datetime(year, month, day)

                    # 날짜 범위 확인
                    return start_date <= file_date <= end_date

            return False  # 파싱 실패 시 제외

        except (ValueError, IndexError) as e:
            logger.debug(f"파일명 날짜 파싱 실패: {filename}, 오류: {e}")
            return False  # 파싱 실패 시 제외

    def fetch_info_metadata_from_drive(self, spreadsheet_id):
        """
        기존 fetch_info_metadata 함수와 100% 동일한 로직
        드라이브 파일에서 정보판 데이터 추출
        """
        logger.info(f"Fetching info metadata for Spreadsheet ID: {spreadsheet_id}")
        try:
            info_range = "정보판!A1:F5"
            result = api_call_with_backoff(
                get_sheets_service().spreadsheets().values().get,
                spreadsheetId=spreadsheet_id,
                range=info_range,
                valueRenderOption="FORMATTED_VALUE",
            ).execute()

            data = result.get("values", [])
            if not data or len(data) < 5:
                logger.warning(
                    f"Insufficient data in info range for Spreadsheet ID: {spreadsheet_id}. Data length: {len(data)}"
                )
                return pd.DataFrame(), {}

            # 기존 로직과 100% 동일한 파싱
            info_dict = {
                "판매오더": data[0][1] if len(data[0]) > 1 else None,
                "고객사": data[0][3] if len(data[0]) > 3 else None,
                "라인": data[0][5] if len(data[0]) > 5 else None,
                "제품코드": data[1][1] if len(data[1]) > 1 else None,
                "MODEL": data[1][3] if len(data[1]) > 3 else None,
                "수량": data[1][5] if len(data[1]) > 5 else None,
                "기구외주": data[2][1] if len(data[2]) > 1 else None,
                "전장외주": data[2][3] if len(data[2]) > 3 else None,
                "모듈외주": data[2][5] if len(data[2]) > 5 else None,
                "제조시작": parse_korean_datetime(
                    data[3][1] if len(data[3]) > 1 else None
                ),
                "제조종료": parse_korean_datetime(
                    data[3][3] if len(data[3]) > 3 else None
                ),
                "S/N": data[3][5] if len(data[3]) > 5 else None,
                "테스트시작": parse_korean_datetime(
                    data[4][1] if len(data[4]) > 1 else None
                ),
                "테스트종료": parse_korean_datetime(
                    data[4][3] if len(data[4]) > 3 else None
                ),
                "반제품시작": parse_korean_datetime(
                    data[4][5] if len(data[4]) > 5 else None
                ),
            }

            logger.debug(f"Info parsed (ID: {spreadsheet_id}): {info_dict}")

            sn = info_dict.get("S/N")
            if not sn:
                logger.warning(
                    f"No S/N found in info data for Spreadsheet ID: {spreadsheet_id}. Skipping."
                )
                return pd.DataFrame(), {}

            # Title number 추출 (기존 로직 유지)
            try:
                title_range = "정보판!B4"
                title_result = api_call_with_backoff(
                    get_sheets_service().spreadsheets().values().get,
                    spreadsheetId=spreadsheet_id,
                    range=title_range,
                    valueRenderOption="FORMATTED_VALUE",
                ).execute()
                title_values = title_result.get("values", [])
                title_number = (
                    title_values[0][0] if title_values and title_values[0] else None
                )
            except Exception as e:
                logger.warning(
                    f"Failed to fetch title number for Spreadsheet ID: {spreadsheet_id}: {e}"
                )
                title_number = None

            model_name_val = info_dict.get("MODEL", "미정")
            if not model_name_val:
                logger.warning(
                    f"No MODEL found for Spreadsheet ID: {spreadsheet_id}, S/N: {sn}. Using '미정'."
                )

            additional_info = {
                "model_name": model_name_val,
                "mech_partner": info_dict.get("기구외주", "미정"),
                "elec_partner": info_dict.get("전장외주", "미정"),
            }

            spreadsheet_link = (
                f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
            )

            # 기존과 100% 동일한 DataFrame 구조
            df_data = {
                "S/N": sn,
                "title number": title_number,
                "Model Name": model_name_val,
                "Mech Partner": additional_info["mech_partner"],
                "Elec Partner": additional_info["elec_partner"],
                "고객사": info_dict.get("고객사"),
                "판매오더": info_dict.get("판매오더"),
                "라인": info_dict.get("라인"),
                "수량": info_dict.get("수량"),
                "제조시작": info_dict.get("제조시작"),
                "제조종료": info_dict.get("제조종료"),
                "테스트시작": info_dict.get("테스트시작"),
                "테스트종료": info_dict.get("테스트종료"),
                "반제품시작": info_dict.get("반제품시작"),
                "모듈외주": info_dict.get("모듈외주"),
                "제품코드": info_dict.get("제품코드"),
                "spreadsheet_link": spreadsheet_link,
            }
            df = pd.DataFrame([df_data])

            logger.info(
                f"Info DataFrame created for Spreadsheet ID: {spreadsheet_id}, S/N: {sn}"
            )
            return df, additional_info

        except HttpError as e:
            logger.error(
                f"Google Sheets API error (info extraction, ID: {spreadsheet_id}): {e}",
                exc_info=True,
            )
            return pd.DataFrame(), {}
        except Exception as e:
            logger.error(
                f"Unexpected error during info extraction (ID: {spreadsheet_id}): {e}",
                exc_info=True,
            )
            return pd.DataFrame(), {}

    def fetch_worksheet_data_from_drive(self, spreadsheet_id):
        """
        기존 fetch_worksheet_data 함수와 100% 동일한 로직
        드라이브 파일에서 Worksheet 데이터 추출
        """
        logger.info(f"Fetching worksheet data for Spreadsheet ID: {spreadsheet_id}")
        try:
            worksheet_range = "Worksheet!A1:G"
            resp_data = api_call_with_backoff(
                get_sheets_service().spreadsheets().values().get,
                spreadsheetId=spreadsheet_id,
                range=worksheet_range,
                valueRenderOption="FORMULA",
            ).execute()

            values = resp_data.get("values", [])
            if not values:
                logger.warning(
                    f"No data found in worksheet range for Spreadsheet ID: {spreadsheet_id}"
                )
                return pd.DataFrame()

            headers = values[0] if values else []
            data_rows = values[1:] if len(values) > 1 else []

            if not data_rows:
                logger.warning(
                    f"No data rows found in worksheet for Spreadsheet ID: {spreadsheet_id}"
                )
                return pd.DataFrame()

            # 기존과 동일한 데이터 정리 로직
            max_cols = max(
                len(headers), max((len(row) for row in data_rows), default=0)
            )

            if max_cols > len(headers):
                headers.extend([""] * (max_cols - len(headers)))

            adjusted_data = []
            for row in data_rows:
                if len(row) < max_cols:
                    row.extend([""] * (max_cols - len(row)))
                adjusted_data.append(row[:max_cols])

            df_raw = pd.DataFrame(adjusted_data, columns=headers[:max_cols])

            # 필요한 컬럼 확인
            needed_cols = ["내용", "시작 시간", "완료 시간", "진행율"]
            missing_cols = [col for col in needed_cols if col not in df_raw.columns]

            if missing_cols:
                logger.warning(
                    f"Missing columns {missing_cols} in worksheet for Spreadsheet ID: {spreadsheet_id}"
                )
                return pd.DataFrame()

            # 기존과 동일한 데이터 처리
            df_use = df_raw[needed_cols].copy()
            df_use["시작 시간"] = df_use["시작 시간"].apply(parse_korean_datetime)
            df_use["완료 시간"] = df_use["완료 시간"].apply(parse_korean_datetime)

            # 진행율 처리
            df_use["진행율"] = (
                df_use["진행율"].astype(str).str.replace("%", "").str.strip()
            )
            df_use["진행율"] = pd.to_numeric(df_use["진행율"], errors="coerce")

            # 빈 내용 제거
            result_df = df_use[
                df_use["내용"].notna() & (df_use["내용"].astype(str).str.strip() != "")
            ]

            logger.info(
                f"Worksheet DataFrame created for Spreadsheet ID: {spreadsheet_id}, Rows: {len(result_df)}"
            )
            return result_df

        except HttpError as e:
            logger.error(
                f"Google Sheets API error (worksheet extraction, ID: {spreadsheet_id}): {e}",
                exc_info=True,
            )
            return pd.DataFrame()
        except Exception as e:
            logger.error(
                f"Unexpected error during worksheet extraction (ID: {spreadsheet_id}): {e}",
                exc_info=True,
            )
            return pd.DataFrame()

    def extract_all_data_for_spreadsheet_from_drive(self, spreadsheet_id):
        """
        기존 sheet_extractor의 extract_all_data_for_spreadsheet 함수를 직접 재사용
        100% 동일한 로직으로 데이터 추출
        """
        logger.info(
            f"Extracting all data for single spreadsheet ID from drive: {spreadsheet_id}"
        )

        # 기존 sheet_extractor 함수 직접 사용
        from utils.sheet_extractor import extract_all_data_for_spreadsheet

        return extract_all_data_for_spreadsheet(spreadsheet_id)

    def extract_all_data_from_drive(self, limit=0, days_back=30, date_range=None):
        """
        드라이브에서 모든 데이터 추출 (기존 extract_all_data 대체)

        Args:
            limit: 처리할 파일 수 제한 (0이면 전체)
            days_back: 최근 N일 내 수정된 파일만 처리
            date_range: 특정 날짜 범위 (start_date, end_date) 튜플

        Returns:
            list: [(info_df, worksheet_df, additional_info), ...] - 기존과 동일한 구조
        """
        logger.info("Starting extract_all_data_from_drive process.")

        if date_range:
            logger.info(
                f"📅 날짜 범위 설정: {date_range[0].strftime('%Y-%m-%d')} ~ {date_range[1].strftime('%Y-%m-%d')}"
            )

        # 1. 드라이브에서 스프레드시트 검색 (S/N 패턴 필터링 제거)
        try:
            drive_files = self.find_spreadsheets_in_drive(
                days_back=days_back,
                sn_patterns=None,  # 패턴 필터링 제거
                date_range=date_range,
            )
        except Exception as e:
            logger.error(f"Error searching drive files: {e}", exc_info=True)
            return []

        if not drive_files:
            logger.warning(f"No spreadsheet files found in drive.")
            return []

        # 2. LIMIT 적용
        if limit > 0:
            logger.info(
                f"Applying LIMIT: {limit}. Original number of files: {len(drive_files)}"
            )
            drive_files = drive_files[:limit]

        logger.info(f"Processing {len(drive_files)} spreadsheet files from drive")

        # 3. 각 파일에서 데이터 추출
        all_extracted_data = []

        for i, file_info in enumerate(drive_files, 1):
            spreadsheet_id = file_info["id"]
            filename = file_info["name"]
            estimated_sn = file_info.get("estimated_sn", "Unknown")

            logger.info(
                f"Processing {i}/{len(drive_files)}: {filename} (추정 S/N: {estimated_sn})"
            )

            try:
                info_df, worksheet_df, additional_info = (
                    self.extract_all_data_for_spreadsheet_from_drive(spreadsheet_id)
                )

                if info_df is None or worksheet_df is None or additional_info is None:
                    logger.warning(
                        f"No valid data extracted for file: {filename}. Skipping."
                    )
                    continue

                # 실제 S/N 확인 (정보판에서 추출됨)
                actual_sn = (
                    info_df["S/N"].iloc[0]
                    if not info_df.empty and "S/N" in info_df.columns
                    else None
                )

                if not actual_sn or str(actual_sn).strip() == "":
                    logger.warning(
                        f"No valid S/N in info data for file: {filename}. Skipping."
                    )
                    continue

                all_extracted_data.append((info_df, worksheet_df, additional_info))
                logger.info(
                    f"✅ Successfully added data for file: {filename} (실제 S/N: {actual_sn})"
                )

                # API 제한 방지
                time.sleep(0.5)

            except Exception as e:
                logger.error(
                    f"❌ Failed to process file {filename}: {e}", exc_info=True
                )
                continue

        logger.info(
            f"Finished extract_all_data_from_drive process. Extracted data for {len(all_extracted_data)} spreadsheets."
        )
        return all_extracted_data


# 기존 함수와의 호환성을 위한 인터페이스
def extract_all_data_from_drive_with_limit(limit=0, days_back=30, date_range=None):
    """
    기존 extract_all_data() 함수와 동일한 인터페이스
    """
    extractor = DriveDataExtractor()
    return extractor.extract_all_data_from_drive(
        limit=limit, days_back=days_back, date_range=date_range
    )


if __name__ == "__main__":
    # 테스트 실행
    logger.info("🧪 Drive Data Extractor 테스트 시작")

    extractor = DriveDataExtractor()

    # 테스트: 최근 7일, 최대 5개 파일
    test_data = extractor.extract_all_data_from_drive(limit=5, days_back=7)

    if test_data:
        logger.info(f"✅ 테스트 성공: {len(test_data)}개 데이터 추출")
        for i, (info_df, worksheet_df, additional_info) in enumerate(test_data, 1):
            sn = info_df["S/N"].iloc[0] if not info_df.empty else "Unknown"
            logger.info(
                f"  {i}. S/N: {sn}, Info: {len(info_df)} rows, Worksheet: {len(worksheet_df)} rows"
            )
    else:
        logger.warning("❌ 테스트 실패: 추출된 데이터가 없음")
