# -*- coding: utf-8 -*-
"""
쪽 하나를 처리하는 한 줄기 — 이미지와 전사문에서 '상자 + 라벨'까지.

2단계(데이터셋 만들기)와 교정서버가 똑같이 이 함수를 쓴다.
두 곳이 서로 다르게 자르면 교정한 것이 데이터셋에 안 맞게 되기 때문이다.
"""
import os

import numpy as np
from PIL import Image

import scan, corpus
from wikitext import page_letters
import align

MIN_LETTERS = 50        # 이보다 적으면 표지·목차 같은 쪽으로 보고 건너뛴다


def doc_ratio(slug):
    """
    그 문헌의 세로/가로 자간 비율. 처음 쓸 때 그림만 보고 한 번 재서 기억해 둔다.
    전사문도 사람 손도 필요 없다 — 새 문헌을 가져와도 그냥 돌아간다.

    ⚠ 표본을 `corpus.images` 에서 뽑는다(`pages` 가 아니라). **전사문이 없는
      문헌에서도 재야 하기 때문**이다 — `읽기.py` 참고. 아래 `doc_tiers`·
      `doc_layout` 도 같다.
    """
    r = corpus.doc_ratio(slug)
    if r:
        return r
    paths = [t[2] for t in corpus.sample(corpus.images(slug), 6)]
    r = scan.estimate_ratio(paths, doc_tiers(slug))   # 판형을 먼저 알아야 한다
    if not r:
        return None
    corpus.save_ratio(slug, r)
    print(f"[{slug}] 세로/가로 자간 비율을 {r:.3f} 으로 쟀습니다 (그림만 보고, 한 번만).")
    return r


def doc_tiers(slug):
    """
    이 문헌은 한 쪽이 몇 단인가. 자간과 똑같이 **처음 쓸 때 그림만 보고 한 번**
    재서 기억한다. 거의 모든 문헌이 1 단이라 아무것도 달라지지 않는다.

    쪽마다 판단하지 않고 문헌마다 정하는 까닭은 `corpus.doc_tiers` 의 설명 참고.

    ★ 먼저 **가름줄 판형**인지 본다(`scan.가름줄판정`, 2026-09-26). 그렇으면
    정수 대신 가름줄 높이 목록을 돌려준다 — 단 수와 상관없이(셩경 개역 두 단,
    독립신문 세 단) 단마다 열을 따로 찾는 갈래를 탄다. 셩경 개역은 이것으로
    예전 두 단 갈래보다 낫다(떼어 둔 쪽 3.4% → 2.6%, 다른 79쪽 7.0% → 4.7%).
    아니면 예전 판정(가운데 가로줄 하나)을 해서 1 또는 2.
    ⚠ 한 단 문헌 일곱은 가름줄 판정에 한 번도 안 걸린다(문헌마다 40쪽으로 확인).
    """
    n = corpus.doc_tiers(slug)
    if n:
        return n
    가름잰 = [scan.가름줄측정(t[2]) for t in corpus.sample(corpus.images(slug), 12)]
    단잰 = [scan.tier_measure(t[2]) for t in corpus.sample(corpus.images(slug), 8)]
    n, 설명 = 판형정하기(가름잰, 단잰)
    if 설명 is None:
        return n                       # 못 재면 적어 두지 않고 보통 판형으로
    corpus.save_tiers(slug, n)
    print(f"[{slug}] {설명}")
    return n


