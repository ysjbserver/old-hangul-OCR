# -*- coding: utf-8 -*-
"""
전사대조 — 이미 전사된 쪽을 스캔과 맞대어 **전사문이 틀렸을 만한 자리**를 찾는다.

OCR 도구(`읽기.py` · 브라우저판)와는 **따로 도는 도구**입니다(작업자 결정, 2026-10-01 —
합칠지는 나중에). OCR 프로젝트의 부품(`부품/`)과 모델을 **읽기만** 하고 아무것도 고치지
않습니다. `교정/` · `data/` · `dataset/` · `모델/` 에 쓰지 않습니다.

어떻게 찾나 (라벨을 만들 때와 같은 길을 거꾸로):
  1. 전사문을 정답지 삼아 스캔을 자른다(`align.to_text` — 교정서버 · 2단계와 같은 자르기).
     그러면 상자 하나 = 전사 글자 하나.
  2. 상자마다 모델의 세 머리(초·중·종) 확률을 읽어
       · 모델이 가장 그럴듯하다고 본 글자(스캔)와
       · **전사된 글자의 확률**
     을 둘 다 낸다. 1순위가 다르다는 것만으로는 안 됨 — 전사 글자가 2·3순위로 꽤 있으면
     모델이 헷갈린 것이라 뺀다.
  3. 앞뒤 글자는 맞는 '외딴' 어긋남만 고른다. 줄지어 어긋나면 자르기가 밀린 것이다
     (그때는 한 칸 옮겨 맞으면 '글자가 빠졌거나 더 들어감' 으로 따로 알린다).
  4. 글자마다 **위키 원문에서의 자리**를 따라가 두어, 틀을 그대로 둔 채 그 글자만 짚는다.

    python 전사대조/대조.py <문헌> <쪽>      한 쪽을 대 보고 후보를 찍는다(시험용)
"""
import os
import re
import sys
import json
import base64
import io
import unicodedata

여기 = os.path.dirname(os.path.abspath(__file__))
뿌리 = os.path.dirname(여기)
os.chdir(뿌리)                                   # 부품들이 `모델/` · `data/` · `교정/` 을 뿌리 기준으로 찾는다
sys.path.insert(0, os.path.join(뿌리, "부품"))
sys.stdout.reconfigure(errors="replace")        # 윈도 콘솔이 못 찍는 글자에서 죽지 않게

import numpy as np
from PIL import Image, ImageDraw

import wikitext
from wikitext import decompose
import align
import scan
import page
import corpus


# ── 문턱 (재기.py 로 고름 — 바꾸면 그쪽 결과도 다시) ──────────────────
P_TR_MAX  = 0.05    # 전사 글자의 모델 확률이 이보다 낮아야(모델이 '이 글자는 아니다' 라고 볼 때만)
TOP_MIN   = 0.80    # 모델 1순위의 확신(세 머리 중 가장 낮은 것)이 이보다 높아야
일치문턱  = 0.75    # 쪽 전체에서 모델과 전사문이 이만큼 안 맞으면 '이 쪽은 맞대기가 흔들림' 으로 본다
다시볼일치 = 0.9    # 자르는 기하로 이만큼 안 맞으면 읽는 기하로도 해 본다
열문턱    = 0.75    # 한 열에서 모델과 전사문이 이만큼 안 맞으면 그 열의 '글자가 다름' 후보는 내지 않는다(열이 통째로 어긋난 것)
받침잘림높이 = 0.8   # 스캔 쪽에서 받침만 빠졌고 상자가 그 열 가운데 높이의 이만큼도 안 되면 버린다 — 상자를 짧게 잘라
                    # 받침이 다음 칸으로 넘어간 것(권1 · 권2 에 많음: ᄅᆞᆷ→ᄅᆞ · 를→르 · 면→며). 100쪽에서 진짜 오타는 1곳만 잃음
밀림몫    = 0.6     # 줄지어 다른 구간에서 한 칸 옮겨 이 몫 넘게 맞으면 '빠짐 · 더 들어감'


# ── 모델 ─────────────────────────────────────────────────────────────
def 모델폴더():
    """
    쓸 모델이 있는 폴더. ⚠ `실험12` 가 도는 동안은 `모델/옛한글모델.pt` 가 학습 중인 모델로
    잠깐 덮이므로, 그때는 실험이 떠 둔 사본(`모델/_실험12백업/`)이 진짜 지금 모델이다.
    ⚠ 그 사본 폴더는 실험이 끝나도 남는다 — 그 뒤 새 모델을 채택하면 사본이 옛것이 된다. 그래서 둘이 다르면
      **가장 최근에 채택한 모델**(`모델/백업/백업_*채택.pt`)과 같은 쪽을 고르고, 그것도 안 되면 `모델/` 을 쓴다.
    """
    import glob, hashlib
    import ocr                                   # torch 를 불러오므로 여기서만(Toolforge 서버는 안 부름)
    있는 = [d for d in ("모델", os.path.join("모델", "_실험12백업"))
            if all(os.path.exists(os.path.join(d, f)) for f in (ocr.WEIGHTS, ocr.TABLE))]
    if len(있는) < 2:
        return 있는[0] if 있는 else None
    해시 = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    h = {d: 해시(os.path.join(d, ocr.WEIGHTS)) for d in 있는}
    if h[있는[0]] == h[있는[1]]:
        return 있는[0]
    채택 = sorted(glob.glob(os.path.join("모델", "백업", "백업_*채택.pt")), key=os.path.getmtime)
    if 채택:
        hc = 해시(채택[-1])
        for d in 있는:
            if h[d] == hc:
                return d
    return 있는[0]


