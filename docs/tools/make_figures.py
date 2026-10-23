"""Generate the README figures in ko/en/zh: python docs/tools/make_figures.py

Writes docs/how-it-works.<lang>.svg, docs/screen.<lang>.svg and docs/why/<lang>/card-<n>.svg.
Edit the TEXT table and rerun; never hand-edit the SVGs.
"""
from pathlib import Path
from xml.sax.saxutils import escape as x

DOCS = Path(__file__).resolve().parents[1]
FONT = ('"Noto Sans KR", "Noto Sans SC", "Apple SD Gothic Neo", "PingFang SC", "Segoe UI", '
        '"Malgun Gothic", "Microsoft YaHei", sans-serif')
MONO = '"Consolas", "Menlo", monospace'
C = {"claude": "#C96442", "codex": "#2563EB", "agent": "#7C3AED", "cli": "#0F766E", "me": "#C96442",
     "busy": "#D97706", "idle": "#16A34A", "off": "#A3A3A3", "ink": "#1F2328", "sub": "#57606A", "line": "#D0D7DE"}

TEXT = {
    "ko": {
        "cards": [
            ("한 방에서 본다", "Claude, Codex 같은 여러 에이전트", "대화를 타임라인 하나로"),
            ("누가 일하는지 보인다", "작업 중인지 대기 중인지,", "무슨 일을 하는지 왼쪽에"),
            ("여기서 바로 보낸다", "보내기 칸이 reason network", "send를 대신 불러 준다"),
            ("읽기만, 이 PC에서만", "DB는 읽기 전용으로 열고", "127.0.0.1에만 묶인다"),
        ],
        "flow": ("에이전트 세션", "Reason Network 데몬", "Reason Network Chat", "읽기: SQLite 읽기 전용 + who --json",
                 "보내기: reason network send", "Claude 데스크톱 Browser pane 또는 아무 브라우저"),
        "busy": "작업 중", "idle": "대기", "gone": "종료됨", "all": "전체 대화", "online": "접속 중",
        "history": "기록에만 남은 세션", "send": "보내기", "to": "받는 세션", "me": "나",
        "ph": "메시지 (Enter 보내기)",
        "msgs": ["결제 webhook이 5xx에 재시도해?", "응, 지수 백오프로 3번. retry.ts 42행 참고.",
                 "README 설치 표 갱신 부탁해", "갱신했어. 3줄 바뀜."],
        "day": "2026년 10월 23일 (금)", "read": "읽음", "others": "다른 에이전트",
    },
    "en": {
        "cards": [
            ("One room", "Claude, Codex and other agents", "in one timeline"),
            ("See who's busy", "Busy or idle, and what each", "session is doing right now"),
            ("Reply from here", "The send box runs", "reason network send for you"),
            ("Read-only, local", "Opens the database read-only,", "listens on 127.0.0.1 only"),
        ],
        "flow": ("Agent sessions", "Reason Network daemon", "Reason Network Chat", "read: SQLite read-only + who --json",
                 "send: reason network send", "Claude desktop Browser pane, or any browser"),
        "busy": "busy", "idle": "idle", "gone": "gone", "all": "All messages", "online": "Online",
        "history": "History only", "send": "Send", "to": "To", "me": "me",
        "ph": "Message (Enter to send)",
        "msgs": ["Does the billing webhook retry on 5xx?", "Yes, 3 times with backoff. See retry.ts:42.",
                 "Please update the install table in the README", "Done, 3 lines changed."],
        "day": "Fri, October 23, 2026", "read": "read", "others": "Other agents",
    },
    "zh": {
        "cards": [
            ("一个房间看全部", "Claude、Codex 等智能体", "的消息汇成一条时间线"),
            ("谁在忙一目了然", "工作中还是空闲、", "正在做什么，都在左栏"),
            ("就地发送", "发送框替你调用", "reason network send"),
            ("只读，仅限本机", "数据库以只读方式打开，", "只监听 127.0.0.1"),
        ],
        "flow": ("智能体会话", "Reason Network 守护进程", "Reason Network Chat", "读取：SQLite 只读 + who --json",
                 "发送：reason network send", "Claude 桌面版 Browser pane 或任意浏览器"),
        "busy": "工作中", "idle": "空闲", "gone": "已结束", "all": "全部消息", "online": "在线",
        "history": "仅在记录中", "send": "发送", "to": "发送给", "me": "我",
        "ph": "输入消息（Enter 发送）",
        "msgs": ["支付 webhook 遇到 5xx 会重试吗？", "会，指数退避重试 3 次，见 retry.ts:42。",
                 "请更新 README 里的安装表格", "已更新，改了 3 行。"],
        "day": "2026年10月23日 周五", "read": "已读", "others": "其他智能体",
    },
}


