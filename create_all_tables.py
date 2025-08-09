"""
모든 테이블을 생성하는 스크립트
"""
import os
import psycopg2
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_all_tables():
    os.environ['DB_HOST'] = 'switchyard.proxy.rlwy.net'
    os.environ['DB_PORT'] = '52564'
    os.environ['DB_USER'] = 'postgres'
    os.environ['DB_NAME'] = 'railway'
    
    try:
        conn = psycopg2.connect(
            host=os.environ['DB_HOST'],
            port=os.environ['DB_PORT'],
            user=os.environ['DB_USER'],
            password=os.environ['DB_PASSWORD'],
            database=os.environ['DB_NAME']
        )
        
        cursor = conn.cursor()
        
        # 모든 테이블 생성
        tables = [
            # documents (이미 생성됨)
            """CREATE TABLE IF NOT EXISTS documents (
                document_id SERIAL PRIMARY KEY,
                execution_date DATE,
                timestamp TIMESTAMP
            );""",
            
            # info (이미 생성됨)
            """CREATE TABLE IF NOT EXISTS info (
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
            );""",
            
            # worksheet
            """CREATE TABLE IF NOT EXISTS worksheet (
                worksheet_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                task_name TEXT, 
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                task_category VARCHAR(50)
            );""",
            
            # task_summary
            """CREATE TABLE IF NOT EXISTS task_summary (
                task_summary_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                serial_number VARCHAR(128),
                task_name VARCHAR(255), 
                task_category VARCHAR(50),
                working_hours DOUBLE PRECISION, 
                total_working_time VARCHAR(20),
                title_number VARCHAR(255) 
            );""",
            
            # ot_details
            """CREATE TABLE IF NOT EXISTS ot_details (
                ot_details_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                task_name VARCHAR(255), 
                duration DOUBLE PRECISION
            );""",
            
            # progress_summary
            """CREATE TABLE IF NOT EXISTS progress_summary (
                progress_summary_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                serial_number VARCHAR(128),
                category VARCHAR(50),
                progress DOUBLE PRECISION, 
                CONSTRAINT unique_progress UNIQUE (document_id, serial_number, category)
            );""",
            
            # stats
            """CREATE TABLE IF NOT EXISTS stats (
                stats_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                category VARCHAR(50),
                total_count INTEGER,
                nan_count INTEGER,
                completed_count INTEGER,
                nan_tasks JSONB,
                ot_count INTEGER
            );""",
            
            # partner_stats
            """CREATE TABLE IF NOT EXISTS partner_stats (
                partner_stats_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                partner_type VARCHAR(50),
                nan_count INTEGER,
                ot_count INTEGER,
                name VARCHAR(100) 
            );""",
            
            # additional_info
            """CREATE TABLE IF NOT EXISTS additional_info (
                additional_info_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                model_name VARCHAR(128),
                mech_partner VARCHAR(100),
                elec_partner VARCHAR(100)
            );""",
            
            # treemap_data
            """CREATE TABLE IF NOT EXISTS treemap_data (
                treemap_data_id SERIAL PRIMARY KEY,
                document_id INTEGER REFERENCES documents(document_id) ON DELETE CASCADE NOT NULL,
                progress_treemap JSONB,
                task_treemap JSONB
            );"""
        ]
        
        for i, sql in enumerate(tables, 1):
            logger.info(f"🏗️  테이블 {i}/10 생성 중...")
            cursor.execute(sql)
        
        # 인덱스 생성
        logger.info("📊 인덱스 생성 중...")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_info_serial_number ON info (serial_number);")
        
        conn.commit()
        logger.info("✅ 모든 테이블 생성 완료!")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        logger.error(f"❌ 오류: {e}")
        if conn:
            conn.rollback()

if __name__ == "__main__":
    create_all_tables()
