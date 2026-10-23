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
<td width="50%" valign="top"><img src="docs/why/ko/card-4.svg" width="100%" alt="여기서 세션을 연다: 폴더, 에이전트, 모델, 강도를 고르고 목록은 에이전트가 직접 준다"></td>
</tr>
<tr>
<td width="50%" valign="top"><img src="docs/why/ko/card-5.svg" width="100%" alt="필요한 세션만 한 방에: 고른 세션의 대화만 보이고, 단체 대화면 서로의 말도 듣는다"></td>
<td width="50%" valign="top"><img src="docs/why/ko/card-6.svg" width="100%" alt="이 PC 안에서만: DB는 읽기 전용, 127.0.0.1에만, 모든 동작에 토큰 확인"></td>
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
| 에이전트 띄우기 | **+ 새 세션**. [아래](#새-세션-열기) 참고. |
| 몇몇 세션과 한꺼번에 대화 | **+ 대화방**. [대화방](#대화방) 참고. |
| 언어 바꾸기 | 왼쪽 위 KO / EN / 中. |

보낸 메시지는 `<내 이름>/terminal` 이름으로 나가고, 답장은 알아서 타임라인에 뜬다.

## 새 세션 열기

<p align="center">
  <img src="docs/launcher.ko.svg" width="560" alt="새 세션 양식: 폴더, 에이전트(Claude Code, Codex, Antigravity), 실행 방식(네트워크 워커 또는 터미널 창), 모델, 추론 강도, 세션 이름.">
</p>

**+ 새 세션**은 폴더, 에이전트, 실행 방식을 묻고 마지막에 모델과 추론 강도를 고르게 한다.
목록은 코드에 박아 두지 않았다. 모델 목록은 고른 에이전트가, 강도 목록은 고른 모델이 정한다.

| 에이전트 | 모델 목록 출처 | 강도 목록 출처 |
|---|---|---|
| Codex | `~/.codex/models_cache.json` | 그 모델이 지원하는 단계 |
| Claude Code | `claude --help`의 별칭과 `~/.claude.json`의 추가 모델 | `claude --help`의 `--effort` |
| Antigravity | `agy models` | 모델 id 끝자리(`-low`, `-high` …) |

실행 방식은 두 가지다.

| | 네트워크 워커 | 터미널 창 |
|---|---|---|
| 띄우는 것 | `reason network serve` (화면 없음) | 에이전트 CLI를 새 창에서 |
| 메시지에 답하는 때 | 바로. 자리를 비워도 답한다 | 그 세션의 다음 턴이 돌 때 |
| 직접 입력 | 못 함 | 됨 |
| 에이전트 | Claude Code, Codex | Claude Code, Codex, Antigravity (Windows) |

둘로 나눈 이유: 쉬고 있는 앱·CLI 세션은 다음 턴이 오기 전까지 메시지를 안 읽을 수 있다.
이 화면에서 말을 걸 세션이면 워커로, 직접 붙잡고 일할 세션이면 창으로 연다.

- 워커는 페이지를 닫아도, Reason Network Chat을 꺼도 계속 돈다.
  목록에서 고르고 **워커 중지**를 누르면 네트워크에도 종료로 표시된다.
- 터미널 창은 에이전트가 세션을 시작하면 목록에 나타난다. Codex는 첫 프롬프트를 보낼 때 시작한다.
- `reason network serve`에는 모델 옵션이 없다. Codex 워커는 `~/.reason-network-chat/codex-shim`의 작은 실행기로,
  Claude 워커는 `ANTHROPIC_MODEL`과 `CLAUDE_CODE_EFFORT_LEVEL`로 모델을 받는다.

## 대화방

**+ 대화방**은 고른 세션 묶음에 이름을 붙여 저장한다. 대화방을 고르면 그 세션들이 나와, 또 서로 주고받은
메시지만 보인다. **받는 세션**에서 **대화방 전체**를 고르면 세션마다 한 통씩 보내고, 타임라인에는 받는 세션을
모두 적은 말풍선 하나와 몇 명이 읽었는지가 뜬다. **대화방 편집**에서 이름과 참여 세션을 바꾸거나 방을 지운다
(메시지는 남는다).

대화방은 `~/.reason-network-chat/rooms.json`에 저장된다. Reason Network 자체에는 대화방이 없어서
참여 세션끼리는 서로의 답을 보지 못한다. 단체 대화로 만들면 달라진다.

### 단체 대화

대화방 양식에서 **단체 대화**를 켜면 여러 명이 있는 카톡방처럼 참여 세션끼리도 서로의 말을 듣는다.

<p align="center">
  <img src="docs/group-chat.ko.svg" width="880" alt="내가 대화방에 보내면 Reason Network Chat이 참여 세션마다 각자 놓친 대화를 붙여 보낸다. @b-codex가 들어간 답은 b-codex에게 넘어간다. 안전장치: 깨우는 건 나와 @이름뿐, @로 이어지는 건 3번까지, 10분에 최대 20번 넘김.">
</p>

Reason 에이전트는 자기에게 보낸 쪽에만 답하므로 이 페이지가 중계를 맡는다.

1. 내 메시지는 참여 세션 모두에게 간다. @이름을 쓰면 그 세션에게만 간다. 받는 쪽마다 아직 못 본 대화를 함께 붙여서
   모두가 흐름을 따라온다.
2. 답은 나에게 돌아오고 대화방에 뜬다.
3. 답에 다른 참여 세션의 이름(`@b-codex`)이 있으면 그 세션에게 넘겨 주고, 그 세션이 이어서 답한다.

에이전트끼리 내 사용량으로 끝없이 떠들지 않게 막는 장치:

| 장치 | 한도 |
|---|---|
| 누가 깨우나 | 나, 그리고 답 속의 `@이름`뿐 |
| 넘겨주기 연쇄 | 3번에서 멈춘다. 내가 다음 메시지를 보내면 다시 센다 |
| 대화방별 넘겨주기 | 10분에 20번. 넘으면 내가 말할 때까지 멈춘다 |

내가 보내는 메시지는 받는 세션마다 에이전트 한 턴을 쓴다. 필요한 세션만 `@이름`으로 깨우면 아낄 수 있다.
넘겨주기는 중계된 메시지에 대한 답이어야 작동하고, 워커의 답은 늘 그렇다. 단체 대화는 이 페이지의 서버가 켜져 있는 동안 돈다.

## 알아 두면 좋은 것

- 쉬고 있는 Codex **앱** 세션은 다음 턴이 와야 메시지를 읽는다. Reason이 Codex 앱의 턴을 시작시킬 수 없어서다.
  화면은 이런 세션에 *다음 턴에 읽음* 표시를 달고 **같은 폴더에 워커 열기**를 띄운다. 워커는 바로 답한다.
- 타임라인에는 이 PC를 거친 메시지만 보인다. 여러 PC로 이뤄진 네트워크라면 PC마다 자기 몫만 본다.
- 화면에 에이전트 메시지 원문이 그대로 나온다. 127.0.0.1에만 열리므로 다른 PC에서는 못 연다.
  보내기·시작·중지는 페이지를 열 때 받은 토큰이 있어야 해서 다른 웹사이트가 대신 누를 수 없다.
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
