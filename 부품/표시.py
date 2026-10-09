# -*- coding: utf-8 -*-
"""
읽은 글자에 확신 표시(⟪⟫)를 붙이고 열마다 한 줄 글월로 — torch 없이 불러올 수 있음.
브라우저판 짝: `읽기.js` 의 `확신표시` · `줄글월`.
"""
import unicodedata


def as_text(seq):
    """사람이 읽기 좋게. 현대 글자는 완성형으로 합쳐 준다."""
    return unicodedata.normalize("NFC", "".join(seq))


안쪽, 바깥 = "⟪", "⟫"          # 옛한글 전사문에 안 나오는 글자라야 지우기 쉽다
표시문턱 = 0.93                 # 확신이 이보다 낮으면 ⟪⟫ — 설정.json '표시문턱' 으로 브라우저판도 씀


def 확신표시(hyp, conf, 문턱=표시문턱, 빈=None):
    """
    확신이 낮은 글자를 `⟪…⟫` 로 감싼 글월과, 감싼 글자 수.
    빈[k] 가 참이면 그 글자 뒤를 띄움(⟪⟫ 는 빈칸을 감싸지 않음).
    """
    조각, 셀, 켬 = [], 0, False
    for k, (ch, c) in enumerate(zip(hyp, conf)):
        낮 = c < 문턱
        if 낮 and not 켬:
            조각.append(안쪽); 켬 = True
        elif not 낮 and 켬:
            조각.append(바깥); 켬 = False
        조각.append(ch); 셀 += 낮
        if 빈 and 빈[k]:                 # 띄어쓰기 — ⟪⟫ 는 빈칸을 감싸지 않는다
            if 켬:
                조각.append(바깥); 켬 = False
            조각.append(" ")
    if 켬:
        조각.append(바깥)
    return as_text(조각), 셀


def 띄운글(hyp, 빈=None):
    """글자들을 이어 붙이되 빈[k] 가 참인 글자 뒤를 띄운다."""
    return as_text([ch + (" " if 빈 and 빈[k] else "") for k, ch in enumerate(hyp)])


def 줄글월(줄들, 문턱=표시문턱):
    """
    열마다 한 줄로 — 원문의 줄바꿈을 살린다. `align.read_page_lines` 의 결과를 받는다
    ((글자, 확신) 또는 띄어쓰기까지 (글자, 확신, 빈칸) — `띄움=True`).
    반환: (표시 없는 글월, ⟪⟫ 표시한 글월, 표시한 글자 수)

    표시는 줄마다 따로 붙인다(⟪…⟫ 가 줄을 넘지 않게).
    """
    글, 표, 셀 = [], [], 0
    for 줄 in 줄들:
        hyp, conf = 줄[0], 줄[1]
        빈 = 줄[2] if len(줄) > 2 else None
        s, n = 확신표시(hyp, conf, 문턱, 빈)
        글.append(띄운글(hyp, 빈)); 표.append(s); 셀 += n
    return "\n".join(글), "\n".join(표), 셀