def 판형정하기(가름잰것들, 단잰것들):
    """
    `doc_tiers` 의 판정 — 쪽마다 잰 것 → (판형, 설명). 못 정하면 설명이 None.
    가름잰것들 = `scan.가름줄측정` 들, 단잰것들 = `scan.tier_measure` 들(못 잰 쪽은 None).
    브라우저판 `판형정하기` 와 짝이다 — `브라우저판/대조뽑기.py` 가 이것으로 정답을 낸다.
    """
    가름 = scan.가름줄정하기(가름잰것들)
    if 가름:
        return tuple(가름), (f"가로줄로 {len(가름)+1}단을 가른 판형으로 봅니다 "
                            f"(가름줄 높이 {', '.join(f'{p:.2f}' for p in 가름)}).")
    got = [v for v in 단잰것들 if v]
    if len(got) < scan.최소쪽(len(단잰것들)):     # 보통 4쪽 — 쪽이 적은 파일은 있는 만큼
        return 1, None
    합의 = float(np.median([v[0] for v in got]))
    자리 = np.array([v[1] for v in got])
    흔들림 = float(np.median(np.abs(자리 - np.median(자리))))
    # 두 가지를 함께 본다 — **진하기**(열들이 합의하는가)와 **자리의 한결같음**.
    # 하나만 보면 갈리지 않는다. 실측(쪽 8개씩):
    #   셩경 개역   합의 0.58 · 흔들림 0.005   ← 두 단
    #   셩경젼셔    합의 0.14 · 흔들림 0.01    ← 자리는 고른데 줄이 없다
    #   시편촬요    합의 0.09 · 흔들림 0.18
    n = 2 if (합의 >= 0.40 and 흔들림 <= 0.02) else 1
    return n, (f"한 쪽이 {n}단인 판형으로 봅니다 "
               f"(가운데 가로줄 합의 {합의:.2f} · 자리 흔들림 {흔들림:.3f}, 그림 {len(got)}쪽).")


def doc_layout(slug):
    """
    이 문헌의 표준 판짜임 {"자간": px, "열수": n}. 자간 비율·판형과 똑같이
    **처음 쓸 때 한 번** 재서 기억한다(`교정/_판짜임.json`).

    쪽 20개를 훑어 **중앙값**을 쓴다. 앞머리(0001~0004)는 판형이 진짜로 달라
    크게 벗어나지만 중앙값이라 섞여도 괜찮다.
    """
    v = corpus.doc_layout(slug)
    if v:
        return v
    잰 = []
    for t in corpus.sample(corpus.images(slug), 20):
        xp, cols = scan.find_columns(np.array(Image.open(t[2]).convert("L")))
        잰.append((xp, len(cols)) if xp and cols else None)
    v = 판짜임정하기(잰)
    if v is None:
        return None                     # 못 재면 적어 두지 않는다
    corpus.save_layout(slug, v["자간"], v["열수"])
    return v


def 판짜임정하기(잰것들):
    """
    `doc_layout` 의 판정 — 쪽마다 (열 자간, 열 수) 또는 None → {"자간", "열수"}, 8쪽 못 되면 None.
    브라우저판 `판짜임정하기` 와 짝이다(처음 보는 파일에서 소도구가 부름, 2026-10-01).
    ⚠ '가장 많이 모인 무리(±5%)의 중앙값' 도 재 봤으나 이득이 없어 접음(2026-10-01) — 권2 는 열 간격이
      책 앞 110~115 · 뒤 97~106 으로 고르게 퍼져 두 규칙 다 104~107 을 냄. 다른 일곱 문헌은 같음.
    """
    got = [v for v in 잰것들 if v]
    if len(got) < 8:
        return None
    return {"자간": float(np.median([v[0] for v in got])),
            "열수": int(np.median([v[1] for v in got]))}


읽기배율 = (0.88, 0.94, 1.00, 1.06, 1.12, 1.18, 1.24)


