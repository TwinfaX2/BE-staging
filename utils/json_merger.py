"""
JSON 병합 시스템
추출 실패 시 이전 성공 데이터와 새 데이터를 병합하여 누락 방지
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import glob

logger = logging.getLogger(__name__)


class JSONMerger:
    """JSON 파일 병합 관리자"""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        self.ensure_output_dir()

    def ensure_output_dir(self):
        """출력 디렉토리 확인/생성"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)
            logger.info(f"📁 출력 디렉토리 생성: {self.output_dir}")

    def find_latest_successful_json(self, date_range=None) -> Optional[str]:
        """
        가장 최근 성공한 JSON 파일 찾기
        
        Args:
            date_range: 날짜 범위 (start_date, end_date) 튜플
            
        Returns:
            str or None: 최근 성공 파일 경로
        """
        try:
            # output 디렉토리에서 JSON 파일 검색
            pattern = os.path.join(self.output_dir, "output_*.json")
            json_files = glob.glob(pattern)
            
            if not json_files:
                logger.info("📂 이전 JSON 파일을 찾을 수 없습니다.")
                return None
            
            # 파일 수정 시간 기준으로 정렬 (최신 순)
            json_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            
            # 각 파일의 유효성 검사
            for json_file in json_files:
                if self.validate_json_file(json_file, date_range):
                    logger.info(f"✅ 최근 성공 파일 발견: {os.path.basename(json_file)}")
                    return json_file
            
            logger.warning("⚠️ 유효한 이전 JSON 파일을 찾을 수 없습니다.")
            return None
            
        except Exception as e:
            logger.error(f"❌ 이전 JSON 파일 검색 실패: {e}")
            return None

    def validate_json_file(self, file_path: str, date_range=None) -> bool:
        """
        JSON 파일 유효성 검사
        
        Args:
            file_path: JSON 파일 경로
            date_range: 날짜 범위
            
        Returns:
            bool: 유효한 파일인지 여부
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 기본 구조 확인
            if 'documents' not in data or not isinstance(data['documents'], list):
                logger.warning(f"⚠️ 잘못된 JSON 구조: {os.path.basename(file_path)}")
                return False
            
            documents = data['documents']
            if len(documents) == 0:
                logger.warning(f"⚠️ 빈 documents 배열: {os.path.basename(file_path)}")
                return False
            
            # 최소 데이터 개수 확인 (너무 적으면 실패로 간주)
            min_expected = 50  # 최소 50개 이상이어야 성공으로 간주
            if len(documents) < min_expected:
                logger.warning(f"⚠️ 데이터 개수 부족: {os.path.basename(file_path)} ({len(documents)}개 < {min_expected}개)")
                return False
            
            logger.info(f"✅ 유효한 JSON 파일: {os.path.basename(file_path)} ({len(documents)}개 documents)")
            return True
            
        except Exception as e:
            logger.error(f"❌ JSON 파일 검증 실패 {os.path.basename(file_path)}: {e}")
            return False

    def extract_sns_from_json(self, file_path: str) -> List[str]:
        """
        JSON 파일에서 S/N 목록 추출
        
        Args:
            file_path: JSON 파일 경로
            
        Returns:
            list: S/N 목록
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            sns = []
            for doc in data.get('documents', []):
                if 'info' in doc and doc['info']:
                    for info_item in doc['info']:
                        sn = info_item.get('S/N')
                        if sn and str(sn).strip():
                            sns.append(str(sn).strip())
            
            return sns
            
        except Exception as e:
            logger.error(f"❌ S/N 추출 실패 {os.path.basename(file_path)}: {e}")
            return []

    def merge_json_data(self, current_data: Dict, previous_file: str) -> Dict:
        """
        현재 데이터와 이전 성공 데이터 병합
        
        Args:
            current_data: 현재 추출된 데이터
            previous_file: 이전 성공 파일 경로
            
        Returns:
            dict: 병합된 데이터
        """
        try:
            # 이전 데이터 로드
            with open(previous_file, 'r', encoding='utf-8') as f:
                previous_data = json.load(f)
            
            logger.info(f"🔄 데이터 병합 시작:")
            logger.info(f"   - 현재 데이터: {len(current_data.get('documents', []))}개")
            logger.info(f"   - 이전 데이터: {len(previous_data.get('documents', []))}개")
            
            # 현재 데이터의 S/N 목록 생성
            current_sns = set()
            for doc in current_data.get('documents', []):
                if 'info' in doc and doc['info']:
                    for info_item in doc['info']:
                        sn = info_item.get('S/N')
                        if sn:
                            current_sns.add(str(sn).strip())
            
            # 병합된 documents 리스트 생성
            merged_documents = []
            
            # 1. 현재 데이터 추가 (우선순위)
            merged_documents.extend(current_data.get('documents', []))
            
            # 2. 이전 데이터에서 중복되지 않는 것만 추가
            added_from_previous = 0
            for doc in previous_data.get('documents', []):
                if 'info' in doc and doc['info']:
                    for info_item in doc['info']:
                        sn = info_item.get('S/N')
                        if sn and str(sn).strip() not in current_sns:
                            merged_documents.append(doc)
                            added_from_previous += 1
                            break  # 하나의 document당 하나의 S/N만 확인
            
            # 병합된 데이터 구성
            merged_data = {
                'documents': merged_documents,
                'timestamp': datetime.now().isoformat(),
                'merge_info': {
                    'current_count': len(current_data.get('documents', [])),
                    'previous_count': len(previous_data.get('documents', [])),
                    'added_from_previous': added_from_previous,
                    'total_merged': len(merged_documents),
                    'previous_file': os.path.basename(previous_file)
                }
            }
            
            logger.info(f"✅ 병합 완료:")
            logger.info(f"   - 이전 데이터에서 추가: {added_from_previous}개")
            logger.info(f"   - 최종 병합 결과: {len(merged_documents)}개")
            
            return merged_data
            
        except Exception as e:
            logger.error(f"❌ 데이터 병합 실패: {e}")
            # 병합 실패 시 현재 데이터 반환
            return current_data

    def should_merge_with_previous(self, current_data: Dict, expected_min: int = 100) -> bool:
        """
        이전 데이터와 병합이 필요한지 판단
        
        Args:
            current_data: 현재 추출된 데이터
            expected_min: 예상 최소 데이터 개수
            
        Returns:
            bool: 병합 필요 여부
        """
        current_count = len(current_data.get('documents', []))
        
        if current_count < expected_min:
            logger.warning(f"⚠️ 추출 데이터 부족 감지: {current_count}개 < {expected_min}개 (병합 필요)")
            return True
        
        logger.info(f"✅ 충분한 데이터 추출: {current_count}개 >= {expected_min}개 (병합 불필요)")
        return False

    def save_merged_json(self, merged_data: Dict, output_file: str) -> bool:
        """
        병합된 데이터를 JSON 파일로 저장
        
        Args:
            merged_data: 병합된 데이터
            output_file: 출력 파일 경로
            
        Returns:
            bool: 저장 성공 여부
        """
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(merged_data, f, ensure_ascii=False, indent=2)
            
            file_size = os.path.getsize(output_file)
            logger.info(f"✅ 병합 JSON 저장 완료: {os.path.basename(output_file)} ({file_size:,} bytes)")
            
            # 병합 정보 로깅
            if 'merge_info' in merged_data:
                info = merged_data['merge_info']
                logger.info(f"📊 병합 정보:")
                logger.info(f"   - 현재 데이터: {info['current_count']}개")
                logger.info(f"   - 이전 파일: {info['previous_file']}")
                logger.info(f"   - 추가된 데이터: {info['added_from_previous']}개")
                logger.info(f"   - 최종 결과: {info['total_merged']}개")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 병합 JSON 저장 실패: {e}")
            return False


