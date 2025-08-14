"""
Processing Logger System
데이터 처리 과정의 상세한 로깅을 담당하는 모듈
"""
import json
import uuid
import psycopg2
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ProcessingLogger:
    """데이터 처리 과정의 로깅을 담당하는 클래스"""
    
    def __init__(self, conn, execution_id: Optional[str] = None):
        """
        Args:
            conn: PostgreSQL 데이터베이스 연결 객체
            execution_id: 실행 ID (없으면 자동 생성)
        """
        self.conn = conn
        self.execution_id = execution_id or str(uuid.uuid4())[:8]
        self.start_time = time.time()
        
    def log_action(self, action: str, status: str, serial_number: Optional[str] = None, 
                   title_number: Optional[str] = None, message: Optional[str] = None,
                   progress_before: Optional[Dict[str, Any]] = None,
                   progress_after: Optional[Dict[str, Any]] = None,
                   processing_time_ms: Optional[int] = None) -> bool:
        """
        처리 액션 로깅
        
        Args:
            action: 액션 타입 (예: 'EXTRACT', 'LOAD', 'UPDATE', 'SKIP')
            status: 상태 (예: 'SUCCESS', 'FAILED', 'SKIPPED')
            serial_number: S/N
            title_number: 제목 번호
            message: 상세 메시지
            progress_before: 변경 전 Progress 데이터
            progress_after: 변경 후 Progress 데이터
            processing_time_ms: 처리 시간 (밀리초)
            
        Returns:
            bool: 로깅 성공 여부
        """
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                INSERT INTO processing_log 
                (execution_id, serial_number, title_number, action, status, message, 
                 progress_before, progress_after, processing_time_ms, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """, (
                self.execution_id,
                serial_number,
                title_number,
                action,
                status,
                message,
                json.dumps(progress_before, ensure_ascii=False) if progress_before else None,
                json.dumps(progress_after, ensure_ascii=False) if progress_after else None,
                processing_time_ms
            ))
            
            cursor.close()
            return True
            
        except Exception as e:
            logger.error(f"❌ 처리 로그 저장 실패: {e}")
            return False
    
    def log_extraction_start(self, message: str = "데이터 추출 시작") -> bool:
        """데이터 추출 시작 로깅"""
        return self.log_action("EXTRACT", "STARTED", message=f"{message} (실행 ID: {self.execution_id})")
    
    def log_extraction_success(self, count: int, message: Optional[str] = None) -> bool:
        """데이터 추출 성공 로깅"""
        msg = message or f"데이터 추출 완료: {count}개 S/N"
        return self.log_action("EXTRACT", "SUCCESS", message=msg)
    
    def log_extraction_failed(self, error_message: str) -> bool:
        """데이터 추출 실패 로깅"""
        return self.log_action("EXTRACT", "FAILED", message=f"데이터 추출 실패: {error_message}")
    
    def log_progress_change_detected(self, serial_number: str, title_number: Optional[str],
                                   progress_before: Dict[str, Any], progress_after: Dict[str, Any],
                                   processing_time_ms: int) -> bool:
        """Progress 변동 감지 로깅"""
        return self.log_action(
            "PROGRESS_CHANGE", "DETECTED", 
            serial_number=serial_number, 
            title_number=title_number,
            message=f"Progress 변동 감지됨",
            progress_before=progress_before,
            progress_after=progress_after,
            processing_time_ms=processing_time_ms
        )
    
    def log_progress_no_change(self, serial_number: str, title_number: Optional[str],
                              processing_time_ms: int) -> bool:
        """Progress 변동 없음 로깅"""
        return self.log_action(
            "PROGRESS_CHECK", "SKIPPED", 
            serial_number=serial_number, 
            title_number=title_number,
            message="Progress 변동 없음 - 처리 건너뜀",
            processing_time_ms=processing_time_ms
        )
    
    def log_db_load_start(self, serial_number: str, title_number: Optional[str]) -> bool:
        """DB 적재 시작 로깅"""
        return self.log_action(
            "LOAD", "STARTED",
            serial_number=serial_number,
            title_number=title_number,
            message="DB 데이터 적재 시작"
        )
    
    def log_db_load_success(self, serial_number: str, title_number: Optional[str],
                           processing_time_ms: int, affected_tables: List[str]) -> bool:
        """DB 적재 성공 로깅"""
        tables_msg = ", ".join(affected_tables)
        return self.log_action(
            "LOAD", "SUCCESS",
            serial_number=serial_number,
            title_number=title_number,
            message=f"DB 적재 완료 - 영향받은 테이블: {tables_msg}",
            processing_time_ms=processing_time_ms
        )
    
    def log_db_load_failed(self, serial_number: str, title_number: Optional[str],
                          processing_time_ms: int, error_message: str) -> bool:
        """DB 적재 실패 로깅"""
        return self.log_action(
            "LOAD", "FAILED",
            serial_number=serial_number,
            title_number=title_number,
            message=f"DB 적재 실패: {error_message}",
            processing_time_ms=processing_time_ms
        )
    
    def log_transaction_start(self, serial_number: str, title_number: Optional[str]) -> bool:
        """개별 트랜잭션 시작 로깅"""
        return self.log_action(
            "TRANSACTION", "STARTED",
            serial_number=serial_number,
            title_number=title_number,
            message="개별 트랜잭션 시작"
        )
    
    def log_transaction_commit(self, serial_number: str, title_number: Optional[str],
                              processing_time_ms: int) -> bool:
        """개별 트랜잭션 커밋 로깅"""
        return self.log_action(
            "TRANSACTION", "COMMITTED",
            serial_number=serial_number,
            title_number=title_number,
            message="개별 트랜잭션 커밋 완료",
            processing_time_ms=processing_time_ms
        )
    
    def log_transaction_rollback(self, serial_number: str, title_number: Optional[str],
                               processing_time_ms: int, error_message: str) -> bool:
        """개별 트랜잭션 롤백 로깅"""
        return self.log_action(
            "TRANSACTION", "ROLLBACK",
            serial_number=serial_number,
            title_number=title_number,
            message=f"개별 트랜잭션 롤백: {error_message}",
            processing_time_ms=processing_time_ms
        )
    
    def log_execution_summary(self, total_processed: int, total_changed: int, 
                             total_skipped: int, total_failed: int) -> bool:
        """실행 요약 로깅"""
        total_time_sec = int((time.time() - self.start_time) * 1000)
        
        summary_msg = (
            f"실행 완료 요약 - 총 처리: {total_processed}개, "
            f"변동 감지: {total_changed}개, 건너뜀: {total_skipped}개, "
            f"실패: {total_failed}개, 총 소요시간: {total_time_sec}ms"
        )
        
        return self.log_action(
            "EXECUTION", "COMPLETED",
            message=summary_msg,
            processing_time_ms=total_time_sec
        )
    
    def get_execution_logs(self) -> List[Dict[str, Any]]:
        """현재 실행의 로그 조회"""
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                SELECT log_id, serial_number, title_number, action, status, 
                       message, progress_before, progress_after, processing_time_ms, created_at
                FROM processing_log 
                WHERE execution_id = %s 
                ORDER BY created_at
            """, (self.execution_id,))
            
            results = cursor.fetchall()
            cursor.close()
            
            logs = []
            for row in results:
                logs.append({
                    'log_id': row[0],
                    'serial_number': row[1],
                    'title_number': row[2],
                    'action': row[3],
                    'status': row[4],
                    'message': row[5],
                    'progress_before': row[6],
                    'progress_after': row[7],
                    'processing_time_ms': row[8],
                    'created_at': row[9]
                })
            
            return logs
            
        except Exception as e:
            logger.error(f"❌ 실행 로그 조회 실패: {e}")
            return []
    
    def commit_logs(self) -> bool:
        """로그 커밋"""
        try:
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"❌ 로그 커밋 실패: {e}")
            return False
    
    def cleanup_old_logs(self, days_to_keep: int = 30) -> int:
        """
        오래된 로그 정리
        
        Args:
            days_to_keep: 보관 기간 (일수)
            
        Returns:
            int: 삭제된 로그 수
        """
        try:
            cursor = self.conn.cursor()
            
            cursor.execute("""
                DELETE FROM processing_log 
                WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '%s days'
            """, (days_to_keep,))
            
            deleted_count = cursor.rowcount
            cursor.close()
            self.conn.commit()
            
            logger.info(f"🧹 오래된 처리 로그 정리 완료: {deleted_count}개 삭제")
            return deleted_count
            
        except Exception as e:
            logger.error(f"❌ 처리 로그 정리 실패: {e}")
            self.conn.rollback()
            raise