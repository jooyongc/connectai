import time
import random
from typing import Dict, Any, Optional

# --- Mock API Client (실제 API 호출을 모킹하여 테스트 용이성 확보) ---
class MockGoogleMapsClient:
    """
    실제 Google Maps API를 대신하는 클라이언트.
    Rate Limit 및 다양한 오류 상황(Exception)을 시뮬레이션합니다.
    """
    MAX_CALLS = 3  # 테스트 목적상 최대 호출 횟수 제한

    def __init__(self):
        self.call_count = 0

    def get_place_data(self, place_id: str) -> Dict[str, Any]:
        """가상의 장소 데이터를 가져오는 함수 (실패 상황 시뮬레이션 포함)."""
        self.call_count += 1
        print(f"[DEBUG] API Call Count: {self.call_count}")

        # 1. Rate Limit 실패 시뮬레이션 (3회 초과)
        if self.call_count > 3 and random.choice([True, False]):
             raise Exception("API_RATE_LIMIT_EXCEEDED: Too many requests.")

        # 2. API 키 오류 시뮬레이션 (매우 낮은 확률)
        if self.call_count == 5:
            raise ConnectionError("AUTH_FAILED: Invalid API Key provided.")

        # 3. 데이터 구조 오류 또는 빈 값 시뮬레이션 (가장 흔한 비정상 케이스)
        if random.random() < 0.1: # 10% 확률로 데이터를 빈 리스트나 None으로 반환 가정
             return {"reviews": [], "total_reviews": None, "trend_score": "N/A"}

        # 성공적인 데이터 반환 (가상의 지역별 리뷰 및 트렌드 변화율)
        review_count = random.randint(10, 500)
        trend_score = round(random.uniform(-1.0, 1.0), 2) # -1.0 ~ 1.0 사이의 값

        return {
            "reviews": [{"text": f"Good place for {place_id}"}],
            "total_reviews": review_count,
            "trend_score": trend_score
        }

# --- Data Adapter Core Logic ---
class GoogleMapsAdapter:
    """
    외부 API 호출의 안정성을 담당하는 전용 어댑터 레이어.
    재시도 로직(Retry) 및 예외 처리를 구현합니다.
    """
    def __init__(self, api_key: str):
        # 실제로는 환경변수나 Secrets Manager에서 키를 가져와야 함
        self._client = MockGoogleMapsClient() # 테스트를 위해 Mock 사용
        self.api_key = api_key
        self.max_retries = 3

    def _execute_with_retry(self, func, *args, **kwargs):
        """재시도 로직 (Exponential Backoff)을 구현한 내부 함수."""
        for attempt in range(self.max_retries):
            try:
                # API 호출 실행
                result = func(*args, **kwargs)
                return result

            except Exception as e:
                error_msg = str(e)
                if "RATE_LIMIT" in error_msg or "OVERLOAD" in error_msg:
                    wait_time = 2 ** attempt + random.uniform(0, 1) # 지수 백오프
                    print(f"[ERROR] Rate Limit Detected. Retrying in {wait_time:.2f} seconds...")
                    time.sleep(wait_time)
                    continue  # 다음 재시도 시도

                elif "AUTH_FAILED" in error_msg:
                     print(f"[CRITICAL ERROR] Authentication Failed. Check API Key.")
                     return None # 복구 불가능한 에러는 즉시 실패 처리

                else:
                    print(f"[ERROR] Unexpected Error on attempt {attempt + 1}: {e}")
                    break # 다른 오류는 재시도하지 않고 종료

        # 모든 재시도가 실패했을 경우
        return None


    def get_local_data(self, place_id: str) -> Optional[Dict[str, float]]:
        """
        장소 ID를 받아 지역별 핵심 지표를 가져오는 주 함수.
        모든 데이터는 안전하게 float 타입으로 변환하여 반환합니다.
        """
        print(f"\n--- Attempting to fetch data for {place_id} ---")

        # 1. API 호출 실행 및 오류 처리 적용
        raw_data = self._execute_with_retry(self._client.get_place_data, place_id)

        if raw_data is None:
            print("[FAIL] Data Adapter failed to retrieve data after all retries.")
            return None

        # 2. 데이터 검증 및 클리닝 (Data Cleaning & Validation)
        try:
            total_reviews = float(raw_data['total_reviews']) if raw_data['total_reviews'] is not None else 0.0
            trend_score = float(raw_data['trend_score']) if raw_data['trend_score'] != "N/A" else 0.0

        except (TypeError, ValueError) as e:
             print(f"[CLEANING FAIL] Data Type Conversion Error: {e}. Defaulting to safe values.")
             # 데이터 타입 오류 발생 시 안전 기본값 반환
            return {"total_reviews": 0.0, "trend_score": 0.0}


        # 최종적으로 Annual Risk Cost 계산에 사용될 핵심 지표만 구조화하여 반환
        cleaned_data = {
            "total_reviews": total_reviews,
            "trend_score": trend_score # 이 값이 연간 리스크 비용 계산의 변수가 됨.
        }
        print(f"[SUCCESS] Cleaned Data Returned: {cleaned_data}")
        return cleaned_data

# --- 테스트 실행 예시 (Run Test Example) ---
if __name__ == "__main__":
    # API 키는 환경변수에서 로드한다고 가정합니다.
    adapter = GoogleMapsAdapter(api_key="DUMMY_API_KEY")

    print("===========================================")
    print("1. 정상 데이터 흐름 테스트 (Success Path)")
    data_success = adapter.get_local_data("Seoul_Cafe_A")
    if data_success:
        # 이 데이터를 가지고 연간 리스크 비용 계산 로직이 돌아갑니다.
        print(f"\n✅ [TEST RESULT] Annual Risk Cost Calculation Input Ready: {data_success}")

    time.sleep(1)

    print("\n===========================================")
    print("2. 비정상 데이터 흐름 테스트 (Failure Path Simulation)")
    # API 호출 횟수를 늘려 Rate Limit을 유도합니다.
    for i in range(6): # 6번의 호출 시도로 Rate Limit 및 다양한 에러 발생 가정
        adapter.get_local_data(f"Test_Place_{i}")