"""
DB 기준 Progress 변동 감지 시스템
실제 DB 데이터와 새로운 JSON 데이터를 직접 비교하여 변동을 감지
스냅샷에 의존하지 않고 실시간 소스 변경사항을 정확히 반영
"""

import hashlib
import json
import psycopg2
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class DBBasedChangeDetector:
    """DB 실제 데이터 기준 변동 감지"""

    def __init__(self, conn):
        """
        Args:
            conn: PostgreSQL 데이터베이스 연결 객체
        """
        self.conn = conn

    def get_current_db_progress(self, serial_number: str) -> Optional[Dict[str, float]]:
        """
        DB에서 현재 Progress 데이터 조회

        Args:
            serial_number: S/N

        Returns:
            dict or None: 현재 DB의 Progress 데이터 또는 None
        """
        try:
            cursor = self.conn.cursor()

            cursor.execute(
                """
                SELECT ps.category, ps.progress
                FROM progress_summary ps
                JOIN info i ON ps.document_id = i.document_id
                WHERE i.serial_number = %s
                ORDER BY ps.category
            """,
                (serial_number,),
            )

            results = cursor.fetchall()
            cursor.close()

            if not results:
                logger.debug(f"🆕 DB에 {serial_number} 데이터가 없음 - 새로운 S/N")
                return None

            # Progress 딕셔너리 생성
            progress_dict = {}
            for category, progress in results:
                progress_dict[category] = float(progress)

            logger.debug(f"📊 DB Progress for {serial_number}: {progress_dict}")
            return progress_dict

        except Exception as e:
            logger.error(f"❌ DB Progress 조회 실패 (S/N: {serial_number}): {e}")
            raise

    def has_progress_changed_vs_db(
        self, serial_number: str, new_progress_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[Dict], Dict]:
        """
        새로운 Progress 데이터와 DB 현재 데이터 비교

        Args:
            serial_number: S/N
            new_progress_data: 새로운 Progress 데이터 (JSON에서 추출)

        Returns:
            tuple: (변동여부, DB현재Progress, 새Progress)
        """
        try:
            # 새로운 데이터의 progress_summary 추출
            if "progress_summary" in new_progress_data:
                new_progress = new_progress_data["progress_summary"]
            else:
                new_progress = new_progress_data

            # DB 현재 Progress 조회
            current_db_progress = self.get_current_db_progress(serial_number)

            if current_db_progress is None:
                # DB에 데이터가 없으면 새로운 데이터로 간주
                logger.info(f"🆕 새로운 S/N 감지: {serial_number}")
                return True, None, new_progress

            # Progress 값 비교 (소수점 차이 허용)
            has_changes = False
            tolerance = 0.01  # 1% 허용 오차

            # 모든 카테고리 확인
            all_categories = set(current_db_progress.keys()) | set(new_progress.keys())

            for category in all_categories:
                db_value = current_db_progress.get(category, 0.0)
                json_value = new_progress.get(category, 0.0)

                if abs(db_value - json_value) > tolerance:
                    logger.info(
                        f"🔄 Progress 변동 감지: {serial_number} [{category}] DB:{db_value}% → JSON:{json_value}%"
                    )
                    has_changes = True

            if not has_changes:
                logger.info(f"⚪ Progress 변동 없음: {serial_number} (DB와 JSON 일치)")

            return has_changes, current_db_progress, new_progress

        except Exception as e:
            logger.error(f"❌ Progress 변동 확인 실패 (S/N: {serial_number}): {e}")
            raise

    def get_changed_serials_vs_db(
        self, all_progress_data: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """
        DB와 비교하여 변동된 S/N 목록 반환

        Args:
            all_progress_data: 전체 Progress 데이터 {serial_number: progress_data}

        Returns:
            List[str]: 변동된 S/N 목록
        """
        changed_serials = []

        try:
            for serial_number, progress_data in all_progress_data.items():
                # DB 기준 Progress 변동 확인
                has_changed, db_progress, new_progress = (
                    self.has_progress_changed_vs_db(serial_number, progress_data)
                )

                if has_changed:
                    changed_serials.append(serial_number)
                    logger.info(f"✅ 변동 감지: {serial_number}")
                else:
                    logger.debug(f"⚪ 변동 없음: {serial_number}")

            logger.info(
                f"📊 DB 기준 변동 감지 결과: 전체 {len(all_progress_data)}개 중 {len(changed_serials)}개 변동"
            )
            return changed_serials

        except Exception as e:
            logger.error(f"❌ DB 기준 변동된 S/N 목록 생성 실패: {e}")
            raise

    def log_change_details(
        self,
        serial_number: str,
        db_progress: Dict[str, float],
        new_progress: Dict[str, float],
    ) -> None:
        """변동 상세 정보 로깅"""
        try:
            logger.info(f"📝 변동 상세 ({serial_number}):")

            all_categories = set(db_progress.keys()) | set(new_progress.keys())
            for category in sorted(all_categories):
                db_val = db_progress.get(category, 0.0)
                new_val = new_progress.get(category, 0.0)

                if abs(db_val - new_val) > 0.01:
                    logger.info(
                        f"   {category}: {db_val}% → {new_val}% (변동: {new_val-db_val:+.1f}%)"
                    )
                else:
                    logger.debug(f"   {category}: {db_val}% (변동없음)")

        except Exception as e:
            logger.warning(f"변동 상세 로깅 실패: {e}")