def 모델불러오기(장치=None):
    import ocr, torch                            # torch 는 여기서만 — Toolforge 서버는 ONNX 모델(`onnx모델.py`)을 넘김
    d = 모델폴더()
    if d is None:
        raise RuntimeError("모델이 없습니다 (모델/옛한글모델.pt)")
    장치 = 장치 or ("cuda" if torch.cuda.is_available() else "cpu")
    with open(os.path.join(d, ocr.TABLE), encoding="utf-8") as f:
        v = json.load(f)
    net = ocr.Net(len(v["초성"]), len(v["중성"]), len(v["종성"])).to(장치)
    net.load_state_dict(torch.load(os.path.join(d, ocr.WEIGHTS), map_location=장치))
    net.eval()
    m = ocr.Model(net, v["초성"], v["중성"], v["종성"], v["size"], 장치)
    m.폴더 = d
    return m


def 확률읽기(mdl, im, boxes, batch=512):
    """상자들 → 세 머리의 확률 (sL, sV, sT) — `ocr.Model.read` 와 같은 입력, 1순위만이 아니라 전부."""
    if hasattr(mdl, "확률"):                      # ONNX 모델(`onnx모델.모델`, Toolforge) — 같은 입력 · 같은 답
        return mdl.확률(im, boxes, batch)
    if not boxes:
        z = np.zeros((0, 1))
        return z, z, z
    import torch
    xt = mdl.crops(im, boxes)
    out = [[], [], []]
    with torch.no_grad():
        for i in range(0, len(xt), batch):
            for k, p in enumerate(mdl.net(xt[i:i + batch].to(mdl.dev))):
                out[k].append(torch.softmax(p, 1).cpu().numpy().astype(np.float64))
    return tuple(np.concatenate(o) for o in out)


# ── 위키 원문 → 인쇄된 글자 + 원문에서의 자리 ─────────────────────────
# `wikitext.printed_text` 와 **글자 하나까지 같은** 결과를 내되, 남는 문자마다 원문의 몇 번째
# 문자였는지를 따라간다. 걷어 내는 규칙이 전부 '지우기 · 틀 인자 남기기' 라 자리를 잃지 않는다.
# ⚠ 규칙은 `wikitext` 의 표(DROP · LAST · JOIN · FIRST)를 그대로 가져다 쓴다 — 한쪽만 바뀌지 않게.
#   다만 정규식은 이 파일에 따로 옮겨 적었으니, `wikitext.printed_text` 를 고치면 여기도 고치고
#   `python 전사대조/재기.py --글자확인` 으로 같은지 확인할 것.

def _바꾸기(t, pos, 맞음들, 남길것):
    """맞음마다 그 자리를 `남길것(m)` 이 돌려준 구간들(t 안의 [a, b))로 바꾼다."""
    nt, npos, p = [], [], 0
    for m in 맞음들:
        nt.append(t[p:m.start()]); npos.extend(pos[p:m.start()])
        for a, b in 남길것(m):
            nt.append(t[a:b]); npos.extend(pos[a:b])
        p = m.end()
    nt.append(t[p:]); npos.extend(pos[p:])
    return "".join(nt), npos


큰틀 = {"크게", "더크게", "더더크게"}   # 큰 활자 — `_한번` 이 '빼고 맞대기' 를 후보로 해 봄


def _틀남길것(이름, 인자, 큰빼기=False):
    """`wikitext._template` 과 같은 판정 — 문자열 대신 인자 구간을 돌려준다. 큰빼기면 큰 활자 틀(`큰틀`)도 버림."""
    if 이름 in wikitext.DROP or 이름.startswith("왼쪽 여백/") or (큰빼기 and 이름 in 큰틀):
        return []
    if 이름 in wikitext.JOIN:  return 인자[:2]
    if 이름 in wikitext.LAST:  return 인자[-1:]
    if 이름 in wikitext.FIRST: return 인자[:1]
    return []


class _자리:
    """`_바꾸기` 에 넘길 맞음 흉내 — `wikitext.표구간` 의 (시작, 끝, 남길)."""
    def __init__(self, a, b, 남길):
        self._a, self._b, self.남길 = a, b, 남길
    def start(self): return self._a
    def end(self): return self._b