def doc_read_ratio(slug, mdl=None):
    """
    **전사문 없이 읽을 때 쓰는 자간.** 적혀 있으면 그것, 없으면 **모델 확신도로
    골라** 적어 둔다(`교정/_자간.json` 의 `_읽기자간`).

    ★ 왜 필요한가 — 읽기 자간은 CER 을 크게 가릅니다(훈아진언 **9%p**). 그런데
    지금까지 이 값을 정하는 도구(`step2_cut.py 자간`, `실험7_읽기자간.py`)는
    **전사문을 필요로 했습니다.** 정작 이 도구가 가장 쓰이려는 자리 —
    **전사문이 없는 새 문헌** — 에는 넣을 방법이 없었습니다.

    ★ 어떻게 전사문 없이 고르나 — 자간을 여러 값으로 바꿔 읽어 보고 **모델이
    가장 자신 있어 한 값**을 고릅니다. `align.read_page` 가 열마다 칸 수를
    고르는 것과 같은 얼개입니다. 실측(문헌 여섯, 쪽 8개씩) — 참값(CER 이 고른
    값)과 **최대 0.6%p** 차이고 셋은 정확히 같습니다:

    | 문헌 | 확신이 고름 | CER 이 고름 |
    |---|---|---|
    | 시편촬요 · 셩경젼셔 신약 · 요한복음 | 같음 | 같음 |
    | 셩경 개역 | ×1.06 (4.2%) | ×1.00 (4.1%) |
    | 구약 권2 | ×1.06 (25.4%) | ×0.94 (24.9%) |
    | 훈아진언 | ×1.12 (23.0%) | ×1.00 (22.4%) |

    ⚠ **이미 적힌 값은 건드리지 않습니다.** 사람이 전사문으로 잰 값이 있으면
      그것이 낫습니다.
    """
    r = corpus.read_ratio(slug)
    if r:
        return r
    바탕 = doc_ratio(slug)
    if not 바탕 or mdl is None:
        return 바탕
    # ⚠ **전사문이 있으면 자동 추정을 쓰지 않는다.** 전사문으로 재는
    #   `step2_cut.py 자간` · `실험7_읽기자간.py` 가 낫다. 확신도 기준은 쪽
    #   표본에 따라 흔들려서, 바탕값이 이미 옳은 문헌을 잘못 건드릴 수 있다 —
    #   요한복음에서 ×1.12 로 잘못 골라 12.9% → 14.7% 가 됐다.
    if corpus.pages(slug):
        return 바탕
    import align as _align
    단 = doc_tiers(slug)
    # ⚠ **쓸 만한 쪽만 본다.** `corpus.images` 에는 앞머리(표지·목차)가 섞여
    #   있는데 그 쪽들은 애초에 '못씀' 이라 확신도가 판단을 흐린다. 걸러내지
    #   않고 재 봤더니 셩경젼셔 신약이 ×0.94, 구약 권2 가 ×1.12 로 잘못
    #   골라져 성적이 12.4% → 12.5% 로 나빠졌다(권2 일치는 75% → 36%).
    후보 = [t for t in corpus.sample(corpus.images(slug), 30)
            if 쪽건강(slug, scan.page_geometry(t[2], 바탕, 단))[0] == "좋음"]
    골라 = corpus.sample(후보, 6) or corpus.sample(corpus.images(slug), 6)
    최고, 고른, 기준 = None, 바탕, None
    for m in 읽기배율:
        점 = []
        for _, pg, ip in 골라:
            geo = scan.page_geometry(ip, 바탕 * m, 단, True)
            if geo is None:
                continue
            hyp, conf = _align.read_page(mdl, geo)
            if hyp:
                점 += list(np.log(np.clip(conf, 1e-6, None)))
        if 점:
            v = float(np.mean(점))
            if m == 1.0:
                기준 = v
            if 최고 is None or v > 최고:
                최고, 고른 = v, 바탕 * m
    # **바탕값보다 뚜렷이 나을 때만** 바꾼다. 근소한 차이로 옮기면 손해다 —
    # CLAUDE.md '자간' 절의 "읽기 자간은 참값에서 벗어나면 손해입니다" 참고.
    if 기준 is not None and 최고 is not None and 최고 - 기준 < 0.02:
        고른 = 바탕
    corpus.save_read_ratio(slug, 고른)
    print(f"[{slug}] 읽기 자간을 {고른:.4f} 로 정했습니다 "
          f"(바탕 {바탕:.4f} 의 {고른/바탕:.2f}배 — 전사문 없이 확신도로).")
    return 고른


