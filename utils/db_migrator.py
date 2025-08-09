import pandas as pd
import logging
from sqlalchemy import create_engine
from config.settings import DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME

def migrate_to_postgres(df: pd.DataFrame, table_name: str = 'pda_results', if_exists: str = 'replace'):
    """
    DataFrame을 PostgreSQL에 저장합니다.

    :param df: 저장할 pandas DataFrame
    :param table_name: 저장할 PostgreSQL 테이블 이름
    :param if_exists: 'fail', 'replace', 'append' 중 선택
    """
    if not isinstance(df, pd.DataFrame):
        raise TypeError("❌ 입력값은 pandas DataFrame이어야 합니다.")

    try:
        # DB 연결 URI 구성
        db_url = f'postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
        engine = create_engine(db_url)

        # 저장 실행
        df.to_sql(name=table_name, con=engine, if_exists=if_exists, index=False)
        logging.info(f"✅ PostgreSQL 저장 완료: {table_name}, 행 수: {len(df)}")
        
    except Exception as e:
        logging.error(f"❌ PostgreSQL 저장 실패: {e}")
        raise