오식틀 = {"SIC"}       # 원문 오식을 그대로 옮긴 표시 — 이 안의 글자는 후보로 내지 않는다


def 인쇄글자(raw, keep_headings=False, 큰빼기=False):
    """
    위키 원문 → [(글자, 원문 시작, 원문 끝, 오식틀 안인가), …]
    글자는 `wikitext.letters(wikitext.printed_text(raw, keep_headings))` 와 같다.
    """
    t, pos = raw, list(range(len(raw)))
    오식 = set()
    표 = wikitext.표있나(raw)
    t, pos = _바꾸기(t, pos, re.finditer(r'<noinclude>.*?</noinclude>', t, flags=re.S), lambda m: [])
    while True:                                  # 안쪽 틀부터 하나씩
        m = re.search(r'\{\{([^{}]*)\}\}', t)
        if not m:
            break
        조각, a = [], m.start(1)
        for 끝 in [i for i in range(m.start(1), m.end(1)) if t[i] == "|"] + [m.end(1)]:
            조각.append((a, 끝)); a = 끝 + 1
        이름 = t[조각[0][0]:조각[0][1]].strip()
        인자 = [(a, b) for a, b in 조각[1:] if not re.match(r'^\s*[A-Za-z-]+\s*=', t[a:b])]
        남길 = _틀남길것(이름, 인자, 큰빼기)
        if 이름 in 오식틀:
            for a, b in 남길:
                오식.update(pos[a:b])
        t, pos = _바꾸기(t, pos, [m], lambda _m: 남길)
    t, pos = _바꾸기(t, pos, re.finditer(r'^\s*=+\s*(.*?)\s*=+\s*$', t, flags=re.M),
                     lambda m: [m.span(1)] if keep_headings else [])
    t, pos = _바꾸기(t, pos, re.finditer(r'^[ \t]*:+', t, flags=re.M), lambda m: [])   # 줄 머리 `:` 들여쓰기 (2026-10-06)
    t, pos = _바꾸기(t, pos, re.finditer(r"'{2,}", t), lambda m: [])   # `''` · `'''` 굵게 · 기울임 (2026-10-06)
    t, pos = _바꾸기(t, pos, re.finditer(r'\[\[[^|\]]*\|([^\]]*)\]\]', t), lambda m: [m.span(1)])
    t, pos = _바꾸기(t, pos, re.finditer(r'\[\[([^\]]*)\]\]', t), lambda m: [m.span(1)])
    표자리 = wikitext.표구간(t, 표)                  # 표 문법 — 규칙은 `wikitext` 의 것을 그대로
    t, pos = _바꾸기(t, pos, [_자리(a, b, 남길) for a, b, 남길 in 표자리], lambda m: m.남길)
    t, pos = _바꾸기(t, pos, re.finditer(r'<[^>]+>', t), lambda m: [])
    t, pos = _바꾸기(t, pos, re.finditer(r'[\s​]+', t), lambda m: [])

    out, cur = [], None                          # `wikitext.letters` 와 같은 묶기
    for ch, p in zip(t, pos):
        o = ord(ch)
        꼬리 = (0x1160 <= o <= 0x11FF) or (0xA960 <= o <= 0xA97F) or (0xD7B0 <= o <= 0xD7FF)
        if 꼬리 and cur:
            cur[0] += ch; cur[1].append(p)
        else:
            if cur: out.append(cur)
            cur = [ch, [p]]
    if cur: out.append(cur)
    return [(c, min(ps), max(ps) + 1, any(p in 오식 for p in ps)) for c, ps in out]


# ── 문헌 설정 · 기하 ─────────────────────────────────────────────────
def 아는문헌(slug):
    """`data/` 에 있고 설정(자간)이 적혀 있는 문헌인가 — 그때만 그 문헌 설정을 쓴다."""
    return bool(slug) and corpus.doc_ratio(slug) is not None


