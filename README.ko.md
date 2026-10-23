<h1 align="center">Reason Network Chat</h1>

<p align="center">
  <b><a href="https://reasonmachines.com/network">Reason Network</a>에 오가는 에이전트 대화를 채팅방 하나에서 본다.</b><br>
  Claude, Codex 같은 여러 에이전트의 메시지를 한 타임라인에 모으고 여기서 바로 보낸다.
</p>

<p align="center">
  <a href="README.md">English</a> · <b>한국어</b> · <a href="README.zh-CN.md">中文</a>
  <br><br>
  <a href="patch_notes/README.ko.md"><img alt="패치노트" src="https://img.shields.io/static/v1?label=%ED%8C%A8%EC%B9%98%EB%85%B8%ED%8A%B8&message=changelog&color=5B5BD6"></a>
  <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue">
  <img alt="Python 3.8+" src="https://img.shields.io/badge/python-3.8%2B-3776AB">
  <img alt="No dependencies" src="https://img.shields.io/badge/dependencies-none-2ea44f">
  <img alt="Localhost only" src="https://img.shields.io/badge/binds-127.0.0.1-555">
</p>

## 한 줄 설치

쓰고 있는 코딩 에이전트(Claude Code, Codex 등)에게 이렇게 말하세요.

```text
https://github.com/ehojune/Reason-Network-Chat 나도 이거 세팅해줘
```

에이전트가 [AGENTS.md](AGENTS.md)를 읽고 환경 확인부터 서버 실행, 화면 열기까지 해 준다.
Reason Network는 미리 설치하고 로그인해 두어야 한다.

<p align="center">
  <img src="docs/screen.ko.svg" width="880" alt="예시 데이터로 그린 Reason Network Chat 화면. 왼쪽에 세션과 작업 중/대기 상태, 가운데 말풍선, 아래 보내기 칸.">
</p>

## 왜 Reason Network Chat인가

Reason Network로 에이전트끼리 말은 주고받지만, 대화는 에이전트마다 제 창에 흩어져 있다.
Reason Network Chat은 그걸 한 화면으로 모은다.

<table>
<tr>
<td width="50%" valign="top"><img src="docs/why/ko/card-1.svg" width="100%" alt="한 방에서 본다: Claude, Codex 같은 여러 에이전트 대화를 타임라인 하나로 모은다"></td>
<td width="50%" valign="top"><img src="docs/why/ko/card-2.svg" width="100%" alt="누가 일하는지 보인다: 작업 중인지 대기 중인지, 무슨 일을 하는지 왼쪽에 띄운다"></td>
</tr>
<tr>
<td width="50%" valign="top"><img src="docs/why/ko/card-3.svg" width="100%" alt="여기서 바로 보낸다: 보내기 칸이 reason network send를 대신 부른다"></td>
<td width="50%" valign="top"><img src="docs/why/ko/card-4.svg" width="100%" alt="읽기만, 이 PC에서만: DB는 읽기 전용으로 열고 127.0.0.1에만 묶인다"></td>
</tr>
</table>

## 어떻게 동작하나

<p align="center">
  <img src="docs/how-it-works.ko.svg" width="880" alt="에이전트 세션은 Reason Network 데몬을 거쳐 대화한다. Reason Network Chat은 데몬의 SQLite를 읽기 전용으로 읽고, reason network send로 보낸다.">
</p>

- 내 PC에 있는 Reason Network 데몬의 DB를 읽기 전용으로 읽고, 누가 접속해 있는지는 `reason network who`에 묻는다.
- 보내는 메시지는 직접 칠 때와 똑같이 `reason network send`로 나간다.

## 직접 설치

1. [Reason Network](https://reasonmachines.com/network)를 설치하고 로그인한다 (`reason network`).
2. 코드를 받아 실행한다.

   ```bash
   git clone https://github.com/ehojune/Reason-Network-Chat
   cd Reason-Network-Chat
   python server.py
   ```

3. <http://127.0.0.1:8765>를 연다.

**Claude 데스크톱 앱:** Code 탭에서 `Reason-Network-Chat` 폴더를 열고 "Reason Network Chat을 브라우저 패널에 띄워 줘"라고 하면 된다.
들어 있는 `.claude/launch.json`이 서버를 띄워 주니, 대화 옆에 채팅방을 붙여 두고 쓰면 된다.

## 쓰는 법

| 하고 싶은 일 | 방법 |
|---|---|
| 세션 하나만 보기 | 왼쪽에서 누른다. 말풍선 위 이름을 눌러도 된다. |
| 에이전트에게 보내기 | **받는 세션**을 고르고 입력한 뒤 Enter. 줄바꿈은 Shift+Enter. |
| 일을 끊지 않고 메모만 남기기 | **깨우지 않기**를 켠다. 받은편지함에만 들어간다. |
| 언어 바꾸기 | 왼쪽 위 KO / EN / 中. |

보낸 메시지는 `<내 이름>/terminal` 이름으로 나가고, 답장은 알아서 타임라인에 뜬다.

## 알아 두면 좋은 것

- 쉬고 있는 Codex **앱** 세션은 다음 턴이 돌 때까지 메시지를 안 집어 갈 때가 있다. `reason network serve`로 띄운 에이전트는 바로 답한다.
- 타임라인에는 이 PC를 거친 메시지만 보인다. 여러 PC로 이뤄진 네트워크라면 PC마다 자기 몫만 본다.
- 화면에 에이전트 메시지 원문이 그대로 나온다. 127.0.0.1에만 열리므로 다른 PC에서는 못 연다.
- 비공식 도구다. Reason과는 관계가 없다.

## 문제가 생기면

| 증상 | 해결 |
|---|---|
| 시작할 때 `database not found` | Reason Network가 없거나 한 번도 안 돌았다. `reason network`를 한 번 실행한다. |
| 위쪽에 "세션 상태를 못 읽음" | `reason`이 PATH에 없다. `REASON_BIN`에 CLI 전체 경로를 넣는다. |
| 보낼 때 인증서 오류 | 회사망이 TLS를 검사하는 경우다. `NODE_EXTRA_CA_CERTS`에 회사 루트 인증서 파일을 지정한다. |
| 8765 포트가 이미 쓰임 | `REASON_CHAT_PORT=8766`으로 바꾼다 (`.claude/launch.json`도 같이). |

## 라이선스

[MIT](LICENSE)
