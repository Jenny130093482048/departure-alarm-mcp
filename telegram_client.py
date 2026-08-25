"""
Telegram Bot API로 메시지를 보내는 아주 얇은 래퍼.

필요한 것 2가지:
  1) TELEGRAM_BOT_TOKEN — @BotFather 에게 /newbot 으로 봇을 만들면 발급됨
  2) TELEGRAM_CHAT_ID   — 그 봇과 대화를 한 번 시작한 뒤,
     https://api.telegram.org/bot<TOKEN>/getUpdates 를 열어보면 내 chat id를 알 수 있음
"""

import httpx

SEND_MESSAGE_URL_TMPL = "https://api.telegram.org/bot{token}/sendMessage"


class TelegramApiError(RuntimeError):
    pass


def send_message(token: str, chat_id: str, text: str) -> dict:
    resp = httpx.post(
        SEND_MESSAGE_URL_TMPL.format(token=token),
        json={"chat_id": chat_id, "text": text},
        timeout=10,
    )
    if resp.status_code != 200:
        raise TelegramApiError(f"텔레그램 전송 실패 ({resp.status_code}): {resp.text}")
    return resp.json()