def 쪽건강(slug, geo, 표준=None):
    """
    **이 쪽이 제대로 잘렸는가.** 전사문 없이 판정한다.
    반환: (등급, [까닭…])   등급은 "좋음" · "의심" · "못씀".

    ⚠ **'잘 잘렸는가' 만 봅니다. '얼마나 잘 읽었는가' 는 여기서 보지 마세요** —
    둘은 다른 물음이고, 섞으면 같은 쪽이 경로에 따라 다르게 판정됩니다.
    실제로 2026-09-09 에 확신도를 여기 넣었다가, 시편촬요가 `step4_read`
    에서는 전부 '의심'인데 `성적재기` 의 문헌 표에서는 98% '좋음'으로 나오는
    모순이 생겼습니다. 시편촬요는 **잘 잘리는데 읽기가 어려운** 문헌입니다.
    → 읽기 쪽은 `step4_read` 의 '확신낮음' 칸과 `확신표시` 가 맡습니다.

    ★ 왜 필요한가 — 이 도구의 쓰임은 '사람이 결과를 보고 고치는 것'이다.
    그때 가장 나쁜 것은 **어느 쪽을 믿을지 모르는 것**이다. 200쪽을 받았는데
    그중 30쪽이 쓰레기면 사람은 200쪽을 다 검토해야 한다. 미리 갈라 주면
    **못 쓰는 쪽은 건너뛰고 처음부터 치면 된다.**

    ⚠ **CER 을 낮추는 것보다 이것이 실전에서 클 수 있습니다.** 2026-09-09 에
      재 보니 권2 는 쪽의 18%, 신약젼셔는 20% 가 제대로 안 잘립니다. 그것을
      고치는 것(`find_columns` 다시 짜기)은 성적표로 −0.3%p 뿐인데, 표시만
      붙이면 사람이 그 18% 를 피해 갈 수 있습니다.

    무엇을 보는가 (전부 전사문 없이 알 수 있는 것):
      · 열을 아예 못 찾음                     → 못씀
      · 자간이 문헌 표준에서 25% 넘게 벗어남  → 못씀 (열이 붙거나 빠진 것)
      · 열 수가 문헌 표준에서 25% 넘게 벗어남 → 의심

    slug 가 None 이면 문헌 표준을 `표준`({"자간", "열수"} — `판짜임정하기` 의 값)으로 받음
    (Toolforge 서버 — `data/` 없이 파일마다 잰 값, 2026-10-07). 둘 다 없으면 열을 찾았는지만 봄.
    """
    까닭 = []
    if geo is None or not geo.get("cols"):
        return "못씀", ["열을 찾지 못했습니다"]
    if slug is not None:
        표준 = doc_layout(slug)
    if 표준:
        # ⚠ 두 단 판형은 `page_geometry` 가 열을 두 배로 늘려 놓는다(셩경 개역
        #   20 → 40). `doc_layout` 은 늘리기 전을 재므로 여기서 되돌려야 한다.
        #   안 그러면 그 문헌의 **모든 쪽이 '의심'** 이 된다. 실제로 당했다.
        xp = geo.get("xpitch")
        n = len(geo["cols"]) // max(int(geo.get("단", 1)), 1)
        # ⚠ 읽는 경로에는 가장자리 후보 열이 붙어 있다(`scan._가장자리후보`).
        #   `doc_layout` 과 같은 잣대(판심만 뗀 열 수)로 센다.
        n = geo.get("본열수", n)
        if xp and abs(xp - 표준["자간"]) > 표준["자간"] * 0.25:
            까닭.append(f"열 간격이 이 문헌 표준과 다릅니다"
                        f" ({xp:.0f} 대 {표준['자간']:.0f})")
            return "못씀", 까닭
        if 표준["열수"] and abs(n - 표준["열수"]) > 표준["열수"] * 0.25:
            까닭.append(f"열이 {n}개입니다 (이 문헌은 보통 {표준['열수']}개)")
    return ("의심" if 까닭 else "좋음"), 까닭


def geometry(slug, ip, 읽기=False, 가장자리=True, 이어=None, 끝띠=None, 판심=None):
    """
    그 문헌의 자간 비율과 판형(몇 단인가)을 반영해 쪽 기하를 구한다.

    읽기=True 는 **전사문 없이 읽을 때(4단계)** 를 뜻한다. 그때만 쓰는 자간이
    따로 적혀 있으면 그것을 쓴다(`corpus.read_ratio` 의 설명 참고).
    적혀 있지 않으면 보통 자간을 쓰므로, 대부분의 문헌은 아무것도 달라지지 않는다.

    ⚠ **읽을 때만 하는 것이 둘 있습니다. 자를 때 하면 오히려 나빠집니다.**
      ① 가장자리 열 가리기 — 판심을 떼지 않고 양 끝에 후보 열을 붙인 뒤
         (`scan._가장자리후보`) **모델 확신도로** 가린다(`align.가장자리다듬기`).
         2026-09-25 부터 `테두리열버리기` 를 대신한다(11.4% → 9.7%).
      ② 광곽 **경계**를 안쪽까지 바짝 잡기 — `scan.page_frame` 의 ★★.
         (읽기 17.7% → 14.4%. 자르기에 쓰면 학습이 14.4% → 16.2% 로 망가집니다.)
    """
    단 = doc_tiers(slug)                  # 자간보다 먼저 — 자간을 단 나눈 뒤에 잰다
    r = (읽기 and corpus.read_ratio(slug)) or doc_ratio(slug)
    # 읽을 때는 문헌 표준 열 간격도 넘긴다 — 열 찾기가 흐린 쪽에서 문턱을 고를 때 씀
    # (`scan.find_columns` 의 ★ 표준자간, 2026-09-26)
    표준 = (doc_layout(slug) or {}).get("자간") if 읽기 and SCAN_PITCH else None
    return (scan.page_geometry(ip, r, 단, 읽기, 가장자리, 표준, 이어=이어, 끝띠=끝띠, 판심=판심) if r
            else scan.page_geometry(ip, 단=단, 읽기=읽기, 가장자리=가장자리, 표준자간=표준, 이어=이어, 끝띠=끝띠, 판심=판심))


