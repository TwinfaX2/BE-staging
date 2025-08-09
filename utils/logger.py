import logging
import os

def setup_logging(logger_name="pda_pipeline"):
    """
    로깅 설정 함수.
    - PDA 프로젝트 루트 기준 logs 폴더에 로그 기록
    - 콘솔과 파일 동시 출력
    """
    # 현재 logger.py 기준 상위 폴더로 이동해 logs 디렉토리 지정
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "pda_pipeline.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filename=log_file,
        filemode='a'
    )

    # 콘솔 핸들러 추가
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)

    logger = logging.getLogger(logger_name)
    if not logger.handlers or not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        logger.addHandler(console_handler)

    return logger

# 테스트용 실행
if __name__ == "__main__":
    logger = setup_logging()
    logger.info("✅ 로깅 정상 작동 확인 완료.")