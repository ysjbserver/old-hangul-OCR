# -*- coding: utf-8 -*-
"""
쪽 하나를 처리하는 한 줄기 — 이미지와 전사문에서 '상자 + 라벨'까지.

데이터셋 만들기와 교정서버가 같은 함수를 써야 교정이 데이터셋과 맞는다.
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
    표본은 `corpus.images` 에서 — 전사문 없는 문헌에서도 재야 하므로(`doc_tiers` · `doc_layout` 도 같음).
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
    이 문헌은 한 쪽이 몇 단인가. 처음 쓸 때 그림만 보고 한 번 재서 기억한다.
    가름줄 판형이면 가름줄 높이 목록(단마다 열을 따로 찾음), 아니면 가운데 가로줄 판정으로 1 또는 2.
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
    브라우저판 `판형정하기` 와 짝.
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
    # 열들의 합의(진하기)와 자리의 한결같음을 함께 본다 — 하나만으로는 안 갈림
    n = 2 if (합의 >= 0.40 and 흔들림 <= 0.02) else 1
    return n, (f"한 쪽이 {n}단인 판형으로 봅니다 "
               f"(가운데 가로줄 합의 {합의:.2f} · 자리 흔들림 {흔들림:.3f}, 그림 {len(got)}쪽).")


def doc_layout(slug):
    """
    이 문헌의 표준 판짜임 {"자간": px, "열수": n}. 처음 쓸 때 한 번 재서 기억한다(`교정/_판짜임.json`).
    쪽 20개의 중앙값 — 앞머리처럼 판형이 다른 쪽이 섞여도 됨.
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
    브라우저판 `판짜임정하기` 와 짝.
    """
    got = [v for v in 잰것들 if v]
    if len(got) < 8:
        return None
    return {"자간": float(np.median([v[0] for v in got])),
            "열수": int(np.median([v[1] for v in got]))}


읽기배율 = (0.88, 0.94, 1.00, 1.06, 1.12, 1.18, 1.24)


def doc_read_ratio(slug, mdl=None):
    """
    전사문 없이 읽을 때 쓰는 자간. 적혀 있으면 그것, 없으면 자간을 `읽기배율` 로 바꿔 읽어 보고
    모델 확신도(로그 평균)가 가장 높은 값을 골라 적어 둔다(`교정/_자간.json` 의 `_읽기자간`).
    이미 적힌 값은 건드리지 않는다.
    """
    r = corpus.read_ratio(slug)
    if r:
        return r
    바탕 = doc_ratio(slug)
    if not 바탕 or mdl is None:
        return 바탕
    # 전사문이 있으면 자동 추정을 쓰지 않는다 — 전사문으로 재는 쪽이 낫다
    if corpus.pages(slug):
        return 바탕
    import align as _align
    단 = doc_tiers(slug)
    # '좋음' 쪽만 본다 — 앞머리(표지·목차)가 섞이면 확신도가 흐려진다
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
    # 바탕값보다 뚜렷이 나을 때만 바꾼다 — 근소한 차이로 옮기면 손해
    if 기준 is not None and 최고 is not None and 최고 - 기준 < 0.02:
        고른 = 바탕
    corpus.save_read_ratio(slug, 고른)
    print(f"[{slug}] 읽기 자간을 {고른:.4f} 로 정했습니다 "
          f"(바탕 {바탕:.4f} 의 {고른/바탕:.2f}배 — 전사문 없이 확신도로).")
    return 고른


def 쪽건강(slug, geo, 표준=None):
    """
    이 쪽이 제대로 잘렸는가 — 전사문 없이 판정한다.
    반환: (등급, [까닭…])   등급은 "좋음" · "의심" · "못씀".
    ⚠ '잘 잘렸는가' 만 본다. 읽기 확신도는 섞지 말 것(`확신표시` 가 맡음).

    무엇을 보는가:
      · 열을 아예 못 찾음                     → 못씀
      · 자간이 문헌 표준에서 25% 넘게 벗어남  → 못씀 (열이 붙거나 빠진 것)
      · 열 수가 문헌 표준에서 25% 넘게 벗어남 → 의심

    slug 가 None 이면 문헌 표준을 `표준`({"자간", "열수"} — `판짜임정하기` 의 값)으로 받음.
    둘 다 없으면 열을 찾았는지만 봄.
    """
    까닭 = []
    if geo is None or not geo.get("cols"):
        return "못씀", ["열을 찾지 못했습니다"]
    if slug is not None:
        표준 = doc_layout(slug)
    if 표준:
        # ⚠ 두 단 판형은 `page_geometry` 가 열을 단 수만큼 늘려 놓으므로 되돌려 센다
        xp = geo.get("xpitch")
        n = len(geo["cols"]) // max(int(geo.get("단", 1)), 1)
        # 읽는 경로에는 가장자리 후보 열이 붙어 있어 `doc_layout` 과 같은 잣대(본열수)로 센다
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

    읽기=True 는 전사문 없이 읽을 때 — 읽기 자간(`corpus.read_ratio`)이 적혀 있으면 그것을 쓴다.
    ⚠ 읽을 때만 하는 것 둘(자를 때 하면 나빠짐):
      ① 양 끝에 후보 열을 붙여 모델 확신도로 가리기(`scan._가장자리후보` · `align.가장자리다듬기`)
      ② 광곽 경계를 안쪽까지 바짝 잡기(`scan.page_frame`)
    """
    단 = doc_tiers(slug)                  # 자간보다 먼저 — 자간을 단 나눈 뒤에 잰다
    r = (읽기 and corpus.read_ratio(slug)) or doc_ratio(slug)
    # 읽을 때는 문헌 표준 열 간격도 넘긴다 — 흐린 쪽에서 열 찾기 문턱을 고를 때 씀(`scan.find_columns`)
    표준 = (doc_layout(slug) or {}).get("자간") if 읽기 and SCAN_PITCH else None
    return (scan.page_geometry(ip, r, 단, 읽기, 가장자리, 표준, 이어=이어, 끝띠=끝띠, 판심=판심) if r
            else scan.page_geometry(ip, 단=단, 읽기=읽기, 가장자리=가장자리, 표준자간=표준, 이어=이어, 끝띠=끝띠, 판심=판심))