SCAN_PITCH = True    # 읽을 때 문헌 표준 열 간격을 열 찾기에 넘기는가
TEDURI = 1.6        # 잉크가 다른 열 중앙값의 이 배를 넘으면 광곽(테두리) 선으로 본다


def 테두리열버리기(geo, 배수=TEDURI):
    """
    **광곽(테두리) 선이 열로 잡힌 것을 버린다.** (2026-09-07, 자르기는 09-08)

    ⚠⚠ **2026-09-25 부터 읽는 경로에서도 쓰지 않습니다.** 잉크 양만 보므로
      **제본 쪽 그림자**가 진 진짜 본문 열을 테두리로 알고 버렸습니다(구약 권2
      0088 · 0146 · 0668 · 권1 0361 — 쪽 꼬리나 머리가 열 하나씩 통째로 빠짐).
      지금은 `align.가장자리다듬기` 가 **모델 확신도로** 가립니다(11.4% → 9.7%).
      아래 기록은 '왜 테두리 열을 읽을 때 빼야 하는가' 의 근거로 남겨 둡니다 —
      그 까닭은 그대로 맞고, 가리는 잣대만 바뀌었습니다.

    무슨 일이 있었나 — 훈아진언 0031쪽은 본문 열이 11개인데 `find_columns` 가
    12개를 찾았습니다. 마지막 하나는 **왼쪽 광곽 선**이고, 새까매서 잉크가 두세
    배입니다:

        잉크비  0.44 0.46 0.42 0.50 0.39 0.40 0.38 0.45 0.45 0.53 0.53 **1.00**
        열간격   139  143  142  147  141  135  142  137  142  133  **97**

    왜 지금까지 안 걸렸나 — `align.to_text`(자를 때)에는 **열을 통째로 버리는
    선택지**(칸수 0)가 있어 저절로 넘어갑니다(그냥 넘어가는 것이 아니라
    **적극적으로 이 열을 골라 버립니다** — 아래 '자르는 경로에 넣어
    보았습니다'). 그런데 `align.read_page`(읽을 때)는
    **`allow_empty=False`** 라 버릴 수가 없어, 그 새까만 띠를 26칸쯤으로 잘라
    글자로 읽어 냅니다. **쪽마다 가짜 글자 20~30개**입니다.

    걸리는 쪽 비율이 성적과 그대로 맞아떨어집니다 —
    훈아진언 78% · 구약 권2 71% · 시편촬요 64% (가장 나쁜 셋),
    요한복음 16% · 셩경젼셔 신약 0% (가장 좋은 둘).

    떼어 둔 쪽에서 잰 이득(재학습 없음, `python 실험/실험9_테두리열.py`):
    훈아진언 −5.0%p · 시편촬요 −4.5%p · 구약 권2 −3.7%p · 구약 권1 −1.9%p ·
    요한복음 −1.7%p · 신약젼셔·셩경젼셔 신약 **소수점까지 그대로**.

    ⚠⚠ **자르는 경로에 넣어 보았습니다 — 넣지 마세요** (2026-09-08 실측)

    `to_text` 는 총 글자 수를 맞춰야 하는데 `est` 가 크게 부풀어 있어(아래)
    **열 하나를 통째로 버려야만 답이 나오는 쪽**이 많습니다. 그때 테두리 열이
    바로 그 **제물**이 되어 주고 있었습니다. 미리 빼 버리면 DP 가 **진짜 열**을
    제물로 삼습니다:

        시편촬요 0044 — 열 16 × 짐작 24 = 384칸, 전사는 303자.
                        span 3 이면 열마다 21~27 이라 15열의 최소 합계가 315.
                        303 을 맞추려면 열 하나를 0 으로 버려야 합니다.
          테두리 있을 때: 0번(테두리)을 버림           → 일치 **71%**
          미리 빼면:      10번(진짜 본문 열)을 버림     → 일치 **18%**

    떼어 둔 쪽의 일치 중앙값(자르기 자간, span 3):
        시편촬요 67% → **48%** · 훈아진언 60% → **48%**   (나빠짐)
        구약 권2 43% → 71% · 구약 권1 82% → 85%           (좋아짐)
        셩경젼셔 신약·요한복음·신약젼셔 — 그대로

    ⚠ **읽는 경로에서 이득이 나는 것과 모순이 아닙니다.** `read_page` 는
      `allow_empty=False` 라 제물을 삼을 수가 없어 테두리를 그냥 읽습니다.
      그래서 **읽을 때는 미리 빼 주는 것이 옳고, 자를 때는 DP 에게 맡기는 것이
      옳습니다.** 두 경로가 일부러 다릅니다.

    ⚠ **'첫 열·끝 열만' 규칙도 자르기에서는 무너집니다.** 구약 권2 0164쪽은
      진짜 테두리가 **15번**(잉크 1397 대 중앙값 360 = 3.9배)이고 그 밖에 본문
      열이 하나 더 있습니다. 그런데 이 규칙은 0번(1.62배 — 문턱을 겨우 넘은
      **진짜 본문 열**)을 버립니다. 읽는 경로에서는 그래도 이득이 났지만
      우연입니다.

    → **뿌리는 `est` 부풀림입니다**(`scan.spans_between` 이 광곽 선을 글자
      잉크로 셈 — CLAUDE.md '다음에 할 일'). 시편촬요는 열마다 24 로 짐작하는데
      참값은 19~20 입니다. 그것을 고치면 제물을 삼을 일이 없어지고, 이 고침을
      자르기에 넣어도 손해가 없어질 것입니다. **순서가 거꾸로였습니다.**

    참고 — 걱정했던 `교정/` 무효화는 실제로 세어 보니 **0쪽**이었습니다
    (`python 실험/실험9_테두리열.py --교정영향`). 자르기에 넣지 않기로 한 까닭은
    교정이 아니라 위의 제물 문제입니다.

    ⚠ **첫 열·끝 열만 봅니다.** 그러지 않으면 큰 활자로 찍힌 편 제목 열처럼
      **진짜 본문 열**을 버릴 수 있습니다. 광곽은 늘 쪽 가장자리에 있습니다.
    ⚠ **문턱은 1.3~1.9 가 평평하고 양쪽에서 나빠집니다**(1.0 은 진짜 열을 버려
      셩경젼셔가 2.5% → 11.7%, 2.4 이상은 테두리를 놓침). 그 가운데를 잡았습니다.
    ⚠ **두 단 판형(셩경 개역)에서는 부르지 않습니다.** `page_geometry(단=2)` 는
      같은 x 자리를 위·아래로 두 번 쓰므로 열 번호를 빼면 단 짝이 어긋납니다.
      그 문헌은 애초에 이 문제가 없습니다.
    """
    v, n = [], len(geo["cols"])
    if n < 4:
        return geo
    g = np.array(geo["image"])            # 이미 열어 둔 그림을 다시 씁니다
    prof = scan.ink_profile(g, geo["cols"])
    for i, p in enumerate(prof):
        sp = geo["spans"][i]
        w = max(1, geo["cols"][i][1] - geo["cols"][i][0])
        v.append(float(p[sp[0]:sp[1]].sum()) / w if sp else 0.0)
    med = float(np.median(v))
    버릴 = {i for i in (0, n - 1) if v[i] > med * 배수}
    if not 버릴:
        return geo
    남 = [i for i in range(n) if i not in 버릴]
    새 = dict(geo)
    for k in ("cols", "crop_cols", "spans", "sm", "est"):
        새[k] = [geo[k][i] for i in 남]
    return 새