def 기하(slug, ip, 읽기=False, 끝띠=False, 판심=None, 설정=None):
    """
    쪽 기하. 먼저 자르는 경로(`page.geometry(…, 읽기=False)` — 교정서버 · 2단계와 같다)로 하고,
    잘 안 맞으면 `한쪽` 이 읽는 경로의 기하(광곽을 열마다 찾는 등 — 가장자리 후보 열은 붙이지 않음)로 한 번 더 한다.
    (훈아진언 0058: 자르는 기하로는 '글자 수를 맞추지 못함', 읽는 기하로는 일치 98%.)
    모르는 문헌은 그 쪽 그림만으로 자간을 재고 한 단으로 본다. ⚠ `page.doc_*` 는 재고 나서 `교정/` 에
    적으므로 모르는 문헌에는 부르지 않는다.
    끝띠=True 는 스캔 끝의 제본 그림자 띠를 지우고 열을 찾는 자르는 기하(`scan.find_columns(…, 끝띠=True)`) — `_한번` 의 셋째 후보.
    판심=False 는 판심 걸러내기(`scan._drop_margin_column`)를 끈 기하 — `_한번` 의 넷째 후보.
    설정 = 파일마다 잰 문헌 설정 {단, 자간비, 읽기자간비, 판짜임}(브라우저 `판형살피기` · Toolforge 서버의 `살피기` 값) — 주면 그것으로
    (`전사대조.js` 의 `기하얻기` 와 같게: 자간비를 못 잰 파일만 이 쪽 그림으로, 판짜임 자간은 읽는 기하에만). 2026-10-07
    """
    if 설정:
        단 = 설정.get("단") or 1
        단 = tuple(단) if isinstance(단, list) else 단
        r = (읽기 and 설정.get("읽기자간비")) or 설정.get("자간비") or scan.page_ratio(ip, 단=단)
        표준 = 설정["판짜임"]["자간"] if 읽기 and 설정.get("판짜임") else None
        return scan.page_geometry(ip, r, 단, 읽기, False, 표준, 끝띠=끝띠, 판심=판심)
    if 아는문헌(slug):
        return page.geometry(slug, ip, 읽기=읽기, 가장자리=False, 끝띠=끝띠, 판심=판심)
    return scan.page_geometry(ip, scan.page_ratio(ip), 읽기=읽기, 가장자리=False, 끝띠=끝띠, 판심=판심)


