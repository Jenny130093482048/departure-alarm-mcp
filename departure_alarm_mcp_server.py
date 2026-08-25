"""
departure_alarm_mcp_server.py
----------------------------------
ADHD 등으로 "미리 계산해두지 않으면 시간 약속을 잘 못 챙기는" 사람들을 위한
출발 시간 알림 프로젝트의 '입력/조회' 담당 MCP 서버입니다.

*** 중요: 이 MCP 서버 자체는 알림을 보내지 않습니다. ***
이 서버는 Claude와 대화하면서 "집 주소 등록", "약속 등록/조회/취소"를 하는
입구 역할만 합니다. 실제로 정해진 시각에 텔레그램 알림을 보내는 건 이 디렉토리의
departure_alarm_daemon.py 가 별도 프로세스로 계속 돌고 있어야 합니다
(Claude Desktop/Code를 껐다 켜는 것과 무관하게 항상 켜져 있어야 진짜 알림 역할을 함).
왜 이렇게 나눴는지는 README.md의 "왜 두 개의 프로세스로 나눴나" 항목을 보세요.

이 서버가 하는 일 (정확한 계산·저장):
  1) 집 주소 등록/조회 (set_home_address, get_home_address)
  2) 약속 등록 (register_appointment) — 등록 시점 기준 예상 이동시간도 즉시 계산해 보여줌
  3) 약속 목록 조회 (list_appointments)
  4) 약속 취소 (cancel_appointment)
  5) 지금 이 순간 기준으로 상태를 즉석에서 확인 (check_now) — daemon 없이도 테스트 가능

이 tool을 호출하는 AI(Claude)가 하는 일:
  - 사용자가 "내일 3시 강남역에서 약속"처럼 자연어로 말한 걸 appointment_time(ISO 8601)과
    destination으로 정리해서 register_appointment에 넘겨주는 것.
  - prep_minutes(준비 시간), buffer_minutes(여유 시간)를 사용자와 대화하며 적절히 정하는 것.

환경변수(.env 파일 또는 셸 환경변수)로 KAKAO_REST_API_KEY 가 설정되어 있어야
이동시간 계산이 가능합니다. 없으면 등록은 되지만 이동시간 없이 저장만 됩니다.

실행 방법:
  1) pip install mcp python-dotenv httpx
  2) .env 파일에 KAKAO_REST_API_KEY=... 설정 (kakao_client.py 상단 설명 참고)
  3) python departure_alarm_mcp_server.py
  4) Claude Desktop 설정에 등록:
     {
       "mcpServers": {
         "departure-alarm": {
           "command": "python",
           "args": ["/절대/경로/departure_alarm_mcp_server.py"]
         }
       }
     }
"""

import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

import appointments_store as store
from kakao_client import KakaoApiError, get_driving_eta_minutes

load_dotenv()

mcp = FastMCP("departure-alarm")

KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")


def _compute_status(home_address: str, appointment: dict) -> dict:
    """지금 이 순간 기준으로 이동시간을 계산해, 준비 시작 시각/출발 시각/여유 여부를 판단."""
    appt_time = datetime.fromisoformat(appointment["appointment_time"])
    now = datetime.now()

    if not KAKAO_REST_API_KEY:
        return {"ok": False, "error": "KAKAO_REST_API_KEY가 설정되어 있지 않아 이동시간을 계산할 수 없습니다."}

    try:
        eta = get_driving_eta_minutes(home_address, appointment["destination"], KAKAO_REST_API_KEY)
    except KakaoApiError as e:
        return {"ok": False, "error": str(e)}

    travel_minutes = eta["minutes"]
    leave_by = appt_time - timedelta(minutes=travel_minutes + appointment["buffer_minutes"])
    prep_start_by = leave_by - timedelta(minutes=appointment["prep_minutes"])

    return {
        "ok": True,
        "now": now.isoformat(timespec="seconds"),
        "appointment_time": appt_time.isoformat(timespec="seconds"),
        "travel_minutes": travel_minutes,
        "distance_km": eta["distance_km"],
        "prep_start_by": prep_start_by.isoformat(timespec="seconds"),
        "leave_by": leave_by.isoformat(timespec="seconds"),
        "should_be_prepping_now": now >= prep_start_by,
        "should_leave_now": now >= leave_by,
        "minutes_until_leave": round((leave_by - now).total_seconds() / 60, 1),
    }


@mcp.tool()
def set_home_address(address: str) -> dict:
    """이동시간 계산의 출발지로 쓸 집 주소를 등록한다. (도로명/지번 주소 권장)"""
    store.set_home_address(address)
    return {"ok": True, "home_address": address}


@mcp.tool()
def get_home_address() -> dict:
    """등록된 집 주소를 확인한다."""
    address = store.get_home_address()
    if not address:
        return {"ok": False, "error": "아직 집 주소가 등록되지 않았습니다. set_home_address를 먼저 호출하세요."}
    return {"ok": True, "home_address": address}


@mcp.tool()
def register_appointment(
    destination: str,
    appointment_time: str,
    prep_minutes: int = 30,
    buffer_minutes: int = 10,
) -> dict:
    """
    약속을 등록한다.
    appointment_time은 "2026-08-26T15:00:00" 형식(ISO 8601, 초 단위까지 권장)이어야 한다.
    prep_minutes: 씻고 준비하는 데 걸리는 시간(분). buffer_minutes: 이동시간에 더할 여유 시간(분).

    등록과 동시에 현재 교통상황 기준 예상 이동시간으로 '지금 시점의' 출발 시각을 미리 계산해
    함께 보여준다. 실제 알림은 daemon이 시간이 가까워질수록 재계산해서 보낸다.
    """
    home_address = store.get_home_address()
    if not home_address:
        return {"ok": False, "error": "집 주소가 먼저 등록되어야 합니다. set_home_address를 호출하세요."}

    try:
        datetime.fromisoformat(appointment_time)
    except ValueError:
        return {"ok": False, "error": f"appointment_time 형식이 올바르지 않습니다: {appointment_time!r} (예: 2026-08-26T15:00:00)"}

    record = store.add_appointment(destination, appointment_time, prep_minutes, buffer_minutes)
    preview = _compute_status(home_address, record)
    return {"ok": True, "appointment": record, "current_estimate": preview}


@mcp.tool()
def list_appointments(include_past: bool = False) -> list[dict]:
    """등록된 약속 목록을 시간순으로 보여준다."""
    return store.list_appointments(include_past=include_past)


@mcp.tool()
def cancel_appointment(appointment_id: str) -> dict:
    """약속을 취소한다 (더 이상 알림이 발송되지 않음)."""
    ok = store.cancel_appointment(appointment_id)
    if not ok:
        return {"ok": False, "error": f"id={appointment_id} 약속을 찾을 수 없습니다."}
    return {"ok": True, "cancelled_id": appointment_id}


@mcp.tool()
def check_now(appointment_id: str) -> dict:
    """
    daemon 없이도, 지금 이 순간 기준으로 '준비 시작해야 하는지' '나가야 하는지'를
    즉석에서 계산해 보여준다 (실제 텔레그램 알림은 보내지 않음, 확인용).
    """
    appointment = store.get_appointment(appointment_id)
    if appointment is None:
        return {"ok": False, "error": f"id={appointment_id} 약속을 찾을 수 없습니다."}

    home_address = store.get_home_address()
    if not home_address:
        return {"ok": False, "error": "집 주소가 등록되어 있지 않습니다."}

    return _compute_status(home_address, appointment)


if __name__ == "__main__":
    mcp.run()