def letters_of(slug, tp):
    """그 문헌의 '제목이 인쇄되는가' 설정을 반영해 전사 글자를 읽는다."""
    return page_letters(tp, corpus.heading_printed(slug))


def usable(ip, tp):
    """이 쪽을 쓸 수 있는지만 빠르게 본다(교정서버가 목록을 만들 때)."""
    raw, letters = letters_of(corpus.slug_of(ip), tp)
    if len(letters) < MIN_LETTERS or "분주" in raw:
        return False
    return scan.page_geometry(ip) is not None


def 교정옮기기(fix, boxes, auto):
    """
    상자가 바뀐 쪽에 옛 교정을 옮겨 붙인다(2026-09-28).

    좌표가 옛 상자와 같은(`corpus.BOX_TOL` 안) 새 상자는 옛 교정의 글자·뺀 칸을 그대로 받고,
    달라진 상자는 '바뀐 칸' 으로 돌려준다 — 사람이 보기 전에는 학습에 넣지 않는다.
    바뀐 칸의 글자는 앞뒤 옮긴 칸 사이에 남은 글자 수와 칸 수가 같으면 차례대로, 아니면 자동 정렬(`auto`) 값.
    ⚠ **겹침(IoU)으로 옮기지 마세요.** 새 모델로 잰 18쪽에서 좌표가 같은 상자는 옮긴 라벨이 모델과 95% 맞는데
      (자동 정렬 79%), 반쯤 겹친 상자는 17% — 달라진 상자는 대개 옛 상자가 **둘로 쪼개지거나 합쳐진** 자리입니다.
    반환: (assign, excluded, 바뀐칸)
    """
    ob, oa, oex = fix["boxes"], fix["assign"], set(fix.get("excluded", []))
    tol = corpus.BOX_TOL
    assign, excluded, 바뀐 = [], set(), []
    for j, b in enumerate(boxes):
        k = next((k for k, o in enumerate(ob)
                  if all(abs(int(p) - int(q)) <= tol for p, q in zip(b, o))), None)
        if k is None:
            assign.append(None); 바뀐.append(j)
        else:
            assign.append(oa[k])
            if k in oex:
                excluded.add(j)
    # 바뀐 칸이 이어진 구간마다 글자를 채운다
    j = 0
    while j < len(assign):
        if assign[j] is not None:
            j += 1; continue
        e = j
        while e < len(assign) and assign[e] is None:
            e += 1
        앞 = next((assign[t] for t in range(j - 1, -1, -1) if assign[t] is not None and assign[t] >= 0), -1)
        뒤 = next((assign[t] for t in range(e, len(assign)) if assign[t] is not None and assign[t] >= 0), None)
        n = e - j
        if 뒤 is not None and 뒤 - 앞 - 1 == n:
            for t in range(n):
                assign[j + t] = 앞 + 1 + t
        else:
            for t in range(j, e):
                assign[t] = auto[t]
        j = e
    return assign, excluded, 바뀐