# ── 맞대기 ───────────────────────────────────────────────────────────
def 맞대기(mdl, geo, 글자들, span=3, 경계=False):
    """
    글자들 = `인쇄글자` 의 결과. 반환:
      dict(사유=None, 일치, 상자, 후보=[…], 흔들림) — 후보마다
        dict(갈래, 번호(글자 번호), 전사, 스캔, 전사확률, 확신, 점수, 상자번호)
      또는 dict(사유="…")
    갈래: '바뀜'(외딴 한 글자) · '모르는자모'(모델이 배운 적 없는 자모) ·
          '빠짐' / '더들어감'(열 안에서 줄지어 다른데 한두 칸 옮기면 맞음 — 스캔에 글자가 더 있음 / 전사문에 더 있음)
    """
    letters = [g[0] for g in 글자들]
    if len(letters) < page.MIN_LETTERS:
        return dict(사유=f"글자가 너무 적습니다({len(letters)}자)")
    r = align.to_text(mdl, geo, letters, span=span, 경계=경계)
    if r.get("사유"):
        return dict(사유=r["사유"])
    boxes, assign = r["boxes"], r["assign"]
    sL, sV, sT = 확률읽기(mdl, geo["image"], align._맞춤상자(np.asarray(geo["image"]), boxes, geo))   # 행간 넓은 쪽(2026-10-06)
    rL, rV, rT = mdl.codes(letters, decompose)
    kL, kV, kT = sL.argmax(1), sV.argmax(1), sT.argmax(1)
    확신 = np.minimum(np.minimum(sL.max(1), sV.max(1)), sT.max(1))
    n = len(boxes)
    k = np.array(assign)
    아는 = (rL[k] >= 0) & (rV[k] >= 0) & (rT[k] >= 0)
    같음 = 아는 & (kL == rL[k]) & (kV == rV[k]) & (kT == rT[k])
    idx = np.arange(n)
    전사확률 = np.where(아는, sL[idx, np.maximum(rL[k], 0)] * sV[idx, np.maximum(rV[k], 0)]
                      * sT[idx, np.maximum(rT[k], 0)], 0.0)
    읽음확률 = sL.max(1) * sV.max(1) * sT.max(1)
    스캔 = [unicodedata.normalize("NFC", mdl.letter(kL[i], kV[i], kT[i])) for i in range(n)]   # 현대 글자는 완성형으로

    다름 = ~같음
    N = len(letters)
    # 열마다 일치 — 한 열이 통째로 어긋나면(개역 1245: 같은 구절이 두 번 나와 열 하나가 다른 자리에 짝지어짐)
    # 외딴 '다름' 이 그 열에 줄줄이 생긴다. 진짜 오타는 한 열(20~30자)에 한두 개라 이 문턱에 안 걸린다.
    열 = [b[0] for b in boxes]
    열일치 = {}
    for x in set(열):
        js = [j for j in range(n) if 열[j] == x and 아는[j]]
        열일치[x] = (sum(bool(같음[j]) for j in js) / len(js)) if len(js) >= 5 else 1.0
    흔들린열 = {x for x, v in 열일치.items() if v < 열문턱}

    def 맞음(i, kk):                              # 상자 i 를 모델이 읽은 것이 전사 글자 kk 와 같은가(자모로 — 완성형 · 첫가끝 섞여도)
        return (0 <= kk < N and rL[kk] >= 0 and rV[kk] >= 0 and rT[kk] >= 0
                and kL[i] == rL[kk] and kV[i] == rV[kk] and kT[i] == rT[kk])

    후보 = []

    높이 = np.array([b[3] - b[1] for b in boxes], dtype=float)
    열높이 = {x: float(np.median([높이[j] for j in range(n) if 열[j] == x])) for x in set(열)}

    def 높이비(j):                                # 상자 높이 ÷ 그 열의 가운데 높이 — 잘못 자른 칸은 1 에서 멀다
        return float(높이[j] / max(1.0, 열높이[열[j]]))

    def 넣기(갈래, i, 점수):
        이웃 = [높이비(j) for j in (i - 1, i + 1) if 0 <= j < n and 열[j] == 열[i]]
        후보.append(dict(갈래=갈래, 번호=int(assign[i]), 상자번호=int(i), 전사=letters[assign[i]],
                         스캔=스캔[i], 전사확률=float(전사확률[i]), 확신=float(확신[i]), 점수=float(점수),
                         높이비=높이비(i), 이웃높이비=이웃))

    빈종성 = mdl.iT.get("", -1)

    def 받침잘림(j):
        kk = assign[j]
        return (kL[j] == rL[kk] and kV[j] == rV[kk] and rT[kk] != 빈종성 and kT[j] == 빈종성
                and 높이비(j) < 받침잘림높이)

    def 바뀜인가(j, 엄격=1.0):
        return (아는[j] and not 글자들[assign[j]][3] and 전사확률[j] < P_TR_MAX * 엄격
                and 확신[j] >= TOP_MIN and 열[j] not in 흔들린열 and not 받침잘림(j))

    i = 0
    while i < n:                                  # 읽는 차례로 '다름' 이 이어진 덩이마다(열을 넘어가도 이어 봄 — 밀림은 열을 넘는다)
        if not 다름[i]:
            i += 1; continue
        e = i
        while e + 1 < n and 다름[e + 1]:
            e += 1
        덩이 = list(range(i, e + 1))
        if len(덩이) == 1:
            if 글자들[assign[i]][3]:
                pass                              # {{SIC}} 안 — 원문 오식으로 이미 표시됨
            elif not 아는[i]:
                if 확신[i] >= TOP_MIN and 열[i] not in 흔들린열:
                    넣기("모르는자모", i, 0.0)
            elif 바뀜인가(i):
                넣기("바뀜", i, np.log(읽음확률[i]) - np.log(max(전사확률[i], 1e-12)))
            i = e + 1
            continue
        # 상자마다 '몇 칸 옮기면 맞나'(가까운 것부터, 못 맞추면 None)
        옮김 = {j: next((d for d in (-1, 1, -2, 2, -3, 3) if 맞음(j, assign[j] + d)), None) for j in 덩이}
        if sum(d is not None for d in 옮김.values()) >= 2:
            # 밀림 — 옮김 값이 바뀌는 자리마다 '빠짐 · 더들어감' 하나. 상자가 전사의 앞 글자를 보이면(옮김 < 0)
            # 스캔에 글자가 더 있고(전사문에서 빠짐), 뒤 글자를 보이면 전사문에 글자가 더 들어간 것
            지금, 틈 = 0, i
            사건 = []
            for j in 덩이:
                d = 옮김[j]
                if d is None:
                    continue
                if d != 지금:
                    사건.append(j)
                    넣기("빠짐" if d < 지금 else "더들어감", 틈, abs(d - 지금))
                    후보[-1]["끝번호"] = int(assign[j])
                    후보[-1]["칸"] = abs(d - 지금)
                    지금 = d
                틈 = j + 1
            # 어디에도 안 맞는 상자 중 밀림 자리에서 먼 것만 낱글자로(두 글자가 한 칸에 든 자리는 사건 곁에 있다)
            for j in 덩이:
                if 옮김[j] is None and all(abs(j - q) > 2 for q in 사건) and 바뀜인가(j, 0.2) and 확신[j] >= 0.95:
                    넣기("바뀜", j, np.log(읽음확률[j]) - np.log(max(전사확률[j], 1e-12)))
                    후보[-1]["붙음"] = True
        else:
            # 옮겨도 안 맞으면 하나하나 — 아주 자신 있게 다를 때만(오타가 붙어 있을 수도)
            for j in 덩이:
                if 바뀜인가(j, 0.2) and 확신[j] >= 0.95:
                    넣기("바뀜", j, np.log(읽음확률[j]) - np.log(max(전사확률[j], 1e-12)))
                    후보[-1]["붙음"] = True
        i = e + 1

    차례 = {"바뀜": 0, "모르는자모": 1, "깨진글자": 1, "빠짐": 2, "더들어감": 2}
    후보.sort(key=lambda c: (차례[c["갈래"]], -c["점수"]))
    일치 = r["일치"]
    return dict(사유=None, 일치=일치, 상자=boxes, assign=list(assign), 후보=후보, 흔들림=bool(일치 is not None and 일치 < 일치문턱),
                흔들린열=len(흔들린열), 열수=len(열일치),
                글자수=len(letters), 이미지=geo["image"])