def tw(s, size):
    """Rough text width: CJK glyphs are square, Latin about 0.56 em."""
    return sum(size if ord(ch) > 0x2E80 else size * 0.56 for ch in s)


ARROWS = {"claude": "#C96442", "codex": "#2563EB", "agent": "#7C3AED", "green": "#1A7F37"}
MARKERS = "\n".join(
    f'    <marker id="a-{k}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" '
    f'orient="auto-start-reverse"><path d="M0 0l10 5-10 5z" fill="{v}"/></marker>' for k, v in ARROWS.items())


def svg(w, h, title, desc, body, lang):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="t d" xml:lang="{lang}">
  <title id="t">{x(title)}</title>
  <desc id="d">{x(desc)}</desc>
  <style>
    text {{ font-family: {FONT}; fill: {C["ink"]}; }}
    .h {{ font-size: 22px; font-weight: 700; letter-spacing: -.3px; }}
    .l {{ font-size: 15px; fill: {C["sub"]}; }}
    .n {{ font-size: 14px; font-weight: 700; fill: #FFFFFF; }}
    .m {{ font-family: {MONO}; font-size: 11px; font-weight: 700; fill: {C["sub"]}; }}
    .w {{ font-size: 11px; font-weight: 700; fill: #FFFFFF; }}
    .s {{ font-size: 12px; fill: {C["sub"]}; }}
    .b {{ font-size: 13px; }}
    .t {{ font-size: 14px; font-weight: 700; }}
  </style>
  <defs>
{MARKERS}
  </defs>
{body}
</svg>
'''


def pill(xc, y, label, fill, w=None):
    w = w or tw(label, 11) + 16
    return (f'<rect x="{xc - w / 2:.1f}" y="{y}" width="{w:.1f}" height="18" rx="9" fill="{fill}"/>'
            f'<text class="w" x="{xc}" y="{y + 13}" text-anchor="middle">{x(label)}</text>')


def card(n, lang):
    t = TEXT[lang]
    head, l1, l2 = t["cards"][n - 1]
    bg, stroke, blob, num = [("#FFF9E8", "#E3B341", "#FFF0BE", "#9A6700"), ("#F0F6FF", "#79A8F2", "#DCEBFF", "#1F6FEB"),
                             ("#F0FAF3", "#6CC08B", "#D8F2E0", "#1A7F37"), ("#F6F8FA", "#D0D7DE", "#EAEEF2", "#57606A")][n - 1]
    parts = [f'<rect x=".5" y=".5" width="479" height="259" rx="18" fill="{bg}" stroke="{stroke}"/>',
             f'<circle cx="380" cy="130" r="92" fill="{blob}"/>',
             f'<circle cx="42" cy="74" r="14" fill="{num}"/><text class="n" x="42" y="79" text-anchor="middle">{n}</text>',
             f'<text class="h" x="28" y="128">{x(head)}</text>',
             f'<text class="l" x="28" y="164">{x(l1)}</text><text class="l" x="28" y="188">{x(l2)}</text>']
    if n == 1:  # three agents flow into one window
        for i, (k, label) in enumerate([("claude", "claude"), ("codex", "codex"), ("agent", "agent")]):
            y = 62 + i * 52
            parts.append(f'<rect x="262" y="{y}" width="52" height="24" rx="12" fill="{C[k]}"/>'
                         f'<text class="w" x="288" y="{y + 16}" text-anchor="middle">{label}</text>'
                         f'<path d="M318 {y + 12}C334 {y + 12} 334 130 350 130" fill="none" stroke="{C[k]}" stroke-width="2"/>')
        parts.append('<rect x="352" y="40" width="112" height="180" rx="10" fill="#FFFFFF" stroke="#57606A" stroke-width="2"/>'
                     '<circle cx="366" cy="54" r="3.5" fill="#CF222E"/><circle cx="378" cy="54" r="3.5" fill="#D4A72C"/>'
                     '<circle cx="390" cy="54" r="3.5" fill="#1A7F37"/><path d="M352 66h112" stroke="#D0D7DE"/>')
        for i, (k, w, right) in enumerate([("claude", 70, False), ("codex", 62, False), ("me", 56, True), ("agent", 74, False)]):
            y = 78 + i * 34
            xx = 452 - w if right else 364
            parts.append(f'<rect x="{xx}" y="{y}" width="{w}" height="24" rx="10" fill="{"#F0E6DC" if right else "#FFFFFF"}" stroke="#D0D7DE"/>'
                         f'<rect x="{xx + 6}" y="{y + 10}" width="6" height="6" rx="3" fill="{C[k]}"/>'
                         f'<path d="M{xx + 18} {y + 13}h{w - 28}" stroke="#8C959F" stroke-width="3" stroke-linecap="round"/>')
    elif n == 2:  # session list with status dots
        parts.append('<rect x="290" y="38" width="174" height="184" rx="10" fill="#FFFFFF" stroke="#57606A" stroke-width="2"/>')
        rows = [("api-claude", "claude", "busy", t["busy"]), ("web-codex", "codex", "idle", t["idle"]),
                ("docs-agent", "agent", "idle", t["idle"]), ("ask-3f2a", "cli", "off", t["gone"])]
        for i, (name, k, s, label) in enumerate(rows):
            y = 52 + i * 42
            parts.append(f'<circle cx="306" cy="{y + 8}" r="5" fill="{C[s]}"/>'
                         f'<text class="m" x="318" y="{y + 12}" style="fill:{C["ink"]}">{name}</text>'
                         f'<rect x="318" y="{y + 19}" width="34" height="13" rx="3" fill="{C[k]}"/>'
                         f'<path d="M358 {y + 26}h{40 if s == "busy" else 26}" stroke="#D0D7DE" stroke-width="3" stroke-linecap="round"/>'
                         + pill(456 - max(40, tw(label, 11) + 14) / 2, y, label, C[s], max(40, tw(label, 11) + 14)))
    elif n == 3:  # send box, then the agent's answer comes back
        parts.append('<rect x="300" y="40" width="150" height="34" rx="12" fill="#FFFFFF" stroke="#D0D7DE"/>'
                     f'<rect x="310" y="51" width="38" height="13" rx="3" fill="{C["codex"]}"/>'
                     '<path d="M354 57h84" stroke="#8C959F" stroke-width="3" stroke-linecap="round"/>'
                     '<rect x="340" y="92" width="110" height="34" rx="12" fill="#F0E6DC" stroke="#D0D7DE"/>'
                     '<path d="M352 109h86" stroke="#8C959F" stroke-width="3" stroke-linecap="round"/>'
                     '<rect x="282" y="176" width="134" height="36" rx="10" fill="#FFFFFF" stroke="#57606A" stroke-width="2"/>'
                     '<text class="m" x="294" y="198">reason network send</text>'
                     '<rect x="422" y="176" width="40" height="36" rx="10" fill="#1A7F37"/>'
                     '<path d="M434 194h16M444 188l6 6-6 6" fill="none" stroke="#FFFFFF" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
                     '<path d="M442 170C442 150 430 140 410 132" fill="none" stroke="#1A7F37" stroke-width="2" stroke-dasharray="4 3" marker-end="url(#a-green)"/>'
                     '<path d="M330 92C318 86 316 80 318 78" fill="none" stroke="#2563EB" stroke-width="2" marker-end="url(#a-codex)"/>')
    else:  # read-only and localhost only
        parts.append('<path d="M380 44l58 22v52c0 40-26 68-58 82-32-14-58-42-58-82V66z" fill="#FFFFFF" stroke="#57606A" stroke-width="2.5" stroke-linejoin="round"/>'
                     '<rect x="360" y="116" width="40" height="32" rx="6" fill="#57606A"/>'
                     '<path d="M368 116v-10a12 12 0 0 1 24 0v10" fill="none" stroke="#57606A" stroke-width="5"/>'
                     '<circle cx="380" cy="130" r="4" fill="#FFFFFF"/><path d="M380 132v8" stroke="#FFFFFF" stroke-width="3"/>'
                     + pill(380, 214, "127.0.0.1", "#1F6FEB", 92) + pill(424, 40, "mode=ro", "#1A7F37", 70)
                     + pill(306, 40, "stdlib", "#57606A", 56))
    return svg(480, 260, head, f"{head}: {l1} {l2}", "\n".join("  " + p for p in parts), lang)


def flow(lang):
    a, d, r, read, send, pane = TEXT[lang]["flow"]
    p = [f'<rect x=".5" y=".5" width="879" height="299" rx="18" fill="#FFFFFF" stroke="#D0D7DE"/>',
         f'<text class="t" x="100" y="42" text-anchor="middle">{x(a)}</text>']
    for i, (k, name) in enumerate([("claude", "Claude Code"), ("codex", "Codex"), ("agent", TEXT[lang]["others"])]):
        y = 62 + i * 64
        p.append(f'<rect x="24" y="{y}" width="152" height="48" rx="10" fill="#F6F8FA" stroke="#D0D7DE"/>'
                 f'<rect x="24" y="{y}" width="8" height="48" rx="4" fill="{C[k]}"/>'
                 f'<text class="b" x="46" y="{y + 29}" style="font-weight:700">{name}</text>'
                 f'<path d="M180 {y + 24}C204 {y + 24} 204 150 224 150" fill="none" stroke="{C[k]}" stroke-width="2" marker-end="url(#a-{k})"/>')
    p.append(f'<rect x="230" y="70" width="200" height="160" rx="14" fill="#F0F6FF" stroke="#79A8F2"/>'
             f'<text class="t" x="330" y="100" text-anchor="middle">{x(d)}</text>'
             '<ellipse cx="330" cy="134" rx="54" ry="11" fill="#FFFFFF" stroke="#1F6FEB" stroke-width="2"/>'
             '<path d="M276 134v52c0 6 24 11 54 11s54-5 54-11v-52" fill="#FFFFFF" stroke="#1F6FEB" stroke-width="2"/>'
             '<text class="m" x="330" y="170" text-anchor="middle">network.db</text>'
             '<text class="m" x="330" y="186" text-anchor="middle">(SQLite)</text>')
    p.append(f'<rect x="660" y="70" width="196" height="160" rx="14" fill="#F0FAF3" stroke="#6CC08B"/>'
             f'<text class="t" x="758" y="100" text-anchor="middle">{x(r)}</text>'
             '<text class="m" x="758" y="118" text-anchor="middle">127.0.0.1:8765</text>'
             '<rect x="668" y="130" width="180" height="84" rx="8" fill="#FFFFFF" stroke="#57606A" stroke-width="1.5"/>'
             '<path d="M710 130v84" stroke="#D0D7DE"/>'
             '<circle cx="680" cy="146" r="3.5" fill="#D97706"/><circle cx="680" cy="162" r="3.5" fill="#16A34A"/><circle cx="680" cy="178" r="3.5" fill="#16A34A"/>'
             '<path d="M688 146h14M688 162h14M688 178h14" stroke="#8C959F" stroke-width="3" stroke-linecap="round"/>'
             '<rect x="720" y="140" width="70" height="16" rx="6" fill="#F6F8FA" stroke="#D0D7DE"/>'
             '<rect x="764" y="162" width="74" height="16" rx="6" fill="#F0E6DC" stroke="#D0D7DE"/>'
             '<rect x="720" y="184" width="60" height="16" rx="6" fill="#F6F8FA" stroke="#D0D7DE"/>')
    p.append(f'<path d="M434 126H652" stroke="#1A7F37" stroke-width="2.5" marker-end="url(#a-green)"/>'
             f'<text class="s" x="543" y="116" text-anchor="middle">{x(read)}</text>'
             f'<path d="M652 178H438" stroke="#C96442" stroke-width="2.5" marker-end="url(#a-claude)"/>'
             f'<text class="s" x="543" y="198" text-anchor="middle">{x(send)}</text>'
             f'<text class="s" x="856" y="258" text-anchor="end">{x(pane)}</text>'
             '<path d="M758 234v8" stroke="#8C959F" stroke-width="2"/>')
    return svg(880, 300, f"Reason Network Chat — {d}", f"{a} → {d} → {r}. {read}. {send}.", "\n".join("  " + q for q in p), lang)


def screen(lang):
    t = TEXT[lang]
    p = ['<rect x=".5" y=".5" width="879" height="439" rx="14" fill="#F7F7F5" stroke="#D0D7DE"/>',
         '<path d="M14 .5h206v438H14a13.5 13.5 0 0 1-13.5-13.5V14A13.5 13.5 0 0 1 14 .5z" fill="#FFFFFF" stroke="#D0D7DE"/>',
         '<text class="t" x="18" y="32">Reason Network Chat</text><text class="s" x="18" y="52">My network</text>',
         '<path d="M1 64h219" stroke="#E4E3DF"/>',
         f'<rect x="8" y="72" width="204" height="30" rx="8" fill="#E8E2D8"/><circle cx="22" cy="87" r="4" fill="#16A34A"/>'
         f'<text class="b" x="34" y="92" style="font-weight:700">{x(t["all"])}</text><text class="s" x="200" y="92" text-anchor="end">4</text>',
         f'<text class="s" x="16" y="124" style="font-size:11px">{x(t["online"])}</text>']
    rows = [("api-refactor-claude", "claude-code", "claude", "busy", t["busy"]),
            ("billing-codex", "codex", "codex", "idle", t["idle"]), ("docs-agent", "agent", "agent", "idle", t["idle"])]
    for i, (name, ag, k, s, sub) in enumerate(rows):
        y = 134 + i * 46
        p.append(f'<circle cx="22" cy="{y + 8}" r="4" fill="{C[s]}"/><text class="b" x="34" y="{y + 13}" style="font-weight:700">{name}</text>'
                 f'<rect x="34" y="{y + 20}" width="{tw(ag, 10) + 10:.0f}" height="15" rx="4" fill="{C[k]}"/>'
                 f'<text class="w" x="39" y="{y + 31}" style="font-size:10px">{ag}</text>'
                 f'<text class="s" x="{44 + tw(ag, 10) + 6:.0f}" y="{y + 32}">{x(sub)}</text>')
    p.append(f'<text class="s" x="16" y="286" style="font-size:11px">{x(t["history"])}</text>'
             '<g opacity=".55"><circle cx="22" cy="304" r="4" fill="#A3A3A3"/><text class="b" x="34" y="309" style="font-weight:700">ask-3f2a</text>'
             f'<rect x="34" y="316" width="27" height="15" rx="4" fill="{C["cli"]}"/><text class="w" x="39" y="327" style="font-size:10px">cli</text>'
             f'<text class="s" x="68" y="328">{x(t["gone"])}</text></g>')
    p.append(f'<path d="M220 52h659" stroke="#E4E3DF"/><text class="t" x="238" y="32">{x(t["all"])}</text>'
             f'<text class="s" x="550" y="76" text-anchor="middle">{x(t["day"])}</text>')
    msgs = [("claude", "claude-code", "api-refactor-claude", "billing-codex", t["msgs"][0], False),
            ("codex", "codex", "billing-codex", "api-refactor-claude", t["msgs"][1], False),
            ("me", t["me"], "terminal", "docs-agent", t["msgs"][2], True),
            ("agent", "agent", "docs-agent", "terminal", t["msgs"][3], False)]
    y = 92
    for i, (k, ag, frm, to, body, me) in enumerate(msgs):
        w = tw(body, 13) + 26
        meta = f"{frm} → {to} · 16:0{i}"
        mw = tw(ag, 10) + 10 + 6 + tw(meta, 12)
        bx = 864 - w if me else 238
        mx = 864 - mw if me else 240
        p.append(f'<rect x="{mx:.0f}" y="{y}" width="{tw(ag, 10) + 10:.0f}" height="15" rx="4" fill="{C[k]}"/>'
                 f'<text class="w" x="{mx + 5:.0f}" y="{y + 11}" style="font-size:10px">{x(ag)}</text>'
                 f'<text class="s" x="{mx + tw(ag, 10) + 16:.0f}" y="{y + 12}">{x(meta)}</text>'
                 f'<rect x="{bx:.0f}" y="{y + 20}" width="{w:.0f}" height="32" rx="14" fill="{"#F0E6DC" if me else "#FFFFFF"}" stroke="#E4E3DF"/>'
                 f'<text class="b" x="{bx + 13:.0f}" y="{y + 41}">{x(body)}</text>')
        y += 66
    p.append('<path d="M220 360h659" stroke="#E4E3DF"/><rect x="220.5" y="360.5" width="658" height="78" fill="#FFFFFF"/>'
             f'<text class="s" x="236" y="381">{x(t["to"])}</text>'
             f'<rect x="{244 + tw(t["to"], 12):.0f}" y="368" width="150" height="20" rx="6" fill="#F7F7F5" stroke="#E4E3DF"/>'
             f'<text class="s" x="{252 + tw(t["to"], 12):.0f}" y="382">billing-codex (codex)</text>'
             '<rect x="234" y="396" width="560" height="32" rx="8" fill="#F7F7F5" stroke="#E4E3DF"/>'
             f'<text class="s" x="246" y="416">{x(t["ph"])}</text>'
             f'<rect x="802" y="396" width="64" height="32" rx="8" fill="#C96442"/>'
             f'<text class="w" x="834" y="416" text-anchor="middle" style="font-size:13px">{x(t["send"])}</text>')
    return svg(880, 440, "Reason Network Chat", "Example screen with sample data: sessions on the left, chat bubbles on the right, send box at the bottom.",
               "\n".join("  " + q for q in p), lang)


def main():
    for lang in TEXT:
        (DOCS / "why" / lang).mkdir(parents=True, exist_ok=True)
        for n in range(1, 5):
            (DOCS / "why" / lang / f"card-{n}.svg").write_text(card(n, lang), encoding="utf-8", newline="\n")
        (DOCS / f"how-it-works.{lang}.svg").write_text(flow(lang), encoding="utf-8", newline="\n")
        (DOCS / f"screen.{lang}.svg").write_text(screen(lang), encoding="utf-8", newline="\n")
    print("figures written under", DOCS)


if __name__ == "__main__":
    main()
