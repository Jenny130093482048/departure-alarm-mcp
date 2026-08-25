"""
departure_alarm_daemon.py
----------------------------------
실제로 텔레그램 알림을 '보내는' 담당 프로세스입니다. MCP 서버가 아니라
그냥 무한 루프를 도는 평범한 파이썬 스크립트입니다 — Claude Desktop/Code가
켜져 있는지와 무관하게, 이 스크립트 자체가 계속 실행되고 있어야 알림이 옵니다.

동작 방식:
  1) appointments.json(=appointments_store.py가 관리하는 파일)을 주기적으로 읽는다.
  2) 취소되지 않고 아직 지나지 않은 약속마다, '지금 출발한다면' 기준 이동시간을
     Kakao 길찾기 API로 다시 계산한다 (시간이 가까워질수록 더 정확해짐).
  3) 준비 시작 시각을 지났는데 아직 안 보낸 알림이면 "준비 시작" 텔레그램을 보낸다.
  4) 출발 시각을 지났는데 아직 안 보낸 알림이면 "지금 출발" 텔레그램을 보낸다.
  5) 보낸 알림은 appointments.json에 표시해 중복 발송을 막는다.

실행:
  python departure_alarm_daemon.py
  (계속 켜둬야 하므로, macOS라면 launchd(LaunchAgent)나 `caffeinate` + 백그라운드 실행,
   또는 tmux/screen 세션에 올려두는 걸 권장. 자세한 설정 예시는 README.md 참고.)
"""

import os
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv

import appointments_store as store
from kakao_client import KakaoApiError, get_driving_eta_minutes
from telegram_client import TelegramApiError, send_message

load_dotenv()

KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

POLL_INTERVAL_SECONDS = 60


def _notify(text: str) -> None:
    print(f"[ALERT] {text}")
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("  (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정 - 콘솔에만 출력합니다)")
        return
    try:
        send_message(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, text)
    except TelegramApiError as e:
        print(f"  텔레그램 전송 실패: {e}")


def _check_once() -> None:
    home_address = store.get_home_address()
    if not home_address:
        return

    now = datetime.now()
    for appt in store.list_appointments(include_past=False):
        if not KAKAO_REST_API_KEY:
            continue
        try:
            eta = get_driving_eta_minutes(home_address, appt["destination"], KAKAO_REST_API_KEY)
        except KakaoApiError as e:
            print(f"[WARN] 이동시간 계산 실패 (id={appt['id']}): {e}")
            continue

        travel_minutes = eta["minutes"]
        appt_time = datetime.fromisoformat(appt["appointment_time"])
        leave_by = appt_time - timedelta(minutes=travel_minutes + appt["buffer_minutes"])
        prep_start_by = leave_by - timedelta(minutes=appt["prep_minutes"])

        store.update_appointment(appt["id"], last_eta_minutes=travel_minutes)

        if not appt["prep_alert_sent"] and now >= prep_start_by:
            _notify(
                f"🚿 지금부터 준비 시작하세요! ({appt['destination']} {appt_time.strftime('%H:%M')} 약속, "
                f"예상 이동 {travel_minutes}분)"
            )
            store.update_appointment(appt["id"], prep_alert_sent=True)

        if not appt["leave_alert_sent"] and now >= leave_by:
            _notify(
                f"🏃 지금 나가야 늦지 않아요! ({appt['destination']} {appt_time.strftime('%H:%M')} 약속, "
                f"예상 이동 {travel_minutes}분)"
            )
            store.update_appointment(appt["id"], leave_alert_sent=True)


def main() -> None:
    print(f"departure-alarm daemon 시작 (poll interval={POLL_INTERVAL_SECONDS}s)")
    if not KAKAO_REST_API_KEY:
        print("[WARN] KAKAO_REST_API_KEY가 없어 이동시간 계산 없이는 알림이 발송되지 않습니다.")
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("[WARN] TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID가 없어 콘솔 출력만 됩니다.")

    while True:
        try:
            _check_once()
        except Exception as e:  # 데몬이 죽지 않도록 루프 자체는 지켜야 함
            print(f"[ERROR] 체크 중 예외 발생: {e}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