# ── 보여 줄 그림 ─────────────────────────────────────────────────────
def 조각그림(im, boxes, i, 앞뒤=1, 높이=None):
    """상자 i 와 같은 열의 앞뒤 글자까지 오려, 그 상자에 빨간 테를 두른 PNG(data: 주소)."""
    b = boxes[i]
    j0 = i
    while j0 > 0 and i - j0 < 앞뒤 and boxes[j0 - 1][0] == b[0]:
        j0 -= 1
    j1 = i
    while j1 + 1 < len(boxes) and j1 - i < 앞뒤 and boxes[j1 + 1][0] == b[0]:
        j1 += 1
    pad = 6
    x0, x1 = max(0, b[0] - pad), min(im.size[0], b[2] + pad)
    y0, y1 = max(0, boxes[j0][1] - pad), min(im.size[1], boxes[j1][3] + pad)
    g = im.crop((x0, y0, x1, y1)).convert("RGB")
    d = ImageDraw.Draw(g)
    d.rectangle((b[0] - x0 - 2, b[1] - y0 - 1, b[2] - x0 + 1, b[3] - y0), outline=(220, 30, 30), width=3)
    if 높이:
        g = g.resize((max(1, round(g.size[0] * 높이 / g.size[1])), 높이), Image.LANCZOS)
    buf = io.BytesIO()
    g.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


# ── 깨진 글자 — 스캔 없이 전사문만 보고 ───────────────────────────────
def 깨짐(c):
    """
    성한 글자가 아니면 그 까닭, 성하면 None. 맞대기가 흔들린 쪽에서도 잡힌다.
    ('글자 수가 어긋난 곳' 으로만 잡히던 고친 곳 29 가운데 대부분이 이것 — `괌ᅟᅡᆫ` · `ᄃힺ` · `모ퟲ` · `{[du|`.
     100쪽에서 고친 곳 16 을 짚고, 고친 뒤 전사문에 남은 것은 본문에 섞인 `}` 하나.)
    ⚠ 빈도 기반 오타 검사(`../옛한글 오타 검사/`)의 '확실자리' 와 겹친다 — 그쪽 코드는 쓰지 않는다(그쪽 규칙).
    """
    if c in ("ㅣ", "○", "〇"):
        return None
    if re.search(r"[{}\[\]|=<>]", c):
        return "틀 찌꺼기"
    o = [ord(x) for x in c]
    if any(0xA960 <= x <= 0xA97F or 0xD7B0 <= x <= 0xD7FF for x in o):
        return "확장 자모"
    if len(c) == 1:
        if 0x1100 <= o[0] <= 0x11FF or 0x3130 <= o[0] <= 0x318F:
            return "홀로 선 자모"
        return None                               # 완성형 · 한자 · 문장부호는 보지 않는다
    if 0xAC00 <= o[0] <= 0xD7A3:
        return "완성형 뒤에 자모"
    L = [x for x in o if 0x1100 <= x <= 0x115F]
    V = [x for x in o if 0x1160 <= x <= 0x11A7]
    T = [x for x in o if 0x11A8 <= x <= 0x11FF]
    if len(L) != 1 or len(V) != 1 or len(T) > 1:
        return "자모 수가 이상함"
    if L[0] == 0x115F or V[0] == 0x1160:
        return "채움 문자"
    if o != sorted(o, key=lambda x: 0 if x < 0x1160 else (1 if x < 0x11A8 else 2)):
        return "자모 차례"
    return None


낱갈래 = ("바뀜", "모르는자모")


def 같은후보(c, 들):
    """다른 자르기로 얻은 후보 목록 `들` 에 c 와 같은 것이 있나 — 같은 글자 번호 · 같은 스캔 글자(밀림은 ±2 안 같은 갈래)."""
    for d in 들:
        if c["갈래"] in 낱갈래:
            if d["갈래"] == c["갈래"] and d["번호"] == c["번호"] and d["스캔"] == c["스캔"]:
                return True
        elif d["갈래"] == c["갈래"] and abs(d["번호"] - c["번호"]) <= 2:
            return True
    return False