# 편의 함수들
def merge_if_needed(current_data: Dict, output_file: str, expected_min: int = 100) -> Tuple[Dict, bool]:
    """
    필요시 이전 데이터와 병합
    
    Args:
        current_data: 현재 데이터
        output_file: 출력 파일 경로
        expected_min: 예상 최소 개수
        
    Returns:
        tuple: (최종_데이터, 병합_여부)
    """
    merger = JSONMerger()
    
    # 병합 필요성 판단
    if not merger.should_merge_with_previous(current_data, expected_min):
        return current_data, False
    
    # 이전 성공 파일 찾기
    previous_file = merger.find_latest_successful_json()
    if not previous_file:
        logger.warning("⚠️ 이전 성공 파일이 없어 병합하지 않습니다.")
        return current_data, False
    
    # 병합 실행
    merged_data = merger.merge_json_data(current_data, previous_file)
    
    return merged_data, True


if __name__ == "__main__":
    # 테스트 실행
    logging.basicConfig(level=logging.INFO)
    
    merger = JSONMerger()
    
    # 테스트: 최근 성공 파일 찾기
    latest_file = merger.find_latest_successful_json()
    if latest_file:
        print(f"✅ 최근 파일: {latest_file}")
        
        # S/N 목록 추출 테스트
        sns = merger.extract_sns_from_json(latest_file)
        print(f"📊 S/N 개수: {len(sns)}개")
        print(f"📋 샘플 S/N: {sns[:5]}")
    else:
        print("❌ 최근 파일을 찾을 수 없습니다.")
