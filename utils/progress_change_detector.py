"""
Progress Change Detection System
해시 기반으로 Progress 데이터의 변동을 감지하여 효율적인 처리를 가능하게 하는 모듈
"""
import hashlib
import json
import psycopg2
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ProgressChangeDetector:
    """Progress 변동 감지를 위한 클래스"""
    
    def __init__(self, conn):
        """
        Args:
            conn: PostgreSQL 데이터베이스 연결 객체
        """
        self.conn = conn
        
    def generate_progress_hash(self, progress_data: Dict[str, Any]) -> str:
        """
        Progress 데이터에서 해시값 생성
        
        Args:
            progress_data: Progress 관련 데이터 (progress_summary 부분)
            
        Returns:
            str: SHA-256 해시값 (64자리 hex string)
        """
        try:
            # progress_summary 데이터만 추출하여 해시 생성
            if 'progress_summary' in progress_data:
                progress_only = progress_data['progress_summary']
            else:
                progress_only = progress_data
                
            # 정렬된 JSON으로 변환하여 일관된 해시 생성
            normalized_json = json.dumps(progress_only, sort_keys=True, ensure_ascii=False)
            
            # SHA-256 해시 생성
            hash_object = hashlib.sha256(normalized_json.encode('utf-8'))
            return hash_object.hexdigest()
            
        except Exception as e:
            logger.error(f"❌ Progress 해시 생성 실패: {e}")
            raise
    
    def get_existing_snapshot(self, serial_number: str, title_number: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        기존 스냅샷 조회
        
        Args:
            serial_number: S/N
            title_number: 제목 번호 (선택사항)
            
        Returns:
            dict or None: 기존 스냅샷 데이터 또는 None
        """
        try:
            cursor = self.conn.cursor()
            
            if title_number:
                cursor.execute("""
                    SELECT snapshot_id, progress_hash, snapshot_data, last_updated
                    FROM progress_snapshots 
                    WHERE serial_number = %s AND title_number = %s
                """, (serial_number, title_number))
            else:
                cursor.execute("""
                    SELECT snapshot_id, progress_hash, snapshot_data, last_updated
                    FROM progress_snapshots 
                    WHERE serial_number = %s AND title_number IS NULL
                """, (serial_number,))
            
            result = cursor.fetchone()
            cursor.close()
            
            if result:
                return {
                    'snapshot_id': result[0],
                    'progress_hash': result[1],
                    'snapshot_data': result[2],
                    'last_updated': result[3]
                }
            return None
            
        except Exception as e:
            logger.error(f"❌ 기존 스냅샷 조회 실패 (S/N: {serial_number}): {e}")
            raise
    
    def save_snapshot(self, serial_number: str, title_number: Optional[str], 
                     progress_hash: str, progress_data: Dict[str, Any]) -> bool:
        """
        Progress 스냅샷 저장 (INSERT or UPDATE)
        
        Args:
            serial_number: S/N
            title_number: 제목 번호
            progress_hash: Progress 해시값
            progress_data: Progress 데이터
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            cursor = self.conn.cursor()
            
            # UPSERT 쿼리 (PostgreSQL ON CONFLICT 사용)
            cursor.execute("""
                INSERT INTO progress_snapshots 
                (serial_number, title_number, progress_hash, snapshot_data, last_updated)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (serial_number, title_number) 
                DO UPDATE SET 
                    progress_hash = EXCLUDED.progress_hash,
                    snapshot_data = EXCLUDED.snapshot_data,
                    last_updated = CURRENT_TIMESTAMP
            """, (serial_number, title_number, progress_hash, json.dumps(progress_data, ensure_ascii=False)))
            
            cursor.close()
            logger.info(f"✅ Progress 스냅샷 저장 완료 (S/N: {serial_number})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Progress 스냅샷 저장 실패 (S/N: {serial_number}): {e}")
            raise
    
    def has_progress_changed(self, serial_number: str, title_number: Optional[str], 
                           new_progress_data: Dict[str, Any]) -> tuple:
        """
        Progress 변동 여부 확인
        
        Args:
            serial_number: S/N
            title_number: 제목 번호
            new_progress_data: 새로운 Progress 데이터
            
        Returns:
            tuple: (변동여부, 기존해시, 새해시)
        """
        try:
            # 새로운 데이터의 해시 생성
            new_hash = self.generate_progress_hash(new_progress_data)
            
            # 기존 스냅샷 조회
            existing_snapshot = self.get_existing_snapshot(serial_number, title_number)
            
            if existing_snapshot is None:
                # 기존 스냅샷이 없으면 새로운 데이터로 간주
                logger.info(f"🆕 새로운 S/N 감지: {serial_number}")
                return True, None, new_hash
            
            existing_hash = existing_snapshot['progress_hash']
            
            if existing_hash != new_hash:
                logger.info(f"🔄 Progress 변동 감지: {serial_number} (해시 변경: {existing_hash[:8]}... → {new_hash[:8]}...)")
                return True, existing_hash, new_hash
            else:
                logger.info(f"⚪ Progress 변동 없음: {serial_number} (해시: {existing_hash[:8]}...)")
                return False, existing_hash, new_hash
                
        except Exception as e:
            logger.error(f"❌ Progress 변동 확인 실패 (S/N: {serial_number}): {e}")
            raise
    
    def get_changed_serials(self, all_progress_data: Dict[str, Dict[str, Any]]) -> List[str]:
        """
        변동된 S/N 목록 반환
        
        Args:
            all_progress_data: 전체 Progress 데이터 {serial_number: progress_data}
            
        Returns:
            List[str]: 변동된 S/N 목록
        """
        changed_serials = []
        
        try:
            for serial_number, progress_data in all_progress_data.items():
                # title_number 추출 (있다면)
                title_number = progress_data.get('title_number')
                
                # Progress 변동 확인
                has_changed, old_hash, new_hash = self.has_progress_changed(
                    serial_number, title_number, progress_data
                )
                
                if has_changed:
                    changed_serials.append(serial_number)
                    
            logger.info(f"📊 변동 감지 결과: 전체 {len(all_progress_data)}개 중 {len(changed_serials)}개 변동")
            return changed_serials
            
        except Exception as e:
            logger.error(f"❌ 변동된 S/N 목록 생성 실패: {e}")
            raise
    
    def update_snapshots_batch(self, progress_data_batch: Dict[str, Dict[str, Any]]) -> int:
        """
        Progress 스냅샷들을 배치로 업데이트
        
        Args:
            progress_data_batch: Progress 데이터 배치 {serial_number: progress_data}
            
        Returns:
            int: 업데이트된 스냅샷 수
        """
        updated_count = 0
        
        try:
            for serial_number, progress_data in progress_data_batch.items():
                title_number = progress_data.get('title_number')
                progress_hash = self.generate_progress_hash(progress_data)
                
                if self.save_snapshot(serial_number, title_number, progress_hash, progress_data):
                    updated_count += 1
                    
            self.conn.commit()
            logger.info(f"✅ Progress 스냅샷 배치 업데이트 완료: {updated_count}개")
            return updated_count
            
        except Exception as e:
            logger.error(f"❌ Progress 스냅샷 배치 업데이트 실패: {e}")
            self.conn.rollback()
            raise
    
    def cleanup_old_snapshots(self, days_to_keep: int = 30) -> int:
        """
        오래된 스냅샷 정리
        
        Args:
            days_to_keep: 보관 기간 (일수)
            
        Returns:
            int: 삭제된 스냅샷 수
        """
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                DELETE FROM progress_snapshots 
                WHERE last_updated < CURRENT_TIMESTAMP - INTERVAL '%s days'
            """, (days_to_keep,))
            
            deleted_count = cursor.rowcount
            cursor.close()
            self.conn.commit()
            
            logger.info(f"🧹 오래된 Progress 스냅샷 정리 완료: {deleted_count}개 삭제")
            return deleted_count
            
        except Exception as e:
            logger.error(f"❌ Progress 스냅샷 정리 실패: {e}")
            self.conn.rollback()
            raise