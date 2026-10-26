<p align="center"><img src="favicon.svg" width="88" height="88" alt="Reason Network Chat 토끼 아이콘"></p>
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

<p align="center">
  <img src="docs/screen.ko.svg" width="880" alt="예시 데이터로 그린 Reason Network Chat 화면. 왼쪽에 세션과 작업 중/대기 상태, 가운데 말풍선, 아래 보내기 칸.">
</p>

## 무엇을 할 수 있나

- Claude·Codex·Gemini 등 여러 에이전트의 대화와 작업 상태를 한 화면에서 본다.
- 채팅방에서 에이전트를 `@이름`으로 부르고 답을 받는다.
- 새 워커를 만들고 모델·추론 강도·권한을 바꾼다. Codex는 Standard·Fast도 고른다.
- 즐겨찾기와 분류별 순서 편집으로 자주 쓰는 세션을 정리한다.

## 설치와 실행

Python 3.8+와 로그인한 [Reason Network](https://reasonmachines.com/network)가 필요하다. Python 추가 패키지는 없다.

쓰고 있는 코딩 에이전트에게 다음 문장을 보내면 [AGENTS.md](AGENTS.md)의 절차로 설치한다.

```text
https://github.com/ehojune/Reason-Network-Chat 나도 이거 세팅해줘
```

직접 설치하려면:

```bash
git clone https://github.com/ehojune/Reason-Network-Chat
cd Reason-Network-Chat
python server.py
```

브라우저에서 <http://127.0.0.1:8765>를 연다. 터미널에서 띄웠다면 Ctrl+C로 서버를 끈다.
Claude 데스크톱 앱에서는 Code 탭에 이 폴더를 열고 “브라우저 패널에 띄워 줘”라고 하면 된다.

## 처음 써 보기

| 하고 싶은 일 | 시작하는 곳 |
|---|---|
| 기존 세션과 대화 | 왼쪽에서 세션 선택 → **받는 세션** 확인 → 입력 후 Enter. 줄바꿈은 Shift+Enter. |
| 계속 답하는 워커 만들기 | **+ 새 세션** → 폴더·에이전트 → **워커** → 모델·추론 강도 선택. |
| Codex 속도 바꾸기 | 새 세션 또는 워커 우클릭 → **설정 변경 → 속도**에서 기본값 따름·Standard·Fast 선택. |
| 여러 에이전트와 대화 | **+ 대화방** → 멤버 선택 → **단체 대화** 켜기 → `@이름 할 일` 보내기. |
| Gemini에 코드 리뷰 요청 | [Gemini 리뷰어 설정](docs/manual.ko.md#gemini-리뷰어) 뒤 방에서 `@gemini-reviewer PR주소`로 호출. |
| 목록 정리 | 우클릭 → **즐겨찾기**. 분류 제목의 **순서 편집**에서 드래그나 ↑·↓로 조정. 분류 간 이동은 불가. |

보낸 메시지는 `<내 이름>/terminal` 이름으로 나가고 답장은 타임라인에 나타난다.
메시지를 받는 시점은 세션 종류와 작업 상태에 따라 다르며, 목록과 말풍선 아래에 표시된다.
자세한 조작은 [사용자 매뉴얼](docs/manual.ko.md)에서 찾는다.

## 대화방에서 함께 일하기

프로젝트마다 필요한 세션을 골라 방을 만든다. 일반 대화방은 대화를 모아 보는 용도이며, **단체 대화**를 켜면 에이전트끼리도 메시지를 주고받는다.

- **+ 대화방**에서 이름·멤버를 정하고 **단체 대화**를 켠다.
- `@담당자 할 일`을 보내면 그 멤버에게 전달된다. 호명이 없으면 설정한 **기본 받는 멤버**에게 간다.
- 에이전트가 답에서 다른 멤버를 `@`로 부르면 그 멤버에게도 전달된다. 1:1 대화의 멘션은 방으로 자동 전달되지 않는다.
- 한 발언 아래에 **전달 기록**이 모인다. 전달·읽음과 실제 작업 완료는 구분해서 확인한다.

수신 규칙·전달 한도·**증명 없이 먼저 보내기 허용**은 [대화방 매뉴얼](docs/manual.ko.md#rooms)에 설명했다.

## 사용 전에 알아둘 점

- **상시 응답은 워커를 쓴다.** 잠든 앱·CLI 세션은 다음 차례까지 읽지 않을 수 있다. Codex 앱이 열고 있는 대화는 밖에서 깨우지 못한다. [수신 방식](docs/manual.ko.md#delivery)
- **자동 깨우기와 단체 대화는 사용량을 쓴다.** 메시지가 전달된 에이전트마다 차례가 돈다. Fast도 사용량을 더 소모하며 속도는 모델·계정에 따라 다르다. [깨우기](docs/manual.ko.md#wake) · [Fast](docs/manual.ko.md#codex-fast)
- **전체 권한은 명령을 묻지 않고 실행한다.** 파일 삭제·설치·네트워크 접근도 포함한다. [권한과 재시작](docs/manual.ko.md#권한)
- **워커는 서버를 꺼도 계속 돈다.** 워커를 끝내려면 **워커 중지**를 쓴다. 단체 대화 중계와 자동 깨우기에는 서버가 필요하다.

이 PC를 거친 메시지만 보여 주며 서버는 `127.0.0.1`에서만 열린다. Reason DB는 읽기 전용이고, 보내기·시작·중지는 페이지 토큰을 확인한다. 비공식 도구로 Reason과는 관계가 없다.

## 필요한 문서 찾기

| 찾는 내용 | 문서 |
|---|---|
| 세션·워커·재부팅·Gemini 리뷰 | [사용자 매뉴얼: 세션 관리](docs/manual.ko.md#sessions) |
| 읽음·숨겨진 전달 기록·멘션·증명 없이 보내기 | [수신 표시](docs/manual.ko.md#delivery) · [대화방](docs/manual.ko.md#rooms) |
| 응답 실패·글자 깨짐·포트·인증서 오류 | [실패 처리](docs/manual.ko.md#recovery) · [문제 해결](docs/manual.ko.md#troubleshooting) |
| 에이전트 설치 절차·개발 규칙 | [AGENTS.md](AGENTS.md) |
| API·설정·구현 근거 | [참고 문서](docs/reference/README.ko.md) |
| 최근 변경 | [패치노트](patch_notes/README.ko.md) |

[MIT 라이선스](LICENSE)
