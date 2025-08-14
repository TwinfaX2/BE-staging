"""
JSON 추출 단계 중복 확인 시스템
DB 기반으로 이미 처리된 S/N을 확인하여 불필요한 추출을 방지
"""

import logging
import psycopg2
from typing import Dict, Any, Optional, List, Set
from datetime import datetime
from utils.load_json_to_postgres import connect_to_db

logger = logging.getLogger(__name__)


class ExtractionDuplicateChecker:
    """JSON 추출 단계에서 중복 확인"""

    def __init__(self):
        """DB 연결 초기화"""
        try:
            self.conn = connect_to_db()
            logger.info("✅ ExtractionDuplicateChecker: DB 연결 성공")
        except Exception as e:
            logger.error(f"❌ ExtractionDuplicateChecker: DB 연결 실패: {e}")
            self.conn = None

    def get_existing_sns_from_db(self, date_range=None) -> Set[str]:
        """
        DB에서 이미 존재하는 S/N 목록 조회
        
        Args:
            date_range: 특정 날짜 범위 (start_date, end_date) 튜플
            
        Returns:
            set: 이미 DB에 존재하는 S/N 집합
        """
        if not self.conn:
            logger.warning("DB 연결이 없어 중복 확인을 건너뜁니다.")
            return set()

        try:
            cursor = self.conn.cursor()
            
            # 기본 쿼리: 모든 S/N 조회
            base_query = """
                SELECT DISTINCT i.serial_number 
                FROM info i 
                JOIN documents d ON i.document_id = d.document_id
                WHERE i.serial_number IS NOT NULL 
                AND i.serial_number != ''
            """
            
            params = []
            
            # 날짜 범위가 있으면 필터링 추가
            if date_range:
                start_date, end_date = date_range
                base_query += " AND d.execution_date BETWEEN %s AND %s"
                params.extend([start_date.date(), end_date.date()])
            
            cursor.execute(base_query, params)
            results = cursor.fetchall()
            
            existing_sns = {row[0] for row in results if row[0]}
            
            logger.info(f"📊 DB에서 조회된 기존 S/N 개수: {len(existing_sns)}개")
            if date_range:
                logger.info(f"   날짜 범위: {date_range[0].strftime('%Y-%m-%d')} ~ {date_range[1].strftime('%Y-%m-%d')}")
            
            return existing_sns
            
        except Exception as e:
            logger.error(f"❌ 기존 S/N 조회 실패: {e}")
            return set()

    def check_sn_needs_extraction(self, sn: str, existing_sns: Set[str]) -> bool:
        """
        특정 S/N이 추출이 필요한지 확인
        
        Args:
            sn: 확인할 S/N
            existing_sns: 이미 존재하는 S/N 집합
            
        Returns:
            bool: True면 추출 필요, False면 건너뛰기
        """
        if not sn or sn.strip() == "":
            return False
            
        needs_extraction = sn not in existing_sns
        
        if needs_extraction:
            logger.debug(f"🆕 새로운 S/N 감지: {sn} (추출 필요)")
        else:
            logger.debug(f"⚪ 기존 S/N: {sn} (추출 건너뛰기)")
            
        return needs_extraction

    def filter_files_for_extraction(self, drive_files: List[Dict], date_range=None) -> List[Dict]:
        """
        드라이브 파일 목록에서 추출이 필요한 파일만 필터링
        
        Args:
            drive_files: 드라이브에서 검색된 파일 목록
            date_range: 날짜 범위
            
        Returns:
            list: 추출이 필요한 파일 목록
        """
        if not self.conn:
            logger.warning("DB 연결이 없어 모든 파일을 추출 대상으로 설정합니다.")
            return drive_files

        # 기존 S/N 목록 조회
        existing_sns = self.get_existing_sns_from_db(date_range)
        
        filtered_files = []
        skipped_count = 0
        
        for file_info in drive_files:
            # 파일명에서 S/N 추정
            estimated_sn = file_info.get("estimated_sn")
            
            if not estimated_sn:
                # S/N을 추정할 수 없으면 추출 진행
                filtered_files.append(file_info)
                continue
            
            if self.check_sn_needs_extraction(estimated_sn, existing_sns):
                filtered_files.append(file_info)
            else:
                skipped_count += 1
                logger.info(f"⏭️ 중복으로 인한 건너뛰기: {file_info['name']} (S/N: {estimated_sn})")
        
        logger.info(f"📊 파일 필터링 결과:")
        logger.info(f"   - 전체 파일: {len(drive_files)}개")
        logger.info(f"   - 추출 대상: {len(filtered_files)}개")
        logger.info(f"   - 건너뛴 파일: {skipped_count}개")
        logger.info(f"   - 효율성: {(skipped_count/len(drive_files)*100):.1f}% 절약")
        
        return filtered_files

    def get_extraction_summary(self, extracted_sns: List[str], date_range=None) -> Dict[str, Any]:
        """
        추출 결과 요약 정보 생성
        
        Args:
            extracted_sns: 실제로 추출된 S/N 목록
            date_range: 날짜 범위
            
        Returns:
            dict: 추출 요약 정보
        """
        if not self.conn:
            return {
                "total_extracted": len(extracted_sns),
                "db_connection": False,
                "summary": "DB 연결 없이 추출 완료"
            }

        existing_sns = self.get_existing_sns_from_db(date_range)
        
        new_sns = set(extracted_sns) - existing_sns
        duplicate_sns = set(extracted_sns) & existing_sns
        
        summary = {
            "total_extracted": len(extracted_sns),
            "new_sns_count": len(new_sns),
            "duplicate_sns_count": len(duplicate_sns),
            "existing_in_db": len(existing_sns),
            "db_connection": True,
            "efficiency_rate": f"{(len(new_sns)/len(extracted_sns)*100):.1f}%" if extracted_sns else "0%",
            "new_sns_list": list(new_sns)[:10],  # 처음 10개만
            "duplicate_sns_list": list(duplicate_sns)[:5]  # 처음 5개만
        }
        
        return summary

    def close(self):
        """DB 연결 종료"""
        if self.conn:
            self.conn.close()
            logger.info("✅ ExtractionDuplicateChecker: DB 연결 종료")


# 편의 함수들
def create_extraction_checker() -> ExtractionDuplicateChecker:
    """ExtractionDuplicateChecker 인스턴스 생성"""
    return ExtractionDuplicateChecker()


def filter_drive_files_for_extraction(drive_files: List[Dict], date_range=None) -> List[Dict]:
    """
    드라이브 파일 목록 필터링 (편의 함수)
    
    Args:
        drive_files: 드라이브 파일 목록
        date_range: 날짜 범위
        
    Returns:
        list: 필터링된 파일 목록
    """
    checker = create_extraction_checker()
    try:
        return checker.filter_files_for_extraction(drive_files, date_range)
    finally:
        checker.close()


if __name__ == "__main__":
    # 테스트 실행
    logging.basicConfig(level=logging.INFO)
    
    checker = create_extraction_checker()
    
    try:
        # 테스트: 7월 데이터 기존 S/N 조회
        from datetime import datetime
        july_range = (datetime(2025, 7, 1), datetime(2025, 7, 31))
        
        existing_sns = checker.get_existing_sns_from_db(july_range)
        print(f"✅ 7월 기존 S/N: {len(existing_sns)}개")
        
        # 샘플 출력
        sample_sns = list(existing_sns)[:10]
        for i, sn in enumerate(sample_sns, 1):
            print(f"  {i}. {sn}")
            
    finally:
        checker.close()

