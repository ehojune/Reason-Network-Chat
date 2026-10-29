# 패치노트

[English](README.md) · **한국어** · [中文](README.zh-CN.md)

Reason Network Chat에서 바뀐 것을 최신순으로 적는다. 시간은 한국 시간이다.
줄마다 해당 PR로 연결된다. 처음 두 커밋은 `main`에 바로 올렸다.

## 2026-10-29

| 시간 | 변경 | 주요 변경사항 |
|---|---|---|
| 15:22 | [#62](https://github.com/ehojune/Reason-Network-Chat/pull/62) | 세 언어 README 제목에 에이전트 채팅 UI 용도를 밝히고 기능 설명을 텍스트로도 표시한다. |
| 14:55 | [#60](https://github.com/ehojune/Reason-Network-Chat/pull/60) | 저장된 일괄 답변과 공동 응답을 확인하고 옛 요청의 재실행을 막습니다. |
| 13:35 | [#58](https://github.com/ehojune/Reason-Network-Chat/pull/58) | 총괄 2개와 worker 6개를 유지하면서 리뷰어도 켜도록 관리형 worker 상한을 12개로 늘렸습니다. |
| 05:05 | [#57](https://github.com/ehojune/Reason-Network-Chat/pull/57) | Gemini 리뷰어가 이름만 인용한 안내문은 요청으로 받지 않고, 모든 프롬프트에 운영 규칙을 넣으며, 제한시간을 설정할 수 있고, 실패하면 원인과 로그 경로를 알립니다. 실패 안내에서도 이미 게시한 리뷰 근거를 보존합니다. |

## 2026-10-27

| 시간 | 변경 | 주요 변경사항 |
|---|---|---|
| 17:26 | [#55](https://github.com/ehojune/Reason-Network-Chat/pull/55) | 첫 대화 전에도 Gemini 수신기를 목록에서 찾아 방에 초대할 수 있고, Gemini 배지를 보라색으로 구분합니다. |
| 16:15 | [#54](https://github.com/ehojune/Reason-Network-Chat/pull/54) | Codex 배치의 공통 전달 안내를 한 번만 담고 메시지 원문·문맥·전달 경로는 모두 보존한다. |
| 10:20 | [#53](https://github.com/ehojune/Reason-Network-Chat/pull/53) | Codex가 같은 방의 대기 메시지를 사용자 지시부터 묶어 읽도록 선택할 수 있게 하고 원문·전달 확인 기록을 보존한다. |

## 2026-10-26

| 시간 | 변경 | 주요 변경사항 |
|---|---|---|
| 21:33 | [#52](https://github.com/ehojune/Reason-Network-Chat/pull/52) | 실행 로그만 온 Codex 응답을 접이식 안내로 표시하고 자동 전달·과거 전달 재시도·대화 문맥에서 제외했다. |
| 17:23 | [#51](https://github.com/ehojune/Reason-Network-Chat/pull/51) | README에 설명을 담은 기능 카드 6개와 단체 대화방 전달 흐름 그림을 복원하고 상세 매뉴얼 분리는 유지했다. |
| 16:14 | [#50](https://github.com/ehojune/Reason-Network-Chat/pull/50) | README를 설치·첫 사용 중심으로 줄이고 세부 사용법과 에이전트 실행·API·구현 설명을 별도 문서로 옮겼다. |
| 14:50 | [#49](https://github.com/ehojune/Reason-Network-Chat/pull/49) | Codex 새 세션·설정 창에서 기본 속도·Standard·Fast를 고른다. 실시간 변경은 다음 메시지부터 적용하고 재시작 때도 유지한다. |
| 12:51 | [#48](https://github.com/ehojune/Reason-Network-Chat/pull/48) | Gemini가 전달 기록을 읽을 때 서버와 같은 잠금을 써 Windows에서도 새 방 호명 기록을 저장한다. |
| 12:00 | [#47](https://github.com/ehojune/Reason-Network-Chat/pull/47) | 방에서 Gemini 상시 리뷰어를 호명한다. PR 요청은 P0~P3 지적과 Gemini GitHub App 명의의 리뷰 링크로 돌아온다. |
| 10:41 | [#45](https://github.com/ehojune/Reason-Network-Chat/pull/45) | 분류별 순서 편집에서 손잡이 드래그나 ↑·↓로 세션을 정렬합니다. 다른 분류로는 옮길 수 없으며 새로고침 뒤에도 순서가 유지됩니다. |
| 03:38 | [#44](https://github.com/ehojune/Reason-Network-Chat/pull/44) | 글자 손상이 의심되면 전송·재전송·저장된 중계 봉투의 재시도를 막습니다. 외부 게시 전 파일 검사와 보호 범위를 안내하고 README 세 언어판에 기존 토끼 아이콘을 넣었습니다. |

## 2026-10-24

| 시간 | 변경 | 주요 변경사항 |
|---|---|---|
| 06:08 | [#43](https://github.com/ehojune/Reason-Network-Chat/pull/43) | 왼쪽 구역을 회색 접기·펼치기로 따로 숨기고 상태를 기억합니다. 긴 토끼 귀가 달린 육각형 탭 아이콘을 넣고, 즐겨찾기 worker 메뉴에 자동 수신 설명을 표시합니다. |
| 05:44 | [#41](https://github.com/ehojune/Reason-Network-Chat/pull/41) | 방에서는 원문 아래에 전달 기록을 묶어 표시합니다. 코드·인용 속 멘션은 멤버를 깨우지 않고, 같은 전달 봉투의 사본으로 온 답도 원래 방에 연결합니다. |
| 03:58 | [#39](https://github.com/ehojune/Reason-Network-Chat/pull/39) | 서버가 전송 직후 꺼져도 기록을 대조해 중복 전달을 막습니다. 결과가 불명확하면 자동 재전송 대신 확인을 기다립니다. worker 기록의 동시 저장·종료·모델 감지와 방 신원·목록 갱신 검증도 보완했습니다. |
| 03:18 | [#36](https://github.com/ehojune/Reason-Network-Chat/pull/36) | **멤버가 방에 먼저 보내기**: `rnc.py room send`로 예약 보고도 먼저 올립니다. 사람이 깨우는 메시지를 보낼 필요가 없습니다. Windows·Linux·macOS 발신 확인과 재시작 뒤 방별 허용 설정을 지원합니다. |
| 03:02 | [#38](https://github.com/ehojune/Reason-Network-Chat/pull/38) | 실패·미응답 알림에 **보기** 추가: 원문·수신자·실패 사유를 확인하고 개별 처리합니다. 인용은 원문으로 이동하고 답 없는 확인은 접습니다. Markdown 링크·목록 코드와 사용량 한도 알림의 전달 반복도 고쳤습니다. |
| 02:47 | [#35](https://github.com/ehojune/Reason-Network-Chat/pull/35) | **멈춘 워커를 알아본다**(30분 넘게 단계가 바뀌지 않는 작업 중 워커). 오른쪽 클릭 메뉴에서 그 아래 도는 프로세스를 보고 같은 설정으로 **다시 시작**한다. 에이전트는 **`python rnc.py worker start/restart/stop/adopt`**로 워커를 다룬다. 에이전트가 자기 턴 안에서 워커를 띄우는 일이 다시 없게 하려는 것이다. |
| 02:41 | [#31](https://github.com/ehojune/Reason-Network-Chat/pull/31) | **워커의 실패를 답으로 넘기지 않는다**(실패한 워커끼리 30초 만에 36번 주고받은 적이 있다). 빨간 안내로 보이고, 내 메시지에 **다시 보내기**가 붙는다. 워커가 읽고 답하지 않은 메시지도 표시하고, 보내기 칸 위 줄에 모아 **모두 다시 보내기**를 준다. |
| 01:55 | [#30](https://github.com/ehojune/Reason-Network-Chat/pull/30) | 넘긴 답(↪ …의 답을 넘김 →)에 **넘긴 내용이 보인다.** 표시 아래에 첫 몇 줄이 뜨고, 누르면 서식대로 전부 펼쳐진다. 표시만 덩그러니 있던 받은 멤버의 1:1 화면에서도 그렇다. |
| 01:40 | [#29](https://github.com/ehojune/Reason-Network-Chat/pull/29) | **1:1과 방을 구분한다.** 단체 대화방 멤버에게 1:1로 쓰면 보내기 칸 위에 1:1 안내와 방 링크가 뜨고, 에이전트에게는 답의 @가 넘어가지 않는다는 안내 한 줄이 붙는다. 멤버의 1:1 답에 다른 멤버 @가 있으면 **방으로 전달**로 방에서 답한 것처럼 한 번 넘긴다. |
| 01:25 | [#28](https://github.com/ehojune/Reason-Network-Chat/pull/28) | 단체 대화방에서 **멤버의 답이 물어본 멤버에게 `@` 없이도 돌아간다**(한 단계만이라 두 에이전트가 인사를 끝없이 주고받지 않는다). `-`나 `(해당 없음)`은 답이 없다는 뜻이라 아무에게도 안 간다. 메시지의 **↩**로 인용을 달아 작성자에게 답한다. 작업 중에 멈춘 워커는 바쁨이 아니라 *중지됨 (네트워크 표시만 남음)*으로 나온다. |
| 00:51 | [#25](https://github.com/ehojune/Reason-Network-Chat/pull/25) | 워커의 **마지막 설정을 재부팅 뒤에도 기억한다.** 꺼진 워커도 "cli" 대신 codex / claude-code 표시를 유지하고, **다시 시작**(하나, 대화방 단위, 전체)으로 같은 모델·추론 강도·권한으로 한 번에 되살린다. 워커의 하위 세션은 목록에서 접는다. |
| 00:41 | [#22](https://github.com/ehojune/Reason-Network-Chat/pull/22) | 메시지를 **마크다운**으로 보여 준다. 표(말풍선 안에서 스크롤), 굵게·기울임, 코드, 목록, 제목, 인용, 링크. 말풍선 아래 **원문**을 누르면 쓴 그대로 보인다. |
| 00:34 | [#20](https://github.com/ehojune/Reason-Network-Chat/pull/20) | 이 페이지가 띄웠지만 목록에서 빠진 워커를 **다시 데려온다**(30초마다 돌고 있는 프로세스에서 찾음). 그래서 Claude 워커도 다시 **설정 변경**이 된다. 다른 곳에서 띄운 워커는 확인을 거쳐 이 페이지에서 관리할 수 있다. |
| 00:25 | [#19](https://github.com/ehojune/Reason-Network-Chat/pull/19) | **단체 대화의 넘겨주기를 버리지 않는다.** 대화방 한도를 넘으면 대기열에서 순서대로 나가고(**지금 모두 보내기**로 바로), 한도는 대화방마다 정하며(기본 100번·10분에 300통, 또는 제한 없음), 서버를 다시 켜는 사이 온 답도 넘긴다. **메시지는 @로 부른 멤버에게만 간다**(`@모두`는 전체, 또는 기본 받는 멤버). 누가 받는지 보여 주고 `@` 뒤에 이름을 추천한다. |

## 2026-10-23

| 시간 | 변경 | 주요 변경사항 |
|---|---|---|
| 23:44 | [#18](https://github.com/ehojune/Reason-Network-Chat/pull/18) | 이미 쓰는 포트에서는 두 번째 서버가 뜨지 않는다. Windows에서 포트를 독점으로 잡아, 새 서버는 옛 서버와 몰래 포트를 나눠 쓰는 대신 "Port 8765 is in use"로 끝난다. |
| 23:31 | [#17](https://github.com/ehojune/Reason-Network-Chat/pull/17) | 세션을 시작할 때 **권한**(기본, 또는 확인을 거친 전체 권한)을 고르고, 돌고 있는 워커의 **모델·추론 강도·권한을 우클릭 메뉴에서 바꾼다**. Codex 모델 변경은 다음 메시지부터 적용되고, 나머지는 같은 이름으로 다시 시작한다. Claude 워커의 추론 강도가 이제 실제로 적용된다. |
| 22:07 | [#16](https://github.com/ehojune/Reason-Network-Chat/pull/16) | **깨우지 않기**(`--fyi`)로 보낸 안 읽은 메시지에 "바로 받음" 대신 *깨우지 않고 보냄 · 다음 차례에 읽음*이 나온다. 이런 메시지는 원래 바로 전달되지 않는다. |
| 21:41 | [#15](https://github.com/ehojune/Reason-Network-Chat/pull/15) | 화살표 뒤 받는 세션 앞에도 에이전트 표시(codex, claude-code 등)가 붙는다. |
| 21:39 | [#14](https://github.com/ehojune/Reason-Network-Chat/pull/14) | 메시지가 오면 Codex 세션을 **자동으로 깨운다**(우클릭 → 자동 깨우기 켜기). 에이전트끼리 사람 없이 주고받는다. Codex 차례를 자동으로 쓰며, 세션마다 1분에 한 번·시간당 12번까지다. Codex 앱이 열고 있는 대화는 깨우지 못하고 표시만 한다. |
| 19:01 | [#13](https://github.com/ehojune/Reason-Network-Chat/pull/13) | 페이지에서 잠든 Codex 세션을 **깨운다**. 그 세션의 대화에서 한 차례(`codex exec resume`)를 돌려 안 읽은 메시지를 읽고 답하게 한다. **보낸 뒤 깨우기**로도 된다. |
| 18:53 | [#12](https://github.com/ehojune/Reason-Network-Chat/pull/12) | 목록과 대화 사이 경계선을 끌어(포커스 후 ←/→도 됨) 목록 폭을 바꾼다. 폭은 서버가 기억하고, 두 번 누르면 원래대로 돌아간다. |
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