# ── 한 쪽 ────────────────────────────────────────────────────────────
def _한번(mdl, slug, ip, raw, 제목, 경계, 기하들, 큰빼기=None, 설정=None):
    """
    한 가지 자르기로 맞대기 → (결과, 글자들). 자르는 기하 → (일치 < 다시볼일치 면) 읽는 기하 → 끝띠 기하 중 잘 맞는 쪽.
    기하들의 원소: False = 자르는 기하 · True = 읽는 기하 · "끝띠" = 제본 그림자 띠를 지운 자르는 기하(2026-10-02 — 권2 0003:
    오른쪽 끝 검은 띠가 열로 잡혀 일치 4%). 끝띠 기하는 열 찾기를 늘 바꾸면 쪽마다 양쪽으로 튀어서(`scan.INK_EDGE`) **후보로만** 씀 —
    전사문과 더 잘 맞을 때만 고르므로 나빠지는 쪽이 없음(표본 175쪽: 63.4 → 68.6%). 띠가 없는 쪽은 자르는 기하와 같아 건너뜀.
    큰빼기 = 큰 활자 틀(`{{더크게|에스라}}` 같은 책 이름) 안 글자를 빼고 맞대기. None 이면 그대로 해 보고, 일치가 `다시볼일치` 에 못 미치고
    원문에 큰 활자 틀이 있으면 빼고도 해 봐서 잘 맞는 쪽(권2 0003: 책 첫 쪽의 큰 「에스라」 열이 판짜임 밖이라 뒤 열이 세 칸씩 밀림).
    "판심" = 판심 걸러내기를 끈 읽는 기하(2026-10-04 — 훈아진언 1894 PDF 58쪽: 오른쪽 광곽에 붙은 끝 열이 광곽 쪽으로 끌려
    이웃과 간격이 1.23배가 되자 판심으로 떼여 13열이 12열 → 일치 29%). 끝띠처럼 **후보로만** — 뗀 열이 없으면 건너뜀.
    """
    if 제목 is None and 아는문헌(slug):
        제목 = corpus.heading_printed(slug)
    시도 = [제목] if 제목 is not None else [False, True]
    best = None
    본열 = {}
    큰있음 = any(re.search(r"\{\{\s*" + 이름 + r"\s*\|", raw) for 이름 in 큰틀)
    for 빼기 in ([큰빼기] if 큰빼기 is not None else [False, True]):
        if 빼기 and 큰빼기 is None and (not 큰있음 or (best and (best[0].get("일치") or 0) >= 다시볼일치)):
            break                                 # 큰 활자 틀이 없거나 이미 잘 맞음
        for 판 in 기하들:
            if best and (best[0].get("일치") or 0) >= 다시볼일치:
                break                             # 자르는 기하로 잘 맞았으면 그만
            판심 = 판 == "판심"
            읽기, 끝띠 = 판 is True or 판심, 판 == "끝띠"
            if 끝띠 and "자르기" not in 본열:
                g0 = 기하(slug, ip, False, 설정=설정)
                본열["자르기"] = g0["cols"] if g0 else None
            if 판심 and "읽기" not in 본열:
                g0 = 기하(slug, ip, True, 설정=설정)
                본열["읽기"] = g0["cols"] if g0 else None
            geo = 기하(slug, ip, 읽기, 끝띠=끝띠, 판심=False if 판심 else None, 설정=설정)
            if geo is None:
                continue
            if 끝띠 and geo["cols"] == 본열.get("자르기"):
                continue                          # 띠가 없는 쪽 — 자르는 기하와 같음
            if 판심 and geo["cols"] == 본열.get("읽기"):
                continue                          # 뗀 판심 열이 없는 쪽 — 읽는 기하와 같음
            if 읽기 and not 판심:
                본열["읽기"] = geo["cols"]
            if not 읽기 and not 끝띠:
                본열["자르기"] = geo["cols"]
            이전 = None
            for kh in 시도:
                글자들 = 인쇄글자(raw, kh, 빼기)
                if 이전 is not None and len(글자들) == 이전:
                    continue                      # 제목이 없는 쪽 — 같은 것을 두 번 할 까닭이 없다
                이전 = len(글자들)
                r = 맞대기(mdl, geo, 글자들, 경계=경계)
                r["기하"] = "판심" if 판심 else ("끝띠" if 끝띠 else ("읽기" if 읽기 else "자르기"))
                r["제목"] = kh
                r["큰빼기"] = 빼기
                if best is None or (r.get("일치") or -1) > (best[0].get("일치") or -1):
                    best = (r, 글자들)
    if best is None:
        return dict(사유="스캔에서 열을 못 찾았습니다"), []
    return best


