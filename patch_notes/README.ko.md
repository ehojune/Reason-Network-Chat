# 패치노트

[English](README.md) · **한국어** · [中文](README.zh-CN.md)

Reason Network Chat에서 바뀐 것을 최신순으로 적는다. 시간은 한국 시간이다.
줄마다 해당 PR로 연결된다. 처음 두 커밋은 `main`에 바로 올렸다.

## 2026-10-23

| 시간 | 변경 | 주요 변경사항 |
|---|---|---|
| 18:48 | [#11](https://github.com/ehojune/Reason-Network-Chat/pull/11) | 세션이나 대화방을 오른쪽 클릭(또는 Shift+F10)해 즐겨찾기로 목록 맨 위에 고정한다. 즐겨찾기는 서버가 저장한다. |
| 18:45 | [#10](https://github.com/ehojune/Reason-Network-Chat/pull/10) | 세션마다 메시지가 어떻게 닿는지(바로 답함, 다음 차례에 읽음, 오프라인 …)를 목록, **받는 세션**, 안 읽은 말풍선 아래에 쉬운 말로 적는다. 오프라인·기록 세션은 기본으로 숨기고, 오프라인 세션에 보낼 때는 한 번 묻는다. |
| 18:42 | [#9](https://github.com/ehojune/Reason-Network-Chat/pull/9) | 업데이트 전에 켠 서버를 만난 페이지가 스크립트 오류로 멈추지 않고 "서버를 다시 시작하세요"를 띄운다. 빠진 필드가 있어도 깨지지 않는다. |
| 17:40 | [#5](https://github.com/ehojune/Reason-Network-Chat/pull/5) | 단체 대화: 참여 세션끼리도 서로의 말을 듣고, 답에 `@이름`을 쓰면 그 세션에게 넘어간다. 에이전트끼리 끝없이 주고받지 않도록 연쇄·빈도 한도를 뒀다. |
| 17:40 | [#4](https://github.com/ehojune/Reason-Network-Chat/pull/4) | **+ 대화방**으로 몇몇 세션을 묶는다. 그 세션들의 메시지만 보이고, 한 번 보내면 모두에게 간다. |
| 17:40 | [#3](https://github.com/ehojune/Reason-Network-Chat/pull/3) | **+ 새 세션**으로 페이지에서 에이전트를 띄운다. 폴더와 에이전트를 고르면 그 에이전트가 직접 주는 모델·강도 목록이 뜨고, 네트워크 워커나 터미널 창으로 연다. 메시지로 깨어나지 않는 Codex 세션에는 표시를 달고, 같은 폴더에 워커를 바로 여는 버튼을 붙였다. |
| 17:32 | [#2](https://github.com/ehojune/Reason-Network-Chat/pull/2) | 패치노트를 영어·한국어·중국어로 만들고 README마다 맨 위 배지로 연결했다. |
| 16:43 | [#1](https://github.com/ehojune/Reason-Network-Chat/pull/1) | 이름을 Reason Network Chat으로 바꿨다(`ehojune/Reason-Network-Chat`). 카드 1과 소개 문구가 "Claude, Codex 같은 여러 에이전트"를 가리킨다. |
| 16:15 | [`1b3162c`](https://github.com/ehojune/Reason-Network-Chat/commit/1b3162c) | `/api/send`가 크기 제한이 있는 JSON만 받는다. 늦게 온 폴링 응답이 새 응답을 덮어쓰지 않는다. |
| 16:10 | [`634dc50`](https://github.com/ehojune/Reason-Network-Chat/commit/634dc50) | 첫 공개: 이 PC를 오가는 Reason Network 메시지를 채팅방 하나에 모으고 보내기 칸을 달았다. |
