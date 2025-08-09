"""
테이블 생성 과정을 상세히 디버깅
"""
import os
import psycopg2
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def create_tables_debug():
    # 연결 정보
    os.environ['DB_HOST'] = 'switchyard.proxy.rlwy.net'
    os.environ['DB_PORT'] = '52564'
    os.environ['DB_USER'] = 'postgres'
    os.environ['DB_NAME'] = 'railway'
    
    try:
        logger.info("🔗 DB 연결 중...")
        conn = psycopg2.connect(
            host=os.environ['DB_HOST'],
            port=os.environ['DB_PORT'],
            user=os.environ['DB_USER'],
            password=os.environ['DB_PASSWORD'],
            database=os.environ['DB_NAME']
        )
        
        cursor = conn.cursor()
        
        # 수동으로 테이블 생성
        logger.info("🏗️  documents 테이블 생성 중...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                document_id SERIAL PRIMARY KEY,
                execution_date DATE,
                timestamp TIMESTAMP
            );
        """)
        
        logger.info("🏗️  info 테이블 생성 중...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS info (
                info_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                serial_number VARCHAR(128),
                model_name VARCHAR(128),
                mech_partner VARCHAR(50),
                elec_partner VARCHAR(50),
                customer VARCHAR(50),
                sales_order VARCHAR(50),
                line VARCHAR(50),
                quantity VARCHAR(10), 
                manufacturing_start TIMESTAMP,
                manufacturing_end TIMESTAMP,
                test_start TIMESTAMP,
                test_end TIMESTAMP,
                semi_product_start TIMESTAMP,
                module_outsourcing VARCHAR(50),
                product_code VARCHAR(50),
                title_number VARCHAR(255), 
                spreadsheet_link VARCHAR(512),
                CONSTRAINT uq_info_document_sn UNIQUE (document_id, serial_number)
            );
        """)
        
        # 커밋 실행
        logger.info("💾 변경사항 커밋 중...")
        conn.commit()
        
        # 생성 확인
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        logger.info(f"✅ 생성된 테이블: {[t[0] for t in tables]}")
        
        cursor.close()
        conn.close()
        
        return len(tables) > 0
        
    except Exception as e:
        logger.error(f"❌ 오류 발생: {e}")
        if conn:
            conn.rollback()
        return False

if __name__ == "__main__":
    success = create_tables_debug()
    print(f"\n{'✅ 성공!' if success else '❌ 실패!'}")