def 한쪽(mdl, slug, ip, raw, 제목=None, 그림=True, 경계=False, 기하들=(False, True, "끝띠", "판심"), 합의=True, 밀림=False, 깨진=False,
         설정=None):
    """
    위키 원문(편집 상자의 본문) 한 쪽을 그 쪽 스캔과 맞댄다.
    제목 = 편·장 제목이 종이에 인쇄되는가. None 이면 아는 문헌은 그 설정, 모르는 문헌은 둘 다 해 보고 잘 맞는 쪽.
    합의 = '글자가 다름 · 모르는 자모' 를 **다르게 한 번 더 잘라서** 확인한다(`c["합의"]`) — 배운 경계 검출기를 섞은 자르기(B),
           그래도 안 나오면 읽는 기하 + 검출기(C). 진짜 오타는 어떻게 잘라도 남고 자르기 실수는 자르기마다 자리가 바뀐다
           (2026-10-01 `실험_자르기합의.py` — 100쪽: 고친 곳은 3곳만 잃고 남는 후보 25% 줄어듦). 후보가 없는 쪽은 한 번만 자른다.
    밀림 = '빠짐 · 더 들어감' 도 낼까 — 작업자가 써 보니 거의 100% 헛경보(상자 자르기 실수)라 기본으로 끔.
    깨진 = 전사문만 보고 '깨진 글자'(`깨짐`)도 낼까 — 기본으로 끔(2026-10-01, 작업자 결정: 이 도구는 **OCR 로 찾는 것만**.
           표 문법 `{| … |}` 같은 서식까지 틀 찌꺼기로 잡았고, 구조 오류는 다른 도구 몫 — `../옛한글 오타 검사/`).
    설정 = 파일마다 잰 문헌 설정(`기하` 참고) — 주면 slug 대신 그것으로 기하를 잡는다(Toolforge 서버).
    반환 dict — 후보마다 원문 자리(시작 · 끝)와 그림(data: 주소)을 붙인다.
    """
    r, 글자들 = _한번(mdl, slug, ip, raw, 제목, 경계, 기하들, 설정=설정)
    if r.get("사유"):
        return r
    if not 밀림:
        r["후보"] = [c for c in r["후보"] if c["갈래"] not in ("빠짐", "더들어감")]
    r["합의본"] = []
    낱 = [c for c in r["후보"] if c["갈래"] in 낱갈래]
    for c in r["후보"]:
        c["합의"] = c["갈래"] not in 낱갈래 or not 합의
    for 이름, 옵 in (("B", dict(경계=True, 기하들=기하들)), ("C", dict(경계=True, 기하들=(True, "판심")))):
        남은 = [c for c in 낱 if not c["합의"]]
        if not 합의 or not 남은:
            break
        r2, 글2 = _한번(mdl, slug, ip, raw, r["제목"], 큰빼기=r.get("큰빼기", False), 설정=설정, **옵)
        r["합의본"].append(이름)
        if r2.get("사유") or len(글2) != len(글자들):
            continue
        for c in 남은:
            c["합의"] = 같은후보(c, r2["후보"])

    # 깨진 글자 — 스캔과 상관없이(맞댄 상자가 있으면 그림도). 기본 끔(위 `깨진`)
    상자번호 = {k: j for j, k in enumerate(r.get("assign", []))}
    for k, g in (enumerate(글자들) if 깨진 else ()):
        왜 = 깨짐(g[0])
        if 왜 and not g[3]:
            r["후보"].append(dict(갈래="깨진글자", 번호=k, 상자번호=상자번호.get(k, -1), 전사=g[0], 스캔="",
                                 전사확률=0.0, 확신=0.0, 점수=0.0, 까닭=왜, 합의=True))
    차례 = {"바뀜": 0, "모르는자모": 1, "깨진글자": 1, "빠짐": 2, "더들어감": 2}
    r["후보"].sort(key=lambda c: (not c["합의"], 차례[c["갈래"]], -c["점수"]))

    for c in r["후보"]:
        끝k = c.get("끝번호", c["번호"])
        c["시작"], c["끝"] = 글자들[c["번호"]][1], 글자들[끝k][2]
        c["앞"] = "".join(g[0] for g in 글자들[max(0, c["번호"] - 5):c["번호"]])
        c["뒤"] = "".join(g[0] for g in 글자들[끝k + 1:끝k + 6])
        if 그림 and c["상자번호"] >= 0:
            c["그림"] = 조각그림(r["이미지"], r["상자"], c["상자번호"], 앞뒤=2 if c["갈래"] in ("빠짐", "더들어감") else 1)
    return r


def main():
    if len(sys.argv) < 3:
        print(__doc__); return
    slug, pg = sys.argv[1], sys.argv[2].zfill(4)
    ip = os.path.join("data", slug, "img", pg + ".jpg")
    tp = os.path.join("data", slug, "text", pg + ".txt")
    raw = open(tp, encoding="utf-8").read()
    mdl = 모델불러오기()
    print(f"모델: {mdl.폴더} ({mdl.dev})")
    r = 한쪽(mdl, slug, ip, raw, 그림=False)
    if r.get("사유"):
        print("✗", r["사유"]); return
    print(f"글자 {r['글자수']} · 일치 {r['일치']:.1%}" + (" · ⚠ 맞대기가 흔들림" if r["흔들림"] else ""))
    for c in r["후보"]:
        print(f"  [{c['갈래']}{'' if c['합의'] else ' · 합의 안 됨'}] {c['번호'] + 1}번째  {c['앞']}〈{c['전사']}〉{c['뒤']}  → 스캔 {c['스캔']}"
              f"  (전사 확률 {c['전사확률']:.3f} · 확신 {c['확신']:.2f})  원문 {c['시작']}~{c['끝']}: {raw[c['시작']:c['끝']]!r}")


if __name__ == "__main__":
    main()
