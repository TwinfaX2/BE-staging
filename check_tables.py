"""
스테이징 DB에 실제로 테이블이 생성되었는지 확인
"""
import os
import psycopg2

def check_tables():
    # 스테이징 DB 연결
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
        
        # 모든 테이블 목록 조회
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        
        tables = cursor.fetchall()
        
        print("🔍 스테이징 DB의 테이블 목록:")
        if tables:
            for table in tables:
                print(f"  ✅ {table[0]}")
            print(f"\n📊 총 {len(tables)}개 테이블 발견")
        else:
            print("  ❌ 테이블이 없습니다!")
        
        # 각 테이블의 레코드 수 확인
        if tables:
            print("\n📈 각 테이블의 레코드 수:")
            for table in tables:
                table_name = table[0]
                cursor.execute(f"SELECT COUNT(*) FROM {table_name};")
                count = cursor.fetchone()[0]
                print(f"  {table_name}: {count}개")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ 연결 오류: {e}")

if __name__ == "__main__":
    check_tables()
