# -*- coding: utf-8 -*-
"""
전사문 — 위키문헌 문법을 걷어내고 종이에 인쇄된 글자만 남긴다.
"""
import re

# 버리는 틀 — 종이에 없거나 본문 열 밖(여백)에 인쇄됨
DROP = {"절", "marginNote", "nop", "upe", "여백", "점선 요약", "목차용 점선",
        "references", "reflist", "pagequality", "-"}
LAST  = {"왼쪽 여백"}                  # {{왼쪽 여백|2em|본문}} → 본문
JOIN  = {"분주"}                       # {{분주|윗줄|아랫줄}} → 윗줄아랫줄
FIRST = {"u", "du", "wu", "물결밑줄", "밑줄", "더크게", "더더크게", "더더더크게", "더더더더크게",   # 첫 인자 = 본문(서식만 입힘)
         "크게", "작게", "가운데", "복원", "SIC", "sc", "글자크기",
         "C", "Sic", "쌍밑줄", "할주", "*", "오른쪽", "세로쓰기", "머리글자 장식",
         "드러냄표", "가늘게", "내어쓰기", "다크 모드 반전"}
# 일부러 안 넣음(버림): `오른쪽 띄우기` · `더작게` · `더더작게` · `?` · `앵커` · `분수` · 숫자 인자 틀
SECOND = {"색상", "배경색상", "배경 색상"}   # {{색상|white|本義}} → 本義
SPACED = {"자간"}                          # {{자간|2em|군|말}} → 군말 (둘째 · 셋째 인자)


def 틀이름(name):
    """MediaWiki 처럼 맞춘 틀 이름 — 밑줄 = 빈칸, 첫 글자 대소문자 무시(`sic` = `Sic`, `du` = `Du`)."""
    n = re.sub(r'[\s_]+', ' ', name).strip()
    return n[:1].upper() + n[1:]


_표 = {}


def 남길인자(name, n):
    """틀 하나 → 남길 인자 번호 목록(인자 n 개). `대조._틀남길것` 도 이것을 씀."""
    if not _표:                        # 처음 부를 때 이름을 맞춰 둠(표를 고치면 `_표.clear()`)
        for 이름, 표 in (("DROP", DROP), ("LAST", LAST), ("JOIN", JOIN), ("FIRST", FIRST),
                       ("SECOND", SECOND), ("SPACED", SPACED)):
            _표[이름] = {틀이름(x) for x in 표}
    k = 틀이름(name)
    if k in _표["DROP"] or k.startswith("왼쪽 여백/"):
        return []
    if k in _표["JOIN"]:   return list(range(min(n, 2)))
    if k in _표["LAST"]:   return [n - 1] if n else []
    if k in _표["FIRST"]:  return [0] if n else []
    if k in _표["SECOND"]: return [1] if n > 1 else []
    if k in _표["SPACED"]: return list(range(1, min(n, 3)))
    return []                          # 모르는 틀은 서식·주석으로 보고 버린다


def _template(name, args):
    return "".join(args[i] for i in 남길인자(name, len(args)))


# 표 문법 `{| … |}` — 칸 글자는 남기고 표시 · 속성만 걷음. 쪽에 `{|` 가 있을 때만.
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

    keep_headings: `== 제목 ==` 을 살릴지(문헌 설정 `corpus.heading_printed`).
    ⚠ `대조.인쇄글자` 에 같은 정규식 — 고치면 둘 다.
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
               t, flags=re.M)                            # 편·장 제목
    t = re.sub(r'^[ \t]*:+', '', t, flags=re.M)         # 줄 머리 `:` = 위키 들여쓰기
    t = re.sub(r"'{2,}", '', t)                          # `''기울임''` · `'''굵게'''`
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


# 첫가끝으로 안 갈리는 글자 — 채움 문자로 세 조각에 싣는다(〇 → ○). 읽기.js `모델.글자` 짝.
특수글자 = {"ㅣ": ("ᅟ", "ᅵ", ""),
            "○": ("○", "ᅠ", ""), "〇": ("○", "ᅠ", ""),
            "々": ("々", "ᅠ", ""),
            "ㅅ": ("ᄉ", "ᅠ", ""),
            ",": (",", "ᅠ", ""), ".": (".", "ᅠ", "")}
# 칸을 차지하지만 결과에는 안 낼 부호 — 쉼표 칸(`,`)에 묶어 배우고 읽은 결과에서는 뺀다(`align.PUNCT_DROP`).
부호묶음 = ("(", ")", "「", "」", "【", "】", "｢", "｣")
부호묶기 = True       # False 면 묶지 않음(빈 조각 → 학습에서 빠짐)
# 환경 변수 OCR_부호묶기=0 이면 끔(학습 자식 프로세스까지 넘기려고)
import os as _os
if _os.environ.get("OCR_부호묶기") == "0":
    부호묶기 = False
특수표시 = {"ᅟᅵ": "ㅣ", "○ᅠ": "○", "々ᅠ": "々", "ᄉᅠ": "ㅅ", ",ᅠ": ",", ".ᅠ": "."}     # 모델이 읽은 조각 → 보여 줄 글자


def decompose(cl):
    """글자 한 개 → (초성, 중성, 종성). 종성이 없으면 빈 문자열."""
    if cl in 특수글자:
        return 특수글자[cl]
    if 부호묶기 and cl in 부호묶음:
        return 특수글자[","]
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
