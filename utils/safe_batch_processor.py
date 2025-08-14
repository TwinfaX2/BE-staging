"""
Safe Batch Processor System
안전한 배치 처리를 담당하는 모듈 - 개별 트랜잭션과 Progress 변동 감지를 통합
"""
import psycopg2
import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

from .progress_change_detector import ProgressChangeDetector
from .processing_logger import ProcessingLogger

logger = logging.getLogger(__name__)


class SafeBatchProcessor:
    """안전한 배치 처리를 담당하는 클래스"""
    
    def __init__(self, conn, batch_size: int = 10, tolerance: float = 0.1):
        """
        Args:
            conn: PostgreSQL 데이터베이스 연결 객체
            batch_size: 배치 크기
            tolerance: Progress 비교 허용 오차
        """
        self.conn = conn
        self.batch_size = batch_size
        self.tolerance = tolerance
        
        # 하위 모듈 초기화
        self.change_detector = ProgressChangeDetector(conn)
        self.logger = ProcessingLogger(conn)
        
        # 처리 통계
        self.stats = {
            'total_processed': 0,
            'total_changed': 0,
            'total_skipped': 0,
            'total_failed': 0,
            'processing_times': []
        }
    
    def process_data_batch(self, extracted_data: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        추출된 데이터를 안전하게 배치 처리
        
        Args:
            extracted_data: 추출된 데이터 {serial_number: data}
            
        Returns:
            dict: 처리 결과 요약
        """
        start_time = time.time()
        
        # 처리 시작 로깅
        self.logger.log_extraction_start(f"배치 처리 시작: {len(extracted_data)}개 S/N")
        
        try:
            # 1. Progress 변동 감지
            changed_serials = self.change_detector.get_changed_serials(extracted_data)
            
            logger.info(f"📊 Progress 변동 감지 결과:")
            logger.info(f"   - 전체 S/N: {len(extracted_data)}개")
            logger.info(f"   - 변동 감지: {len(changed_serials)}개")
            logger.info(f"   - 건너뛸 S/N: {len(extracted_data) - len(changed_serials)}개")
            
            # 2. 변동된 S/N만 개별 처리
            success_count = 0
            failed_serials = []
            
            for serial_number in changed_serials:
                data = extracted_data[serial_number]
                
                if self.process_single_serial(serial_number, data):
                    success_count += 1
                else:
                    failed_serials.append(serial_number)
            
            # 3. 변동되지 않은 S/N들에 대해 SKIP 로깅
            skipped_serials = set(extracted_data.keys()) - set(changed_serials)
            for serial_number in skipped_serials:
                data = extracted_data[serial_number]
                title_number = data.get('title_number')
                self.logger.log_progress_no_change(serial_number, title_number, 0)
            
            # 4. Progress 스냅샷 업데이트 (변동된 S/N만)
            changed_data = {sn: extracted_data[sn] for sn in changed_serials}
            self.change_detector.update_snapshots_batch(changed_data)
            
            # 5. 통계 업데이트
            self.stats['total_processed'] = len(extracted_data)
            self.stats['total_changed'] = len(changed_serials)
            self.stats['total_skipped'] = len(skipped_serials)
            self.stats['total_failed'] = len(failed_serials)
            
            total_time_ms = int((time.time() - start_time) * 1000)
            self.stats['processing_times'].append(total_time_ms)
            
            # 6. 실행 요약 로깅
            self.logger.log_execution_summary(
                self.stats['total_processed'],
                self.stats['total_changed'],
                self.stats['total_skipped'],
                self.stats['total_failed']
            )
            
            # 7. 최종 커밋
            self.conn.commit()
            self.logger.commit_logs()
            
            logger.info(f"✅ 배치 처리 완료: {success_count}/{len(changed_serials)}개 성공")
            
            return {
                'success': True,
                'total_processed': len(extracted_data),
                'total_changed': len(changed_serials),
                'total_skipped': len(skipped_serials),
                'success_count': success_count,
                'failed_count': len(failed_serials),
                'failed_serials': failed_serials,
                'processing_time_ms': total_time_ms
            }
            
        except Exception as e:
            logger.error(f"❌ 배치 처리 실패: {e}")
            self.conn.rollback()
            
            self.logger.log_extraction_failed(str(e))
            self.logger.commit_logs()
            
            return {
                'success': False,
                'error': str(e),
                'total_processed': len(extracted_data),
                'total_changed': 0,
                'total_skipped': 0,
                'success_count': 0,
                'failed_count': len(extracted_data),
                'failed_serials': list(extracted_data.keys()),
                'processing_time_ms': int((time.time() - start_time) * 1000)
            }
    
    def process_single_serial(self, serial_number: str, data: Dict[str, Any]) -> bool:
        """
        단일 S/N 데이터를 개별 트랜잭션으로 처리
        
        Args:
            serial_number: S/N
            data: 해당 S/N의 모든 데이터
            
        Returns:
            bool: 처리 성공 여부
        """
        start_time = time.time()
        title_number = data.get('title_number')
        
        # 개별 트랜잭션 시작
        try:
            # SavePoint 생성 (중첩 트랜잭션)
            savepoint_name = f"sp_{serial_number.replace('-', '_')}"
            cursor = self.conn.cursor()
            cursor.execute(f"SAVEPOINT {savepoint_name}")
            cursor.close()
            
            self.logger.log_transaction_start(serial_number, title_number)
            
            # 기존 데이터 삭제 (해당 S/N의 모든 관련 데이터)
            self._delete_existing_data(serial_number)
            
            # 새 데이터 삽입
            affected_tables = self._insert_new_data(serial_number, data)
            
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # 개별 트랜잭션 커밋 (SavePoint 해제)
            cursor = self.conn.cursor()
            cursor.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            cursor.close()
            
            self.logger.log_db_load_success(
                serial_number, title_number, processing_time_ms, affected_tables
            )
            self.logger.log_transaction_commit(serial_number, title_number, processing_time_ms)
            
            logger.info(f"✅ S/N {serial_number} 처리 완료 ({processing_time_ms}ms)")
            return True
            
        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # 개별 트랜잭션 롤백 (SavePoint로 복구)
            try:
                cursor = self.conn.cursor()
                cursor.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                cursor.close()
            except:
                pass  # SavePoint가 없을 수도 있음
            
            logger.error(f"❌ S/N {serial_number} 처리 실패: {e}")
            
            self.logger.log_db_load_failed(
                serial_number, title_number, processing_time_ms, str(e)
            )
            self.logger.log_transaction_rollback(
                serial_number, title_number, processing_time_ms, str(e)
            )
            
            return False
    
    def _delete_existing_data(self, serial_number: str) -> None:
        """해당 S/N의 기존 데이터 삭제"""
        cursor = self.conn.cursor()
        
        try:
            # documents 테이블에서 document_id 조회
            cursor.execute("SELECT document_id FROM documents WHERE serial_number = %s", (serial_number,))
            doc_result = cursor.fetchone()
            
            if doc_result:
                document_id = doc_result[0]
                
                # 각 테이블에서 관련 데이터 삭제 (외래키 순서 고려)
                delete_queries = [
                    "DELETE FROM treemap_data WHERE document_id = %s",
                    "DELETE FROM stats WHERE document_id = %s", 
                    "DELETE FROM partner_stats WHERE document_id = %s",
                    "DELETE FROM additional_info WHERE document_id = %s",
                    "DELETE FROM task_summary WHERE document_id = %s",
                    "DELETE FROM progress_summary WHERE document_id = %s",
                    "DELETE FROM ot_details WHERE document_id = %s",
                    "DELETE FROM worksheet WHERE document_id = %s",
                    "DELETE FROM info WHERE document_id = %s",
                    "DELETE FROM documents WHERE document_id = %s"
                ]
                
                for query in delete_queries:
                    cursor.execute(query, (document_id,))
                    
        except Exception as e:
            logger.error(f"❌ 기존 데이터 삭제 실패 (S/N: {serial_number}): {e}")
            raise
        finally:
            cursor.close()
    
    def _insert_new_data(self, serial_number: str, data: Dict[str, Any]) -> List[str]:
        """새 데이터 삽입 - 기존 load_json_to_postgres.py의 삽입 함수들을 재사용"""
        affected_tables = []
        
        try:
            # 기존 삽입 함수들을 import 및 사용 (현재 모듈에서 접근)
            from . import load_json_to_postgres as loader
            
            # documents 테이블 삽입
            document_id = loader.insert_document(self.conn, data, data.get('timestamp'))
            affected_tables.append('documents')
            
            # 각 테이블별 삽입
            loader.insert_info(self.conn, document_id, data.get('info', []))
            affected_tables.append('info')
            
            loader.insert_worksheet(self.conn, document_id, data.get('worksheet', []))
            affected_tables.append('worksheet')
            
            loader.insert_task_summary(self.conn, document_id, data.get('task_summary', []), data.get('info', []))
            affected_tables.append('task_summary')
            
            loader.insert_ot_details(self.conn, document_id, data.get('ot_details', []))
            affected_tables.append('ot_details')
            
            loader.insert_progress_summary(self.conn, document_id, data.get('progress_summary', {}))
            affected_tables.append('progress_summary')
            
            loader.insert_stats(self.conn, document_id, data.get('stats', {}))
            affected_tables.append('stats')
            
            loader.insert_partner_stats(self.conn, document_id, data.get('partner_stats', {}))
            affected_tables.append('partner_stats')
            
            loader.insert_additional_info(self.conn, document_id, data.get('additional_info', {}))
            affected_tables.append('additional_info')
            
            loader.insert_treemap_data(self.conn, document_id, data.get('treemap_data', {}))
            affected_tables.append('treemap_data')
            
            # 데이터 검증
            loader.verify_data(self.conn, document_id)
            
            logger.debug(f"✅ 새 데이터 삽입 완료 (S/N: {serial_number}, DocID: {document_id})")
            
        except Exception as e:
            logger.error(f"❌ 새 데이터 삽입 실패 (S/N: {serial_number}): {e}")
            raise
            
        return affected_tables
    
    def get_processing_stats(self) -> Dict[str, Any]:
        """처리 통계 반환"""
        avg_time = 0
        if self.stats['processing_times']:
            avg_time = sum(self.stats['processing_times']) / len(self.stats['processing_times'])
            
        return {
            'total_processed': self.stats['total_processed'],
            'total_changed': self.stats['total_changed'],
            'total_skipped': self.stats['total_skipped'],
            'total_failed': self.stats['total_failed'],
            'success_rate': (
                (self.stats['total_changed'] - self.stats['total_failed']) / 
                max(self.stats['total_changed'], 1)
            ) * 100,
            'average_processing_time_ms': int(avg_time),
            'efficiency_improvement': (
                self.stats['total_skipped'] / 
                max(self.stats['total_processed'], 1)
            ) * 100
        }
    
    def cleanup_old_data(self, days_to_keep: int = 30) -> Dict[str, int]:
        """오래된 데이터 정리"""
        try:
            # Progress 스냅샷 정리
            deleted_snapshots = self.change_detector.cleanup_old_snapshots(days_to_keep)
            
            # 처리 로그 정리
            deleted_logs = self.logger.cleanup_old_logs(days_to_keep)
            
            return {
                'deleted_snapshots': deleted_snapshots,
                'deleted_logs': deleted_logs
            }
            
        except Exception as e:
            logger.error(f"❌ 오래된 데이터 정리 실패: {e}")
            raise