SCAN_PITCH = True    # 읽을 때 문헌 표준 열 간격을 열 찾기에 넘기는가
TEDURI = 1.6        # 잉크가 다른 열 중앙값의 이 배를 넘으면 광곽(테두리) 선으로 본다


def 테두리열버리기(geo, 배수=TEDURI):
    """
    광곽(테두리) 선이 열로 잡힌 것을 버린다 — 첫 열·끝 열 중 잉크가 다른 열 중앙값의 `배수` 를 넘는 것.
    ⚠ 지금 읽는 경로는 쓰지 않음(제본 그림자 진 본문 열을 버림) — `align.가장자리다듬기` 가 확신도로 가림.
    ⚠ 자르는 경로에도 넣지 말 것 — `to_text` 는 칸수 0 으로 테두리 열을 스스로 버리는데, 미리 빼면 진짜 열을 버림.
    ⚠ 두 단 판형에서는 부르지 않음(열 번호를 빼면 단 짝이 어긋남).
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
    상자가 바뀐 쪽에 옛 교정을 옮겨 붙인다.

    좌표가 옛 상자와 같은(`corpus.BOX_TOL` 안) 새 상자는 옛 교정의 글자·뺀 칸을 그대로 받고,
    달라진 상자는 '바뀐 칸' 으로 돌려준다 — 사람이 보기 전에는 학습에 넣지 않는다.
    바뀐 칸의 글자는 앞뒤 옮긴 칸 사이에 남은 글자 수와 칸 수가 같으면 차례대로, 아니면 자동 정렬(`auto`) 값.
    ⚠ 겹침(IoU)으로 옮기지 말 것 — 달라진 상자는 대개 옛 상자가 쪼개지거나 합쳐진 자리라 옮길 글자가 없음.
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
    # 교정 때 본 상자와 지금 상자의 좌표가 같을 때만 쓴다(상자 수는 늘 같음 · 좌표 없는 교정은 안 씀)
    fixed = bool(fix and len(fix["assign"]) == len(r["boxes"])
                 and corpus.same_boxes(fix.get("boxes"), r["boxes"]))
    # 글자 수는 맞는데 상자가 달라진 경우 = 자르는 방식이나 모델이 바뀌었다는 뜻
    r["fix_unused"] = bool(fix and not fixed)
    r["옮김"], r["미확인"] = False, set()
    if fixed:
        r["assign"] = list(fix["assign"])
        r["excluded"] = set(fix.get("excluded", []))
        # 보라 점도 교정의 짝으로 다시 찍는다
        if mdl is not None:
            r["mark"] = _교정점(mdl, geo, r, letters)
    elif fix and fix.get("boxes"):
        # 상자가 바뀐 쪽 — 좌표가 같은 상자에는 옛 교정을 옮겨 붙이고, 바뀐 칸만 보라 점으로
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
