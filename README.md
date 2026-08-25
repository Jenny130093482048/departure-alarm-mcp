# departure-alarm-mcp

약속 장소·시간을 등록해두면, 집에서부터 실제 이동시간을 계산해서
"지금 준비 시작해야 해요", "지금 나가야 해요"를 텔레그램으로 알려주는 개인용 프로젝트입니다.
시간 계산을 미리 해두지 않으면 약속에 잘 늦는 사람들(예: ADHD 특성)을 돕기 위해 만들었습니다.

## 왜 프로세스를 두 개(MCP 서버 / daemon)로 나눴나

- `departure_alarm_mcp_server.py` — Claude와 대화하며 집 주소·약속을 **등록/조회**하는 MCP 서버.
  Claude Desktop/Code가 이 서버를 실행하는 동안에만 켜져 있습니다.
- `departure_alarm_daemon.py` — 실제로 **텔레그램 알림을 보내는** 평범한 상시 실행 스크립트.

MCP 서버는 Claude 앱을 켤 때만 같이 켜지는 구조라, 여기에 "알림 보내기"까지 넣으면
Claude 앱을 꺼두는 순간 알림도 같이 죽어버립니다. 그건 "약속에 정말 늦지 않게 도와주는 앱"의
목적에 맞지 않아서, 알림 발송은 Claude와 무관하게 항상 떠 있는 별도 스크립트로 분리했습니다.
**즉, daemon을 안 띄워두면 알림은 오지 않습니다.**

두 프로세스는 같은 `appointments.json` 파일을 통해 정보를 주고받습니다.

## 준비물

1. **Kakao REST API 키** — [Kakao Developers](https://developers.kakao.com) 에서 앱 생성 후
   REST API 키 발급. "카카오모빌리티 길찾기" 제품은 콘솔에서 별도 동의가 필요할 수 있습니다
   (정책은 카카오 쪽에서 바뀔 수 있으니 콘솔 안내를 최종 기준으로 확인하세요).
2. **Telegram 봇** — 텔레그램에서 `@BotFather` 검색 → `/newbot` → 토큰 발급.
   발급받은 봇과 먼저 대화를 한 번 걸어야 chat id를 받을 수 있습니다
   (`https://api.telegram.org/bot<토큰>/getUpdates` 접속해서 확인).

`.env.example`을 `.env`로 복사하고 위에서 얻은 값을 채워 넣으세요.

## 설치 및 실행

```bash
uv venv .venv --python 3.12   # 또는 python -m venv .venv
uv pip install --python .venv/bin/python mcp python-dotenv httpx
cp .env.example .env   # 값 채우기

# 1) 알림 daemon을 상시 실행 (터미널을 하나 계속 띄워두거나, tmux/launchd 등으로 백그라운드화)
.venv/bin/python departure_alarm_daemon.py

# 2) Claude Desktop/Code에 MCP 서버 등록 (claude_desktop_config.json)
```
```json
{
  "mcpServers": {
    "departure-alarm": {
      "command": "/절대/경로/.venv/bin/python",
      "args": ["/절대/경로/departure_alarm_mcp_server.py"]
    }
  }
}
```

## 사용 흐름

1. Claude에게 "집 주소는 OO야"라고 말하면 `set_home_address` 호출됨
2. "내일 3시 강남역에서 약속이야"라고 말하면 Claude가 `register_appointment`를 호출
   (destination="강남역", appointment_time="2026-08-26T15:00:00", prep_minutes/buffer_minutes은
   대화하면서 적절히 정함) — 등록 즉시 "지금 교통상황 기준" 예상 출발 시각을 바로 보여줍니다.
3. `check_now`로 daemon 없이도 지금 상태를 바로 확인 가능 (텔레그램 발송은 안 함, 확인용)
4. daemon이 1분마다 모든 약속을 다시 계산하며, 준비 시작 시각/출발 시각을 지나면
   텔레그램으로 알림을 보냅니다.

## 알려진 한계 (정직하게 적어둡니다)

- **미래 시점 교통 예측 아님**: Kakao 길찾기 API는 "지금 출발한다면" 기준 이동시간만
  알려줍니다. 약속이 많이 남았을 때 계산한 값은 참고용이고, daemon이 1분마다 재계산하며
  실제 출발 시점에 가까워질수록 정확해지는 방식으로 이 한계를 보완합니다.
- **자동차 이동 기준**: 도보/대중교통 이동시간이 아닙니다. 다른 이동수단을 쓰려면
  `kakao_client.py`에 대중교통/도보 API 호출을 추가해야 합니다.
- **캘린더 연동 없음**: 약속은 Claude와의 대화(MCP tool)로 직접 등록합니다.
  실제 캘린더 앱에서 자동으로 읽어오게 하려면 Google Calendar API 등의 별도 연동이 필요합니다.
- **동시 쓰기 안전성**: `appointments.json`은 개인 1인용 규모를 가정한 단순 파일 저장소입니다.
