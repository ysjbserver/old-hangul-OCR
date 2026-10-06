# -*- coding: utf-8 -*-
"""
전사문 쪽 — 위키문헌 문법을 걷어내고 '종이에 실제로 인쇄된 글자'만 남긴다.

여기서 한 글자라도 빠지거나 더해지면 2단계 정렬이 통째로 어긋난다.
그래서 틀마다 '이건 종이에 찍혀 있나'를 하나씩 판정한다.
"""
import re

# 종이에 없거나(편집자가 넣은 표시) 본문 열 밖(여백)에 인쇄된 틀
DROP = {"절", "marginNote", "nop", "upe", "여백", "점선 요약", "목차용 점선",
        "references", "reflist", "pagequality", "-"}
LAST  = {"왼쪽 여백"}                  # {{왼쪽 여백|2em|본문}} → 본문
JOIN  = {"분주"}                       # {{분주|윗줄|아랫줄}} → 윗줄아랫줄
FIRST = {"u", "du", "wu", "물결밑줄", "밑줄", "더크게", "더더크게", "크게", "작게",
         "가운데", "복원", "SIC", "sc", "글자크기"}


def _template(name, args):
    name = name.strip()
    if name in DROP or name.startswith("왼쪽 여백/"):
        return ""
    if name in JOIN:  return "".join(args[:2])
    if name in LAST:  return args[-1] if args else ""
    if name in FIRST: return args[0] if args else ""
    return ""                          # 모르는 틀은 서식·주석으로 보고 버린다


# 표 문법 `{| … |}` (2026-10-02, 전사대조에서 협셩회회보 1쪽 `{| class="wikitable"` 이 글자로 샘).
# 칸 안의 글자는 종이에 찍힌 것이라 남기고 표시 · 속성만 걷는다. 쪽에 `{|` 가 있을 때만(머리 noinclude 에 있어도 —
# 시편촬요 0127~0129 는 표가 머리에서 열려 본문이 `|-` · `| …` 줄로만 됨). 표가 없는 쪽은 그대로.
_속성 = re.compile(r'^\s*[A-Za-z-]+\s*=')


def 표구간(t, 표):
    """표 문법 자리 → [(시작, 끝, [남길 (a, b) …]), …] (차례대로 · 겹치지 않음). `대조.인쇄글자` 도 이것을 씀."""
    if not 표:
        return []
    out = []
    for m in re.finditer(r'^[ \t]*(\{\||\|\}|\|-|\|\+|\||!)(.*)$', t, flags=re.M):
        a, b, s, 표시 = m.start(), m.end(), m.start(2), m.group(1)
        if 표시 in ("{|", "|-"):                   # 표 · 줄 속성 — 줄째
            out.append((a, b, []))
            continue
        if 표시 == "|}":                           # 표 끝 — 표시만
            out.append((a, s, []))
            continue
        칸들, p = [], s                            # 칸(`||`, 머리칸은 `!!` 도) — `속성 | 글자` 면 글자만
        for d in re.finditer(r'\|\||!!' if 표시 == "!" else r'\|\|', t[s:b]):
            칸들.append((p, s + d.start())); p = s + d.end()
        칸들.append((p, b))
        남길 = []
        for ca, cb in 칸들:
            i = t.find("|", ca, cb)
            if i >= 0 and _속성.match(t[ca:i]):
                ca = i + 1
            남길.append((ca, cb))
        out.append((a, b, 남길))
    return out


def 표있나(raw):
    return bool(re.search(r'(?<!\{)\{\|', raw))


def printed_text(t, keep_headings=False):
    """
    위키문헌 원문 → 인쇄된 글자만 이어 붙인 한 줄.

    keep_headings 는 `== 제목 ==` 을 살릴지 정한다. **문헌마다 다르다.**
      · 셩경젼셔 신약의 `== 일쟝 ==` 은 종이에 '일쟝' 이라고 찍혀 있지 않다.
        판심 위쪽에 한자 「一」 로만 있다 → 버려야 한다(기본값).
      · 시편촬요의 `== 뎨ᄉᆞ편 ==` 은 본문 열에 큰 활자로 찍혀 있다 → 살려야 한다.
    잘못 버리면 모델은 읽는데 전사문에는 없어서 그 자리가 통째로 어긋난다
    (CLAUDE.md 4번과 같은 유형의 실수).
    문헌별 설정은 `corpus.heading_printed` 가 기억한다.
    """
    표 = 표있나(t)
    t = re.sub(r'<noinclude>.*?</noinclude>', '', t, flags=re.S)
    while True:                        # 안쪽 틀부터 하나씩 푼다
        m = re.search(r'\{\{([^{}]*)\}\}', t)
        if not m:
            break
        parts = m.group(1).split("|")
        args = [a for a in parts[1:] if not re.match(r'^\s*[A-Za-z-]+\s*=', a)]
        t = t[:m.start()] + _template(parts[0], args) + t[m.end():]
    t = re.sub(r'^\s*=+\s*(.*?)\s*=+\s*$', (r'\1' if keep_headings else ''),
               t, flags=re.M)                            # 편·장 제목 (위 설명 참고)
    t = re.sub(r'^[ \t]*:+', '', t, flags=re.M)         # 줄 머리 `:` = 위키 들여쓰기(시집 · 쪽 번호 줄 — 2026-10-06, 확인한 쪽에는 0)
    t = re.sub(r"'{2,}", '', t)                          # `''기울임''` · `'''굵게'''` (증남포 장 번호 — 2026-10-06, 확인한 쪽에는 0)
    t = re.sub(r'\[\[[^|\]]*\|([^\]]*)\]\]', r'\1', t)
    t = re.sub(r'\[\[([^\]]*)\]\]', r'\1', t)
    nt, p = [], 0                                        # 표 문법 (위 `표구간`)
    for a, b, 남길 in 표구간(t, 표):
        nt.append(t[p:a]); nt.extend(t[x:y] for x, y in 남길); p = b
    t = "".join(nt) + t[p:]
    t = re.sub(r'<[^>]+>', '', t)
    return re.sub(r'[\s​]+', '', t)


