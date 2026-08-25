"""
Kakao 주소 검색(Geocoding) + 카카오모빌리티 길찾기(자동차) API 래퍼.

필요한 것: Kakao Developers(https://developers.kakao.com)에서 발급받은 REST API 키 1개.
  - "로컬" 제품: 주소 -> 좌표 변환에 사용 (기본 활성화되어 있음)
  - "카카오모빌리티 길찾기" 제품: 콘솔에서 별도로 활성화(약관 동의)해야 호출 가능.
    발급 절차/무료 호출 한도는 카카오 쪽 정책이 바뀔 수 있으니, 최신 안내는
    Kakao Developers 콘솔에서 직접 확인해야 한다.

이 모듈은 순수 계산/조회만 담당하고, 그 결과를 어떻게 알림으로 보낼지는
telegram_client.py, 언제 보낼지 판단은 departure_alarm_daemon.py가 담당한다.
"""

import httpx

GEOCODE_URL = "https://dapi.kakao.com/v2/local/search/address.json"
DIRECTIONS_URL = "https://apis-navi.kakaomobility.com/v1/directions"


class KakaoApiError(RuntimeError):
    pass


def geocode(address: str, api_key: str) -> tuple[float, float]:
    """주소 문자열 -> (경도 x, 위도 y). 여러 건 검색되면 첫 번째 결과를 쓴다."""
    resp = httpx.get(
        GEOCODE_URL,
        headers={"Authorization": f"KakaoAK {api_key}"},
        params={"query": address},
        timeout=10,
    )
    if resp.status_code != 200:
        raise KakaoApiError(f"주소 검색 실패 ({resp.status_code}): {resp.text}")

    docs = resp.json().get("documents", [])
    if not docs:
        raise KakaoApiError(f"주소를 찾을 수 없습니다: {address!r}")

    doc = docs[0]
    return float(doc["x"]), float(doc["y"])


def get_driving_eta_minutes(origin_address: str, destination_address: str, api_key: str) -> dict:
    """
    두 주소 사이의 '지금 출발한다면' 자동차 이동시간(분)/거리(km)를 돌려준다.
    Kakao 길찾기 API는 미래 시점의 예상 교통상황까지 미리 계산해주지는 않으므로,
    약속 시간이 많이 남았을 때 미리 계산한 값은 참고용이고, 실제 출발 시점이
    가까워질수록 다시 계산해야 정확하다 (daemon이 주기적으로 재계산하는 이유).
    """
    ox, oy = geocode(origin_address, api_key)
    dx, dy = geocode(destination_address, api_key)

    resp = httpx.get(
        DIRECTIONS_URL,
        headers={"Authorization": f"KakaoAK {api_key}"},
        params={
            "origin": f"{ox},{oy}",
            "destination": f"{dx},{dy}",
            "priority": "RECOMMEND",
        },
        timeout=10,
    )
    if resp.status_code != 200:
        raise KakaoApiError(f"길찾기 실패 ({resp.status_code}): {resp.text}")

    data = resp.json()
    routes = data.get("routes", [])
    if not routes or routes[0].get("result_code") != 0:
        raise KakaoApiError(f"경로를 찾을 수 없습니다: {data}")

    summary = routes[0]["summary"]
    return {
        "minutes": round(summary["duration"] / 60, 1),
        "distance_km": round(summary["distance"] / 1000, 2),
    }
