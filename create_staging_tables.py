"""
스테이징 DB에 테이블 구조만 생성하는 스크립트
"""
import os
import sys
from utils.load_json_to_postgres import connect_to_db, create_tables
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # 스테이징 DB 환경변수 설정 (GitHub Secrets에서 가져올 값들)
    os.environ['DB_HOST'] = 'switchyard.proxy.rlwy.net'
    os.environ['DB_PORT'] = '52564'
    os.environ['DB_USER'] = 'postgres'
    os.environ['DB_NAME'] = 'railway'
    # DB_PASSWORD는 실제 실행 시 환경변수로 설정 필요
    
    if not os.getenv('DB_PASSWORD'):
        logger.error("❌ DB_PASSWORD 환경변수가 설정되지 않았습니다.")
        logger.info("실행 방법: DB_PASSWORD='your_password' python create_staging_tables.py")
        return
    
    try:
        logger.info("🔗 스테이징 DB 연결 중...")
        conn = connect_to_db()
        
        logger.info("🏗️  테이블 생성 중...")
        create_tables(conn)
        
        logger.info("✅ 스테이징 DB 테이블 생성 완료!")
        logger.info("📊 생성된 테이블:")
        logger.info("  - documents")
        logger.info("  - info")
        logger.info("  - worksheet") 
        logger.info("  - task_summary")
        logger.info("  - ot_details")
        logger.info("  - progress_summary")
        logger.info("  - stats")
        logger.info("  - partner_stats")
        logger.info("  - additional_info")
        logger.info("  - treemap_data")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"❌ 테이블 생성 실패: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
