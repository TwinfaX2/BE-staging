import json
import logging
import os
from datetime import datetime
import pandas as pd


def save_to_json(data: dict | pd.DataFrame, output_path: str = "output/result.json"):
    """
    데이터를 JSON 파일로 저장합니다. 파일명에 오늘 날짜를 추가합니다.

    :param data: 저장할 데이터 (dict 또는 DataFrame)
    :param output_path: 저장할 파일의 전체 경로 (디렉토리 포함)
    :return: 저장된 파일 경로
    """
    try:
        # 출력 경로의 디렉토리 확인 및 생성
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logging.info(f"출력 디렉토리 생성: {output_dir}")

        # 파일명에 날짜 추가
        base_filename = os.path.splitext(os.path.basename(output_path))[0]
        today = datetime.now().strftime("%Y%m%d")
        filename = f"{base_filename}_{today}.json"
        output_file = os.path.join(output_dir, filename)

        if isinstance(data, pd.DataFrame):
            save_data = {
                "data": data.to_dict(orient="records"),
                "timestamp": datetime.now().isoformat(),
            }
        elif isinstance(data, dict):
            save_data = data.copy()
            # timestamp가 없으면 추가
            if "timestamp" not in save_data:
                save_data["timestamp"] = datetime.now().isoformat()
        else:
            raise TypeError(
                "지원되지 않는 데이터 형식입니다. dict 또는 DataFrame을 사용하세요."
            )

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(save_data, f, ensure_ascii=False, indent=4)
        logging.info(f"✅ JSON 저장 완료: {output_file}")
        return output_file
    except Exception as e:
        logging.error(f"❌ JSON 저장 실패: {e}")
        raise