def letters(s):
    """첫가끝 자모열(ᄆ+ᆞ+ᆷ)을 한 글자로 묶어 목록으로."""
    out, cur = [], ''
    for ch in s:
        o = ord(ch)
        tail = (0x1160 <= o <= 0x11FF) or (0xA960 <= o <= 0xA97F) or (0xD7B0 <= o <= 0xD7FF)
        if tail and cur:
            cur += ch
        else:
            if cur: out.append(cur)
            cur = ch
    if cur: out.append(cur)
    return out


def page_letters(path, keep_headings=False):
    """전사문 파일 → (원문, 인쇄된 글자 목록)."""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    return raw, letters(printed_text(raw, keep_headings))


# ── 첫가끝 ───────────────────────────────────────────────────────────
LBASE, VBASE, TBASE = 0x1100, 0x1161, 0x11A7


# 첫가끝으로 안 갈리는데 본문에 흔한 글자 — 채움 문자로 세 조각에 싣는다 (2026-09-26).
#   ㅣ  주격 조사 (`예수ㅣ`) — 초성 채움 + ᅵ
#   ○  절·단락 표시. 〇(숫자 0 으로 적힌 것)도 같은 모양이라 ○ 로 합친다(작업자 결정)
# 예전에는 둘 다 (빈, 빈, 빈)으로 풀려 학습에서 빠졌고, 모델이 **아예 낼 수 없었다**
# (떼어 둔 쪽 글자의 0.1~1.25%, 훈아진언이 가장 많음).
#   々  반복 부호(앞 글자를 되풀이 — `(구대소설)봉황대` 등, 순한글 문헌에도 종종). 2026-10-01 작업자 요청.
#       그 전에도 `letters` 는 한 글자로 셌으므로 글자 수 · 교정 기록은 그대로(기존 문헌 전사문에는 0개).
#   ㅅ  사이시옷(`웃음ㅅ거리` — 근대 활자본에서 따로 한 칸에 작게 찍힘). 2026-10-06 작업자 요청. 초성 ᄉ + 중성 채움이라
#       새 출력 칸 없이 이미 아는 초성 ㅅ 칸을 씀. `letters` 는 전부터 한 글자로 셌음(확인한 쪽에는 0개 — 교정 그대로).
#   ,  .  쉼표 · 마침표(근대 활자본에 반 칸쯤으로 찍힌 `、` `。` — 불상한 동무 1,428개). 2026-10-06 작업자 요청.
#       초성 자리에 부호 + 중성 채움 — 새 출력 칸 둘. 합성 글꼴로는 안 그림(가로쓰기 `,` 모양이라 — `합성글꼴.안그릴것`),
#       자동 라벨로만 배움. 확인한 쪽에는 0개. 다른 문장부호(`「」` `()` …)는 그대로 둠.
특수글자 = {"ㅣ": ("ᅟ", "ᅵ", ""),
            "○": ("○", "ᅠ", ""), "〇": ("○", "ᅠ", ""),
            "々": ("々", "ᅠ", ""),
            "ㅅ": ("ᄉ", "ᅠ", ""),
            ",": (",", "ᅠ", ""), ".": (".", "ᅠ", "")}
특수표시 = {"ᅟᅵ": "ㅣ", "○ᅠ": "○", "々ᅠ": "々", "ᄉᅠ": "ㅅ", ",ᅠ": ",", ".ᅠ": "."}     # 모델이 읽은 조각 → 보여 줄 글자


def decompose(cl):
    """글자 한 개 → (초성, 중성, 종성). 종성이 없으면 빈 문자열."""
    if cl in 특수글자:
        return 특수글자[cl]
    if len(cl) == 1 and 0xAC00 <= ord(cl) <= 0xD7A3:       # 현대 완성형은 나눗셈으로
        i = ord(cl) - 0xAC00
        return (chr(LBASE + i // 588),
                chr(VBASE + (i % 588) // 28),
                chr(TBASE + i % 28) if i % 28 else '')
    L = V = T = ''                                          # 첫가끝은 범위로 갈라낸다
    for ch in cl:
        o = ord(ch)
        if   0x1100 <= o <= 0x115F: L += ch
        elif 0x1160 <= o <= 0x11A7: V += ch
        elif 0x11A8 <= o <= 0x11FF: T += ch
    return L, V, T


def compose(L, V, T):
    """(초성, 중성, 종성) → 글자. 첫가끝으로 이어 붙인다."""
    return (L or '') + (V or '') + (T or '')