def _교정점(mdl, geo, r, letters):
    """교정의 짝으로 보라 점을 찍는다(모델이 읽은 글자와 라벨이 다른 칸)."""
    from wikitext import decompose
    import align
    pL, pV, pT, _ = mdl.read(geo["image"], align._맞춤상자(np.asarray(geo["image"]), r["boxes"], geo))
    rL, rV, rT = mdl.codes(letters, decompose)
    return [bool(0 <= a < len(letters) and i not in r["excluded"] and rL[a] >= 0
                 and not (pL[i] == rL[a] and pV[i] == rV[a] and pT[i] == rT[a]))
            for i, a in enumerate(r["assign"])]


def prepare(slug, page, ip, tp, mdl=None, span=3, use_fix=True, 경계=False, 이어=None):
    """
    반환: dict(letters, boxes, assign, mark, conf, 일치, 모름, note, fixed) 또는
          dict(사유="…") — 쓸 수 없는 쪽
    교정을 옮겨 붙인 쪽은 fixed=False · 옮김=True · 미확인={바뀐 칸} (`교정옮기기`).
    """
    raw, letters = letters_of(slug, tp)
    if len(letters) < MIN_LETTERS:
        return dict(사유="글자가 너무 적음")
    if "분주" in raw:
        return dict(사유="분주(두 줄 협주)가 있어 열 구조가 다름")

    geo = geometry(slug, ip, 이어=이어)        # 이어=True 는 자동 라벨만(`scan.page_geometry`)
    if geo is None:
        return dict(사유="열을 못 찾음")

    r = align.to_text(mdl, geo, letters, span=span, 경계=경계)   # 경계=True 는 자동 라벨만(`align.to_text`)
    if r.get("사유"):
        return r

    fix = corpus.load_fix(slug, page, len(letters)) if use_fix else None
    # 교정 파일은 있는데 못 쓰는 경우 = 전사문이 그 뒤로 바뀌었다는 뜻
    r["fix_stale"] = bool(use_fix and fix is None and
                          os.path.exists(corpus.fix_path(slug, page)))
    # 교정을 할 때 본 상자와 지금 상자가 같을 때만 쓴다 — 상자 **수**는 늘 같으므로 좌표로 가린다
    # (2026-09-27 — `corpus.same_boxes`. 좌표가 없는 옛 교정도 쓰지 않는다)
    fixed = bool(fix and len(fix["assign"]) == len(r["boxes"])
                 and corpus.same_boxes(fix.get("boxes"), r["boxes"]))
    # 글자 수는 맞는데 상자가 달라진 경우 = 자르는 방식이나 모델이 바뀌었다는 뜻
    r["fix_unused"] = bool(fix and not fixed)
    r["옮김"], r["미확인"] = False, set()
    if fixed:
        r["assign"] = list(fix["assign"])
        r["excluded"] = set(fix.get("excluded", []))
        # 보라 점도 **교정의 짝**으로 다시 찍는다 — 예전에는 자동 정렬의 짝으로 찍힌 점이 그대로 남아,
        # 교정이 있는 쪽을 다시 열면 점이 화면의 라벨과 상관없는 자리를 가리켰다(2026-09-27).
        if mdl is not None:
            r["mark"] = _교정점(mdl, geo, r, letters)
    elif fix and fix.get("boxes"):
        # 상자가 바뀐 쪽 — 좌표가 같은 상자에는 옛 교정을 옮겨 붙이고, 바뀐 칸만 보라 점으로(2026-09-28)
        r["assign"], r["excluded"], 바뀐 = 교정옮기기(fix, r["boxes"], r["assign"])
        r["옮김"], r["미확인"] = True, set(바뀐)
        if mdl is not None:
            r["mark"] = _교정점(mdl, geo, r, letters)
        for i in 바뀐:
            r["mark"][i] = True
    else:
        r["excluded"] = set()

    r["letters"] = letters
    r["fixed"] = fixed
    r["image"] = geo["image"]
    if r["일치"] is None:
        r["note"] = f"전사 {len(letters)}자 · 상자 {len(r['boxes'])}개 · 모델 없이 기하로만 자름"
    else:
        r["note"] = (f"전사 {len(letters)}자 · 상자 {len(r['boxes'])}개 · "
                     f"아는 글자와 {r['일치']:.0%} 일치")
        if r["모름"]:
            r["note"] += f" · 모델이 모르는 글자 {r['모름']}자"
    if fixed:
        r["note"] += " · 저장된 교정 적용됨"
    elif r["옮김"]:
        r["note"] += (f" · ⚠ 그때와 상자가 {len(r['미확인'])}칸 달라졌습니다 — 나머지 "
                      f"{len(r['boxes']) - len(r['미확인'])}칸은 저장된 교정을 옮겨 붙였으니, "
                      f"바뀐 칸(보라 점)만 보고 저장해 주세요")
    elif r["fix_unused"]:
        r["note"] += " · ⚠ 저장된 교정이 있지만 그때와 상자가 달라 쓰지 않았습니다 — 다시 확인해 주세요"
    return r


def pairs(r):
    """학습에 쓸 (상자, 글자) 짝만 골라낸다."""
    # 교정을 옮겨 붙인 쪽의 바뀐 칸(`미확인`)은 사람이 보기 전이라 뺀다
    letters, ex = r["letters"], set(r.get("excluded", set())) | set(r.get("미확인", ()))
    return [(b, letters[a]) for i, (b, a) in enumerate(zip(r["boxes"], r["assign"]))
            if 0 <= a < len(letters) and i not in ex]
