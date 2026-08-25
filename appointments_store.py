"""
약속(목적지/시간)과 집 주소를 담아두는 아주 단순한 JSON 파일 저장소.

MCP 서버 프로세스(등록/조회용)와 daemon 프로세스(실제 알림 발송용)가 같은
appointments.json 파일을 공유해서 본다 — 그래서 둘 사이의 "연결고리"가 이 파일이다.

동시 쓰기 충돌은 이 프로젝트 규모(개인 1인용, 초 단위로 몰려 쓰지 않음)에서는
거의 발생하지 않지만, 그래도 파일이 깨지는 걸 막기 위해 임시파일에 쓰고
os.replace로 원자적으로 교체한다.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

STORE_PATH = Path(__file__).parent / "appointments.json"

_DEFAULT = {"home_address": None, "appointments": []}


def _load() -> dict:
    if not STORE_PATH.exists():
        return dict(_DEFAULT)
    try:
        with open(STORE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULT)
    data.setdefault("home_address", None)
    data.setdefault("appointments", [])
    return data


def _save(data: dict) -> None:
    tmp_path = STORE_PATH.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, STORE_PATH)


def get_home_address() -> str | None:
    return _load().get("home_address")


def set_home_address(address: str) -> None:
    data = _load()
    data["home_address"] = address
    _save(data)


def add_appointment(destination: str, appointment_time_iso: str, prep_minutes: int, buffer_minutes: int) -> dict:
    record = {
        "id": uuid.uuid4().hex[:8],
        "destination": destination,
        "appointment_time": appointment_time_iso,
        "prep_minutes": prep_minutes,
        "buffer_minutes": buffer_minutes,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "prep_alert_sent": False,
        "leave_alert_sent": False,
        "cancelled": False,
        "last_eta_minutes": None,
    }
    data = _load()
    data["appointments"].append(record)
    _save(data)
    return record


def list_appointments(include_cancelled: bool = False, include_past: bool = False) -> list[dict]:
    data = _load()
    items = data["appointments"]
    if not include_cancelled:
        items = [a for a in items if not a["cancelled"]]
    if not include_past:
        now = datetime.now()
        items = [a for a in items if datetime.fromisoformat(a["appointment_time"]) >= now]
    return sorted(items, key=lambda a: a["appointment_time"])


def get_appointment(appointment_id: str) -> dict | None:
    data = _load()
    for a in data["appointments"]:
        if a["id"] == appointment_id:
            return a
    return None


def update_appointment(appointment_id: str, **fields) -> dict | None:
    data = _load()
    for a in data["appointments"]:
        if a["id"] == appointment_id:
            a.update(fields)
            _save(data)
            return a
    return None


def cancel_appointment(appointment_id: str) -> bool:
    result = update_appointment(appointment_id, cancelled=True)
    return result is not None
