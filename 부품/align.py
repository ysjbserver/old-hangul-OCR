# -*- coding: utf-8 -*-
"""
정렬 — 열을 몇 칸으로 자를지 정한다. 이 프로젝트의 심장이다.

전사문이 있으면 정답지로 쓴다 — 열마다 여러 개수로 잘라 본 뒤, 모델이 읽은 글자가 전사문과 가장 잘 맞는 조합을
쪽 전체에서 고른다(열을 차례로 훑는 동적 계획법).
정답지가 없으면(읽는 경로) 같은 후보들 중 모델이 가장 자신 있어 하는 것을 고른다.
"""
import os
import numpy as np

import scan
import 경로
from wikitext import decompose

# ── 점수의 무게 ──────────────────────────────────────────────────────
W_L, W_V, W_T, W_ALL = 0.40, 0.40, 0.20, 0.20   # 자리마다 초·중·종성이 맞으면
UNKNOWN   = 0.45      # 모델이 배운 적 없는 글자 — 맞다 틀리다 할 수 없으니 중립
W_CONF    = 0.20      # 모델이 그 조각들을 얼마나 자신 있게 읽었는가
W_PITCH   = 22.0      # 이 열의 자간이 이 쪽의 다른 열과 얼마나 다른가
PITCH_CAP = 0.20      # 자간 차이는 이만큼까지만 벌한다(큰 활자 열을 죽이지 않게)
W_CUT     = 0.4       # 자른 자리가 글자 사이 골짜기에 잘 떨어졌는가
EMPTY_PEN = 6.0       # 열 하나를 통째로 버릴 때의 벌점

# ── 읽을 때 가장자리 열 가리기 (`가장자리다듬기`) ─────────────────────
EDGE_DROP    = 0.3    # 가장자리 열의 로그 확신이 가운데 열 중앙값보다 이만큼 낮으면 버린다
EDGE_MAX     = 3      # 한쪽에서 이만큼까지만 버린다
EDGE_OVERLAP = 0.6    # 이웃 열과 가운데가 자간의 이 배보다 가까우면 겹친 것으로 본다
EDGE_DROP_IN = 0.7    # 광곽 세로줄을 찾은 쪽은 줄 안쪽 열을 이만큼까지 봐준다
EDGE_BAR     = 0.5    # 끝 열의 글자가 이 몫 넘게 `ㅣ` 면 광곽 세로줄로 보고 뗀다 (None = 끔)
EDGE_BAR_RUN = 5      # 끝 열에 `ㅣ` 가 이만큼 넘게 **연달아** 나오면 광곽 줄 · 판심 열로 보고 뗀다 (None = 끔, 2026-10-09)
                      #   — 본문의 주격 조사 `ㅣ` 는 두 번 넘게 잇따르지 않음. 판심 글씨 열(「예례미야일쟝ㅣㅣㅣㅣ…이쳔구십칠」)은 `ㅣ` 가 40% 라 EDGE_BAR 에 안 걸림
EDGE_GUIDE   = 0.3    # 세로줄 너머 떼일 열(둘 이상)이 본문처럼 보이면(확신 · 간격이 자간 ±이 몫) 떼지 않음 — 계선 판 (None = 끔)

# ── 읽을 때 글자가 아닌 칸 빼기 (`열마다읽기`) ────────────────────────
NOTCHAR_CONF  = 0.5   # 확신이 이보다 낮고
NOTCHAR_WIDTH = 0.5   # 잉크 폭이 상자의 이만큼 안 되면 → 작은 절 번호(十八 · 三十)
NOTCHAR_ROW   = 0.9   # 또는 한 행이 폭의 이만큼을 채우면 → 광곽 가로줄
NOTCHAR_KEEP  = ("ㅣ",)  # 모델이 이 글자로 읽은 칸은 빼지 않는다 — 주격 조사 ㅣ 는 가늘다

# ── 읽을 때 두 열에 걸친 큰 활자 편 제목 (`큰제목읽기`) ────────
HEADING      = True   # 이웃한 두 열이 함께 확신이 낮을 때 '두 열을 합친 넓은 칸' 으로 위쪽을 다시 읽어 본다
HEADING_LOW  = 0.25   # 두 열의 로그 확신이 쪽 가운데값보다 이만큼 넘게 낮을 때만 해 본다
HEADING_GAIN = 0.10   # 다시 읽은 쪽의 로그 확신 평균이 이만큼 넘게 나을 때만 바꾼다
HEADING_K    = (2, 3, 4, 5, 6)          # 큰 글자 수 후보
HEADING_H    = (1.5, 1.7, 1.9, 2.1)     # 큰 글자 높이 후보(열 간격의 배)
HEADING_CONF = 0.5    # 큰 글자 칸들의 확신(기하평균)이 이보다 낮으면 버린다 — 진짜 큰 제목은 넓은 칸으로 읽으면 자신 있다

# ── 읽을 때 자를 자리를 모델이 고르기 (`모델자르기계획`) ────────
SEG_MODEL = False     # 켜면 열마다 골짜기 사이 구간을 모두 읽어, 칸 수마다 **모델 확신 합이 가장 큰** 자르기를 고른다
SEG_UNIF  = 0.0       # 칸 높이가 고르지 않은 만큼의 벌점(칸마다, ((h − p)/p)² 배) — 0 이면 모델만 본다
# ── 읽을 때 자를 자리를 배운 경계 검출기로 (`경계검출.py`) ────────
CUT_LEARN = True      # 자를 후보·비용에 검출기의 '경계가 아닐 확률' 을 섞는다(몫 `CUT_MIX`) — 읽는 경로에만
CUT_MIX   = 0.5       # 1 = 검출기만 · 0 = 잉크 그림자만
CUT_CLIP  = 0.0       # 경계 확률을 [이것, 1 − 이것] 으로 자른다 — 0 = 자르지 않음
CUT_ROUND = 10000     # 경계 확률을 1/이것 단위로 반올림(은행가) — 빈 종이에서 검출기가 내는 '평평한' 값을 정확히 평평하게
CUT_LEARN_PATH = os.path.join(경로.모델, "경계검출.pt")
_검출기 = None


def 경계프로파일(geo):
    """열마다 자르기에 쓸 그림자 — `CUT_MIX` 만큼 검출기의 (1 − 경계 확률)을 잉크 그림자 크기로 섞는다."""
    global _검출기
    if _검출기 is None:
        import 경계검출
        _검출기 = 경계검출.검출기(CUT_LEARN_PATH)
    g = np.asarray(geo["image"].convert("L")) if hasattr(geo["image"], "convert") else np.asarray(geo["image"])
    out = []
    for i, (x0, x1) in enumerate(geo["crop_cols"]):
        sm = np.asarray(geo["sm"][i], dtype=float)
        sp = geo["spans"][i]
        if sp is None:
            out.append(sm); continue
        # 1e-4 반올림 — 빈 종이의 거의 일정한 값을 평평하게 해 파이토치 · ONNX(읽기.js) 후보가 같아지게
        p = np.clip(_검출기.경계확률(g, x0, x1)[:len(sm)], CUT_CLIP, 1 - CUT_CLIP)
        p = np.round(p * CUT_ROUND) / CUT_ROUND
        크기 = max(1.0, float(sm[sp[0]:sp[1]].max())) if sp[1] > sp[0] else 1.0
        out.append((1 - CUT_MIX) * sm + CUT_MIX * (1 - p) * 크기)
    return out


SEG_W     = 20.0      # `scan.split_column` 의 비용(자른 자리 잉크 + 1.2 × 칸 높이 고르지 않음)을 이 무게로 섞는다 — 0 이면 모델만


# ── 자르기 후보 만들기 ───────────────────────────────────────────────
def build_plans(geo, centers, span, allow_empty=True, 그림자=None):
    """
    plans[i] = [(칸수, 상자들, flat에서의 시작번호, 개수, 자르기 비용), …]
    flat     = 모든 후보 상자를 한 줄로 (모델에 한 번에 넣으려고)

    칸수 0 = 그 열을 통째로 버리는 선택지. 판심(쪽 이름·쪽 번호)이 열로
    잘못 잡히는 쪽이 있는데, 그것만 버리면 나머지가 한 번에 제자리를 찾는다.
    """
    plans, flat = [], []
    for i, (x0, x1) in enumerate(geo["crop_cols"]):
        opts = []
        sp = geo["spans"][i]
        sm = geo["sm"][i] if 그림자 is None else 그림자[i]   # `그림자` = 읽을 때 검출기로 바꾼 것(`CUT_LEARN`)
        if sp is not None:
            y0, y1 = sp
            cands = scan.cut_points(sm, y0, y1, geo["pitch"])
            for n in range(max(1, centers[i] - span), centers[i] + span + 1):
                cuts, cost = scan.split_column(sm, y0, y1, n, cands)
                if not cuts:
                    continue
                bx = [(x0, a, x1, b) for a, b in zip(cuts[:-1], cuts[1:])]
                opts.append((n, bx, len(flat), len(bx), cost))
                flat.extend(bx)
            if not opts:                    # 한 열이 안 갈라져도 쪽을 버리지 않는다
                n = max(1, centers[i])
                bx = [(x0, int(y0 + (y1-y0)*k/n), x1, int(y0 + (y1-y0)*(k+1)/n))
                      for k in range(n)]
                opts = [(n, bx, len(flat), len(bx), 3.0 * n)]
                flat.extend(bx)
        if allow_empty or not opts:
            opts.append((0, [], len(flat), 0, 0.0))
        plans.append(opts)
    return plans, flat


# ── 정답지가 있을 때 (2단계) ─────────────────────────────────────────
def _match_matrix(pL, pV, pT, rL, rV, rT):
    """후보상자 × 전사글자 점수판. 다 맞으면 1.2, 하나도 안 맞으면 0."""
    mL = (pL[:, None] == rL[None, :])
    mV = (pV[:, None] == rV[None, :])
    mT = (pT[:, None] == rT[None, :])
    M = W_L * mL + W_V * mV + W_T * mT + W_ALL * (mL & mV & mT)
    M[:, (rL < 0) | (rV < 0)] = UNKNOWN
    return M.astype(np.float64), (mL & mV & mT)


def _bonus(plans, geo, logc, page_pitch):
    """글자를 맞춰 보기 전에 '이 자르기가 그럴듯한가'만 따로 매긴다."""
    out = []
    for i, opts in enumerate(plans):
        row = []
        for (n, bx, s0, ln, cost) in opts:
            if ln == 0:
                row.append(0.0); continue
            y0, y1 = geo["spans"][i]
            mlog = float(np.mean(logc[s0:s0 + ln])) if logc is not None else 0.0
            dev = min(abs((y1 - y0) / n - page_pitch) / max(1.0, page_pitch), PITCH_CAP)
            row.append(n * (W_CONF * mlog - W_PITCH * dev * dev) - W_CUT * cost)
        out.append(np.array(row))
    return out


def _solve(plans, M, N, bonus=None):
    """
    열을 왼쪽으로 훑으며 '지금까지 전사문 몇 글자를 썼는가'를 상태로 놓고
    최고점 경로를 찾는다. 한 열이 n 칸이면 그 열은 전사문 n 글자를 가져간다.
    버리는 열은 한 쪽에 하나까지만 허용한다(진짜 본문 열을 버리면 안 되니까).
    반환: [(열번호, 고른후보번호, 시작글자번호), …] 또는 None
    """
    NEG = -1e18
    dp = np.full((2, N + 1), NEG); dp[0][0] = 0.0
    back = []
    for i, opts in enumerate(plans):
        nd = np.full((2, N + 1), NEG)
        bo = np.full((2, N + 1), -1, dtype=np.int32)
        bs = np.zeros((2, N + 1), dtype=np.int8)
        for oi, (n, bx, s0, ln, cost) in enumerate(opts):
            if n > N:
                continue
            K = N - n + 1
            add = np.zeros(K)
            for j in range(n):
                add += M[s0 + j, j:j + K]
            if bonus is not None and n:
                add += bonus[i][oi]
            if n == 0:
                add -= EMPTY_PEN
            for st in (0, 1):
                to = st if n else st + 1
                if to > 1:
                    continue
                cand = np.where(dp[st][:K] > NEG / 2, dp[st][:K] + add, NEG)
                view = nd[to][n:]
                better = cand > view
                view[better] = cand[better]
                bo[to][n:][better] = oi
                bs[to][n:][better] = st
        dp = nd; back.append((bo, bs))

    st = 0 if dp[0][N] >= dp[1][N] else 1
    if dp[st][N] <= NEG / 2:
        return None
    chosen, k = [], N
    for i in range(len(plans) - 1, -1, -1):
        bo, bs = back[i]
        oi = int(bo[st][k])
        if oi < 0:
            return None
        n = plans[i][oi][0]
        if n:
            chosen.append((i, oi, k - n))
        st = int(bs[st][k]); k -= n
    return list(reversed(chosen)) if k == 0 else None


def _readout(chosen, plans, exact, rL, cf, ncol, min_col):
    boxes, assign, mark, conf, percol = [], [], [], [], []
    hit = known = 0
    weak = []
    for i, oi, k0 in chosen:
        n, bx, s0, ln, _ = plans[i][oi]
        ok = kn = 0
        for j in range(n):
            boxes.append(bx[j]); assign.append(k0 + j)
            seen = rL[k0 + j] >= 0                 # 모델이 배운 적 있는 글자인가
            good = bool(exact[s0 + j, k0 + j])
            mark.append(seen and not good)         # 모르는 글자에는 점을 찍지 않는다
            conf.append(float(cf[s0 + j]))
            ok += good; kn += seen
        hit += ok; known += kn
        percol.append((ncol - i, n, ok, kn))
        if kn and ok / kn < min_col:
            weak.append(ncol - i)
    return dict(boxes=boxes, assign=assign, mark=mark, conf=conf,
                hit=hit, known=known, percol=percol, weak=weak)


def to_text(mdl, geo, letters, span=3, min_col=0.45, 경계=False):
    """
    전사문을 정답지 삼아 자르고 짝지어 준다.
    반환: dict(boxes, assign, mark, conf, 일치, …) 또는 None
    경계=True 면 자를 자리를 고를 때 배운 경계 검출기를 섞는다(읽는 경로의 `CUT_LEARN` 과 같은 그림자).
    ⚠ 자동 라벨을 만들 때만 켠다 — 교정서버의 자르기는 꺼 둔 그대로여야 저장된 교정의 상자 좌표가 맞는다(`corpus.same_boxes`).
    """
    N = len(letters)
    ncol = len(geo["cols"])
    base = sum(geo["est"])
    tries = [(list(geo["est"]), span)]
    if abs(N - base) > span * ncol * 0.5:          # 짐작이 크게 빗나가면 넓게 다시
        k = max(0.35, N / max(1, base))
        tries.append(([max(1, int(round(e * k))) for e in geo["est"]],
                      span + 2 + int(abs(N - base) / max(1, ncol))))

    rL, rV, rT = mdl.codes(letters, decompose) if mdl else (
        np.zeros(N, int), np.zeros(N, int), np.zeros(N, int))
    why = "글자 수를 맞추지 못함"
    결과 = None
    for centers, sp in tries:
        # 열을 버리는 선택지는 모델이 있을 때만. 모델 없이는 진짜 본문 열을 버려도 알아챌 수가 없음
        plans, flat = build_plans(geo, centers, sp, allow_empty=bool(mdl),
                                  그림자=경계프로파일(geo) if 경계 else None)
        mins = [min(o[0] for o in c if o[0] > 0) for c in plans
                if any(o[0] > 0 for o in c)]
        lo = sum(mins) - (max(mins) if mins else 0)
        hi = sum(max(o[0] for o in c) for c in plans)
        if not (lo <= N <= hi):
            why = f"글자 수를 맞추지 못함 (그림은 {lo}~{hi}칸, 전사문은 {N}자)"
            continue

        if mdl:
            pL, pV, pT, cf = mdl.read(geo["image"], _맞춤상자(np.asarray(geo["image"]), flat, geo))   # 행간 넓은 쪽만 바뀜
            M, exact = _match_matrix(pL, pV, pT, rL, rV, rT)
            logc = np.log(np.clip(cf, 1e-6, None))
        else:                                       # 모델이 아직 없을 때(첫 문헌)
            M = np.zeros((len(flat), N))             # 맞춰 볼 정답이 없으니 0점
            exact = np.zeros((len(flat), N), dtype=bool)
            cf = np.zeros(len(flat)); logc = None
            rL = np.full(N, -1)

        # 모델이 없으면 글자 맞추기 점수가 전부 0이라 기하 점수만으로 골라야 한다
        first = None if mdl else _bonus(plans, geo, None, geo["pitch"])
        best = None
        ch = _solve(plans, M, N, first)
        if ch:
            best = _readout(ch, plans, exact, rL, cf, ncol, min_col)
            best["방법"] = 1
            seen_p = []
            pit = float(np.median([(geo["spans"][i][1] - geo["spans"][i][0])
                                   / plans[i][oi][0] for i, oi, _ in ch]))
            for step in (2, 3, 4):                  # 잰 자간으로 벌점을 주고 다시 푼다
                if any(abs(pit - q) < q * 0.01 for q in seen_p):
                    break
                seen_p.append(pit)
                ch2 = _solve(plans, M, N, _bonus(plans, geo, logc, pit))
                if not ch2:
                    break
                cand = _readout(ch2, plans, exact, rL, cf, ncol, min_col)
                cand["방법"] = step
                if cand["hit"] > best["hit"]:       # 실제로 더 맞은 쪽만 채택
                    best = cand
                pit = float(np.median([(geo["spans"][i][1] - geo["spans"][i][0])
                                       / plans[i][oi][0] for i, oi, _ in ch2]))
        if best is None:
            continue

        best["일치"] = best["hit"] / max(1, best["known"]) if mdl else None
        best["모름"] = N - best["known"] if mdl else N
        best["사유"] = None
        best["맞춤"] = geo.get("맞춤")              # 행간 넓은 쪽 — 학습 그림도 같은 상자로 오리게
        if not mdl:
            return best
        # 넓게 다시 자른 판(둘째 시도)도 풀어 보고 일치율이 더 높은 쪽을 채용
        if 결과 is None or best["hit"] > 결과["hit"]:
            결과 = best
    return 결과 if 결과 is not None else dict(사유=why)


# ── 정답지가 없을 때 (4단계) ─────────────────────────────────────────
def read_page(mdl, geo, span=3):
    """
    전사문 없이 쪽을 읽는다. 열마다 여러 개수로 잘라 보고 모델이 가장 자신 있어 한 것을 고른다(확신도만 씀).
    기하에 `가장자리=True` 가 서 있으면 양 끝 열을 `가장자리다듬기` 로 가린다.

    반환: (읽은 글자 목록, 확신도 목록)
    """
    out, conf = [], []
    for 글, 확 in read_page_lines(mdl, geo, span):
        out += 글
        conf += 확
    return out, conf


def read_page_lines(mdl, geo, span=3, 띄움=False):
    """
    `read_page` 와 같되 **열마다 나눠서** 돌려준다 — 한 열이 원문의 한 줄.
    반환: [(글자 목록, 확신도 목록), …] 읽는 차례대로. 읽을 것이 없는 열은 뺀다.
    이어 붙이면 `read_page` 와 글자 하나까지 같다.
    띄움=True 면 [(글자, 확신, 빈칸), …] — 빈칸[k] 는 k 번째 글자 뒤를 띄우는가(`띄울자리`). 글자는 그대로.
    """
    열들 = 열마다읽기(mdl, geo, span)
    남 = 가장자리다듬기(geo, 열들) if geo.get("가장자리") else range(len(열들))
    남 = [i for i in 남 if 열들[i] is not None]
    if not 띄움:
        return [부호빼기(열들[i][1], 열들[i][2])[:2] for i in 남]
    빈 = 띄울자리(geo["image"], [(열들[i][1], 열들[i][3]) for i in 남])
    return [부호빼기(열들[i][1], 열들[i][2], b) for i, b in zip(남, 빈)]


# 읽은 결과에서 뺄 글자. 모델은 부호를 알아보고(부호 칸을 한글로 읽지 않게) 결과 글에서만 지운다 —
# 칸 나누기 · 열 고르기 · 띄어쓰기 계산은 부호 칸까지 넣고 끝낸 뒤.
PUNCT_DROP = (",", ".")


def 부호빼기(글, 확, 빈=None):
    """`PUNCT_DROP` 글자를 뺀다. 뺀 글자 뒤가 띄어져 있으면 그 띄움을 앞 글자로 옮긴다(`쉼표 뒤 빈칸` → `앞 글자 뒤 빈칸`).
    반환: (글자, 확신, 빈) — 빈 이 None 이면 None."""
    if not PUNCT_DROP or not any(c in PUNCT_DROP for c in 글):
        return 글, 확, 빈
    g, h, b = [], [], ([] if 빈 is not None else None)
    for k, c in enumerate(글):
        if c in PUNCT_DROP:
            if b is not None and b and 빈[k]:
                b[-1] = True
            continue
        g.append(c); h.append(확[k])
        if b is not None:
            b.append(빈[k])
    if b is not None and b:
        b[-1] = False                     # 열 끝은 늘 False (`띄울자리` 와 같게)
    return g, h, b


# ── 띄어쓰기 ─────────────────────────────────────────────
# 한 열 안 이웃 글자의 잉크 사이 빈틈 ÷ 그 열 칸 높이 중앙값으로 가른다(모델 없이). 문턱은 쪽마다 오츠.
# 잘 안 갈리거나 붙은 무리의 빈틈이 넓으면(붙여 쓴 책) 띄우지 않는다. 열 끝은 못 본다.
SPACE      = True           # `읽기.py`·브라우저판이 띄어쓰기를 넣는가
SPACE_ROW  = 0.03           # 상자 안 한 행의 잉크가 폭의 이 몫(적어도 2px)을 넘으면 잉크 행
SPACE_ETA  = 0.5            # 쪽의 빈틈이 둘로 이만큼(급간 분산 몫) 잘 갈려야 띄운다
SPACE_LOW  = 0.2            # 붙은 무리 빈틈의 중앙값이 이보다 작아야(촘촘한 활자)
SPACE_FRAC = (0.08, 0.6)    # 띄울 자리가 이웃 쌍의 이 몫 안이어야
SPACE_CLIP = (-0.5, 1.5)    # 가를 때 빈틈 값을 이 안으로 자름
# 글자 모양 고침 — 잉크가 칸 안에서 납작하거나 한쪽에 몰린 글자(으 · 오)는 빈틈이 커 보인다. 중성 + 받침 유무마다
# '붙여 쓴 자리의 빈틈이 보통보다 얼마나 큰가' 를 앞 글자 · 뒤 글자로 빼 준다.
SPACE_BEFORE = {"ᅡ": -0.0086, "ᅡ받침": -0.0255, "ᅢ": -0.0064, "ᅢ받침": -0.0391, "ᅣ": -0.011, "ᅣ받침": -0.0323,
                "ᅥ": 0.0028, "ᅥ받침": -0.0175, "ᅦ": -0.0149, "ᅦ받침": -0.0331, "ᅧ": 0.0099, "ᅧ받침": -0.0241,
                "ᅨ": 0.0314, "ᅩ": 0.0596, "ᅩ받침": -0.0223, "ᅪ": -0.0257, "ᅪ받침": -0.0221, "ᅬ": -0.0025,
                "ᅬ받침": -0.0313, "ᅭ": 0.0368, "ᅭ받침": -0.0329, "ᅮ": 0.0087, "ᅮ받침": -0.0187, "ᅯ": 0.0023,
                "ᅯ받침": -0.0263, "ᅱ": -0.0018, "ᅱ받침": -0.0404, "ᅲ": -0.0208, "ᅲ받침": -0.0474, "ᅳ": 0.092,
                "ᅳ받침": -0.011, "ᅴ": 0.0027, "ᅵ": 0.004, "ᅵ받침": -0.0144, "ᆞ": 0.0422, "ᆞ받침": -0.006,
                "ᆡ": -0.0016, "ᆡ받침": -0.0286}
SPACE_AFTER = {"ᅡ": -0.0077, "ᅡ받침": -0.0153, "ᅢ": -0.005, "ᅢ받침": -0.0397, "ᅣ": 0.0047, "ᅣ받침": -0.0127,
               "ᅥ": -0.0077, "ᅥ받침": -0.0062, "ᅦ": -0.0181, "ᅦ받침": -0.0395, "ᅧ": -0.0036, "ᅧ받침": -0.0119,
               "ᅨ": -0.0092, "ᅩ": 0.083, "ᅩ받침": -0.0125, "ᅪ": -0.0233, "ᅪ받침": -0.0221, "ᅬ": -0.0097,
               "ᅭ": 0.0449, "ᅭ받침": -0.0367, "ᅮ": 0.0265, "ᅮ받침": -0.011, "ᅯ": -0.0013, "ᅯ받침": -0.0226,
               "ᅱ": -0.0249, "ᅱ받침": -0.1139, "ᅲ": -0.0105, "ᅲ받침": -0.0101, "ᅳ": 0.0786, "ᅳ받침": -0.011,
               "ᅴ": -0.014, "ᅵ": 0.0001, "ᅵ받침": -0.0065, "ᆞ": 0.0199, "ᆞ받침": 0.0086, "ᆡ": 0.0142,
               "ᆡ받침": -0.0417, "○": -0.0422, "ㅣ": 0.0472}


def _띄움모양(c):
    """고침표의 열쇠 — 중성(없으면 글자 그대로) + 받침이 있으면 '받침'."""
    return (c[1] if len(c) > 1 else c) + ("받침" if len(c) > 2 else "")


def _잉크위아래(g, b):
    """상자 b 안에서 잉크 행의 첫 · 끝(쪽 좌표). 없으면 None."""
    x0, y0, x1, y1 = (int(v) for v in b)
    c = g[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] < scan.INK
    if c.size == 0:
        return None
    행 = np.nonzero(c.sum(1) > max(2, (x1 - x0) * SPACE_ROW))[0]
    return None if not len(행) else (max(0, y0) + int(행[0]), max(0, y0) + int(행[-1]))


def 빈틈값(글, 상, 잉크):
    """한 열의 이웃 글자 쌍마다 (잉크 빈틈 ÷ 칸 높이 중앙값) − 모양 고침. 잴 수 없으면 None."""
    if not 상:
        return []
    h = float(np.median([int(b[3]) - int(b[1]) for b in 상]))
    out = []
    for k in range(len(글) - 1):
        a, b = 잉크[k], 잉크[k + 1]
        if a is None or b is None or h <= 0:
            out.append(None); continue
        x = (b[0] - a[1]) / h
        x -= SPACE_BEFORE.get(_띄움모양(글[k]), 0.0) + SPACE_AFTER.get(_띄움모양(글[k + 1]), 0.0)
        out.append(x)
    return out


def 빈틈가르기(값들):
    """
    쪽의 빈틈 값들을 둘로 가르는 문턱(오츠 — 정렬한 값 사이 모든 자리를 봄). 띄우지 말아야 하면 None.
    ⚠ 합은 앞에서부터 차례로(브라우저판과 같게) — numpy 합은 모으는 차례가 달라 쓰지 않는다.
    """
    lo, hi = SPACE_CLIP
    v = sorted(min(max(float(x), lo), hi) for x in 값들)
    n = len(v)
    if n < 10:
        return None
    누적 = [0.0]
    for x in v:
        누적.append(누적[-1] + x)
    m = 누적[-1] / n
    제곱 = 0.0
    for x in v:
        제곱 += (x - m) * (x - m)
    if 제곱 <= 0:
        return None
    최고, 자리 = -1.0, None
    for i in range(1, n):
        if v[i - 1] == v[i]:
            continue
        ma, mb = 누적[i] / i, (누적[-1] - 누적[i]) / (n - i)
        s = i * (n - i) * (ma - mb) * (ma - mb)
        if s > 최고:
            최고, 자리 = s, i
    if 자리 is None:
        return None
    η = 최고 / (n * 제곱)
    i = 자리
    아래 = v[(i - 1) // 2] if i % 2 else (v[i // 2 - 1] + v[i // 2]) / 2
    위몫 = (n - i) / n
    if η < SPACE_ETA or 아래 >= SPACE_LOW or not (SPACE_FRAC[0] <= 위몫 <= SPACE_FRAC[1]):
        return None
    return (v[i - 1] + v[i]) / 2


def 띄울자리(image, 줄들):
    """
    줄들 = [(글자 목록, 글자마다 상자), …] (한 쪽). 반환: 줄마다 [글자 뒤를 띄우는가, …] (글자 수와 같은 길이, 끝은 늘 False).
    """
    g = np.asarray(image)
    값 = [빈틈값(글, 상, [_잉크위아래(g, b) for b in 상]) for 글, 상 in 줄들]
    t = 빈틈가르기([x for 열 in 값 for x in 열 if x is not None])
    return [[(t is not None and x is not None and x > t) for x in 열] + ([False] if 글 else [])
            for 열, (글, _) in zip(값, 줄들)]


def _맞춤상자(g, boxes, geo):
    """행간이 넓은 쪽(`geo["맞춤"]` — `scan.CROP_FIT`)이면 모델에 넣을 상자를 칸 안 잉크의 가운데에 맞춘 글자 크기 정사각형으로.
    칸 자체(자른 자리 · 글자 차례 · 띄어쓰기)는 그대로 — 모델이 보는 그림만 바뀜. 잉크가 없는 칸 · 글자보다 큰 잉크는 그대로 둠."""
    S = geo.get("맞춤")
    if not S:
        return boxes
    out = []
    for b in boxes:
        x0, y0, x1, y1 = b
        c = (g[y0:y1, x0:x1] < scan.INK).any(axis=1)
        if y1 - y0 <= S or not c.any():
            out.append(b); continue
        ys = np.nonzero(c)[0]
        a, z = y0 + int(ys[0]), y0 + int(ys[-1]) + 1
        if z - a >= S:
            out.append(b); continue
        m = (a + z) / 2
        na = int(round(min(max(m - S / 2, y0), y1 - S)))
        out.append((x0, na, x1, int(round(na + S))))
    return out


def 열마다읽기(mdl, geo, span=3):
    """
    열마다 가장 자신 있는 칸수로 읽는다. `read_page` 의 앞 절반.
    반환: 열마다 (로그 확신 평균, 글자들, 확신들, 글자마다 상자, 잘라 본 칸 수) — 읽을 것이 없는 열은 None.

    글자가 아닌 칸은 뺀다: 확신이 `NOTCHAR_CONF` 보다 낮은 칸 중 잉크 폭이 상자의 `NOTCHAR_WIDTH` 가 안 되는 것
    (작은 한자 절 번호)과 한 행이 폭의 `NOTCHAR_ROW` 를 채우는 것(광곽 가로줄).
    ⚠ 열 점수(첫 값)는 뺀 칸까지 다 넣어 낸다 — `가장자리다듬기` 의 판단을 바꾸지 않으려고.
    """
    plans, flat = (모델자르기계획(mdl, geo, span) if SEG_MODEL
                   else build_plans(geo, geo["est"], span, allow_empty=False,
                                    그림자=경계프로파일(geo) if CUT_LEARN else None))
    g = np.array(geo["image"])
    pL, pV, pT, cf = mdl.read(geo["image"], _맞춤상자(g, flat, geo))
    logc = np.log(np.clip(cf, 1e-6, None))
    out = []
    for opts in plans:
        opts = [o for o in opts if o[0] > 0]
        if not opts:
            out.append(None)
            continue
        # 산술평균은 몇 개의 엉망인 칸을 나머지가 가려 버린다. 기하평균을 쓴다.
        n, bx, s0, ln, _ = max(opts, key=lambda o: float(np.mean(logc[o[2]:o[2]+o[3]])))
        글, 확, 상 = [], [], []
        for j in range(ln):
            c = float(cf[s0 + j])
            자 = mdl.letter(pL[s0+j], pV[s0+j], pT[s0+j])
            if c < NOTCHAR_CONF and 자 not in NOTCHAR_KEEP:
                폭, 가로 = scan.칸모양(g, bx[j])
                if 폭 < NOTCHAR_WIDTH or 가로 >= NOTCHAR_ROW:
                    continue
            글.append(자); 확.append(c); 상.append(bx[j])
        out.append((float(np.mean(logc[s0:s0+ln])), 글, 확, ln, 상))
    if HEADING:
        큰제목읽기(mdl, geo, out, span)
    if BUNJU:
        분주읽기(mdl, geo, out)
    # 넷째 = 글자를 낸 칸의 상자들(글자와 같은 차례) · 다섯째 = 잘라 본 칸 수(뺀 칸 포함 — 끝 열 보호가 씀)
    return [None if o is None else (o[0], o[1], o[2], o[4], o[3]) for o in out]


BUNJU      = True    # (읽을 때만, 2026-10-09) 열 안의 두 줄(분주 · 협주)을 갈라 읽어 보고 모델이 뚜렷이 자신 있을 때만 바꿈 — `분주읽기`
BUNJU_GAIN = 0.3     # 갈라 읽은 쪽의 로그 확신 평균이 이만큼 넘게 나을 때만
BUNJU_CONF = 0.5     # 갈라 읽은 칸들의 확신(기하평균)이 이보다 낮으면 버림
BUNJU_H    = (0.45, 0.55, 0.7, 0.85, 1.0)   # 분주 글자 높이 후보(세로 자간의 배) — 작은 협주부터 보통 크기(증남포)까지
BUNJU_MINC = 2       # 바꿀 칸이 이보다 적거나 갈라 읽은 한쪽 줄이 이보다 짧으면 안 바꿈(한 글자를 반으로 갈라 읽는 헛켜짐)
BUNJU_BAR  = 0.25    # 갈라 읽은 글자 중 'ㅣ' 가 이 몫을 넘으면 안 바꿈(계선 · 광곽 줄을 ㅣ 로 읽는 헛켜짐)


def _줄읽기(mdl, geo, x0, x1, y0, y1):
    """[x0, x1) × [y0, y1) 을 한 줄로 보고 칸 수를 모델 확신으로 골라 읽음 — (로그 확신 합, 글자, 확신, 상자) 또는 None."""
    g = np.asarray(geo["image"])
    prof = (g[:, x0:x1] < scan.INK).sum(axis=1).astype(float)
    sm = scan.smooth(prof, max(2.0, geo["pitch"] / 9))
    r = _잉크범위(sm, y0, y1)
    if r is None or r[1] - r[0] < geo["pitch"] * 0.3:
        return None
    a, b = r
    최고 = None
    후보, 상자들 = [], []
    for hm in BUNJU_H:
        h = geo["pitch"] * hm
        n = max(1, int(round((b - a) / h)))
        cuts, _ = scan.split_column(sm, a, b, n, scan.cut_points(sm, a, b, h))
        if not cuts:
            cuts = [int(a + (b - a) * k / n) for k in range(n + 1)]
        bx = [(x0, p, x1, q) for p, q in zip(cuts[:-1], cuts[1:])]
        후보.append((n, bx, len(상자들)))
        상자들.extend(bx)
    # 후보 순서와 점수 계산은 유지하고 모델 호출만 묶는다.
    전체L, 전체V, 전체T, 전체cf = mdl.read(geo["image"], 상자들)
    for n, bx, 시작 in 후보:
        끝 = 시작 + len(bx)
        pL, pV, pT, cf = (v[시작:끝] for v in (전체L, 전체V, 전체T, 전체cf))
        lg = np.log(np.clip(cf, 1e-6, None))
        if 최고 is None or lg.mean() > 최고[0] / len(최고[1]):
            최고 = (float(lg.sum()), [mdl.letter(pL[j], pV[j], pT[j]) for j in range(n)], [float(c) for c in cf], bx)
    return 최고


def 분주읽기(mdl, geo, out):
    """
    열 안에 두 줄로 찍힌 분주(협주)를 갈라 읽는다 — 읽는 경로에만. `scan.분주후보` 가 느슨하게 잡은 구간마다
    지금 읽은 칸들(가운데가 그 구간 안)과, 열 가운데를 경계로 오른쪽 줄 → 왼쪽 줄로 갈라 읽은 판을 견주어
    로그 확신 평균이 `BUNJU_GAIN` 넘게 낫고 기하평균 확신이 `BUNJU_CONF` 넘을 때만 바꾼다(전사문 `{{분주|오른|왼}}` 차례와 같음).
    `out` 을 제자리에서 고친다. 열 점수(첫 값)는 그대로.
    """
    if hasattr(mdl, "그림고정"):
        with mdl.그림고정(geo["image"]):
            return _분주읽기(mdl, geo, out)
    return _분주읽기(mdl, geo, out)


def _분주읽기(mdl, geo, out):
    g = np.asarray(geo["image"])
    for i, o in enumerate(out):
        if o is None or not geo["spans"][i]:
            continue
        for (y0, y1, lo, cx, hi) in scan.분주후보(g, geo["cols"], i, geo["spans"][i], geo["pitch"]):
            o = out[i]
            안 = [j for j, b in enumerate(o[4]) if y0 <= (b[1] + b[3]) / 2 < y1]
            if not 안:
                continue
            Y0, Y1 = min(y0, o[4][안[0]][1]), max(y1, o[4][안[-1]][3])
            옛 = float(np.mean(np.log(np.clip([o[2][j] for j in 안], 1e-6, None))))
            오 = _줄읽기(mdl, geo, cx, hi, Y0, Y1)
            왼 = _줄읽기(mdl, geo, lo, cx, Y0, Y1)
            if 오 is None or 왼 is None:
                continue
            n = len(오[1]) + len(왼[1])
            if len(안) < BUNJU_MINC or min(len(오[1]), len(왼[1])) < BUNJU_MINC or                     sum(c == "ㅣ" for c in 오[1] + 왼[1]) > n * BUNJU_BAR:
                continue
            새 = (오[0] + 왼[0]) / n
            if 새 <= 옛 + BUNJU_GAIN or 새 < np.log(BUNJU_CONF):
                continue
            a, b = 안[0], 안[-1] + 1
            out[i] = (o[0], o[1][:a] + 오[1] + 왼[1] + o[1][b:], o[2][:a] + 오[2] + 왼[2] + o[2][b:],
                      o[3], o[4][:a] + 오[3] + 왼[3] + o[4][b:])


HEADING_INK = 0.15     # 잉크가 그 구간 최댓값의 이 몫을 넘는 첫·끝 자리부터 칸을 나눈다(위아래 빈 여백을 칸으로 읽지 않게)


def _잉크범위(prof, y0, y1, 틈=None):
    """[y0, y1) 에서 **처음 잉크 덩어리**의 첫 자리와 끝 자리 — 없으면 None.
    `틈`(px) 넘게 비면 거기서 끊는다 — 짧은 부제 아래 빈 여백 끝의 광곽 줄·잡티까지 늘리지 않게."""
    seg = np.asarray(prof[y0:y1], dtype=float)
    if not len(seg) or seg.max() <= 0:
        return None
    on = np.nonzero(seg > seg.max() * HEADING_INK)[0]
    if not len(on):
        return None
    끝 = on[0]
    for y in on[1:]:
        if 틈 is not None and y - 끝 > 틈:
            break
        끝 = y
    return (y0 + int(on[0]), y0 + int(끝) + 1)


def _구간읽기(mdl, geo, i, y0, y1, span):
    """열 i 의 [y0, y1) 만 따로 칸을 나눠 읽는다. 반환: (로그 확신 합, 칸 수, 글자, 확신, 상자) — 못 읽으면 None."""
    x0, x1 = geo["crop_cols"][i]
    sm = geo["sm"][i]
    r = _잉크범위(sm, y0, y1, geo["pitch"] * 1.5) if y1 - y0 >= geo["pitch"] * 0.6 else None
    if r is None or r[1] - r[0] < geo["pitch"] * 0.6:
        return (0.0, 0, [], [], [])
    y0, y1 = r
    cands = scan.cut_points(sm, y0, y1, geo["pitch"])
    est = max(1, int(round((y1 - y0) / geo["pitch"])))
    best = None
    for n in range(max(1, est - span), est + span + 1):
        cuts, _ = scan.split_column(sm, y0, y1, n, cands)
        if not cuts:                    # 골짜기가 모자라면 고르게 — `build_plans` 와 같게
            cuts = [int(y0 + (y1 - y0) * k / n) for k in range(n + 1)]
        bx = [(x0, a, x1, b) for a, b in zip(cuts[:-1], cuts[1:])]
        pL, pV, pT, cf = mdl.read(geo["image"], bx)
        lg = np.log(np.clip(cf, 1e-6, None))
        if best is None or lg.mean() > best[0] / best[1]:
            best = (float(lg.sum()), n, [mdl.letter(pL[j], pV[j], pT[j]) for j in range(n)],
                    [float(c) for c in cf], bx)
    return best


def 큰제목읽기(mdl, geo, out, span=3):
    """
    두 열에 걸쳐 찍힌 큰 활자 편 제목을 넓은 칸으로 다시 읽는다 — 읽는 경로에만.

    이웃한 두 열이 함께 확신이 낮으면 두 열을 합친 x 범위 위쪽에 큰 글자 k 개(높이 h)를 두고,
    그 아래는 두 열을 따로 읽는 판을 만들어 로그 확신 평균이 뚜렷이 나을 때만 바꾼다.
    읽는 차례: 큰 제목 → 오른쪽 열 나머지 → 왼쪽 열 나머지(전사문 차례와 같음). 열 점수(첫 값)는 그대로 둔다.
    `out` 을 제자리에서 고친다.
    """
    점 = [o[0] for o in out if o is not None]
    if len(점) < 5:
        return
    가운데 = float(np.median(점))
    sp, cc = geo["spans"], geo["crop_cols"]
    i = 0
    while i + 1 < len(out):
        a, b = out[i], out[i + 1]
        if (a is None or b is None or sp[i] is None or sp[i + 1] is None
                or a[0] > 가운데 - HEADING_LOW or b[0] > 가운데 - HEADING_LOW):
            i += 1; continue
        X0, X1 = min(cc[i][0], cc[i + 1][0]), max(cc[i][1], cc[i + 1][1])
        y0 = min(sp[i][0], sp[i + 1][0])
        합쳐 = np.asarray(geo["sm"][i], dtype=float) + np.asarray(geo["sm"][i + 1], dtype=float)
        r = _잉크범위(합쳐, y0, max(sp[i][1], sp[i + 1][1]))
        if r is None:
            i += 1; continue
        y0 = r[0]
        옛 = (a[0] * a[3] + b[0] * b[3]) / max(1, a[3] + b[3])
        최고 = None
        for k in HEADING_K:
            for hm in HEADING_H:
                h = geo["xpitch"] * hm
                y1 = int(y0 + k * h)
                if y1 >= max(sp[i][1], sp[i + 1][1]):
                    continue
                cuts, _ = scan.split_column(합쳐, y0, y1, k, scan.cut_points(합쳐, y0, y1, h))
                if not cuts:
                    continue
                bx = [(X0, p, X1, q) for p, q in zip(cuts[:-1], cuts[1:])]
                pL, pV, pT, cf = mdl.read(geo["image"], bx)
                제 = [mdl.letter(pL[j], pV[j], pT[j]) for j in range(k)]
                if any(x in NOTCHAR_KEEP for x in 제):   # 큰 제목 칸이 `ㅣ` = 광곽 세로줄을 읽은 것
                    continue
                lg = np.log(np.clip(cf, 1e-6, None))
                if float(lg.mean()) < np.log(HEADING_CONF):   # 본문 글자 둘을 큰 글자 하나로 읽은 것
                    continue
                ra = _구간읽기(mdl, geo, i, y1, sp[i][1], span)
                rb = _구간읽기(mdl, geo, i + 1, y1, sp[i + 1][1], span)
                if ra is None or rb is None:
                    continue
                n = k + ra[1] + rb[1]
                v = (float(lg.sum()) + ra[0] + rb[0]) / n
                if 최고 is None or v > 최고[0]:
                    최고 = (v, 제 + ra[2], [float(c) for c in cf] + ra[3], rb[2], rb[3], bx + ra[4], rb[4])
        if 최고 is not None and 최고[0] > 옛 + HEADING_GAIN:
            out[i] = (a[0], 최고[1], 최고[2], a[3], 최고[5])
            out[i + 1] = (b[0], 최고[3], 최고[4], b[3], 최고[6])
            i += 2
        else:
            i += 1


def 모델자르기계획(mdl, geo, span=3):
    """
    `build_plans` 와 같은 모양(allow_empty=False)이되 자를 자리를 모델이 고른다(`SEG_MODEL`).
    골짜기 후보(`scan.cut_points`) 사이의 구간을 칸 높이 0.45~2 배 안에서 모두 읽어, n 마다 로그 확신 합
    (− `SEG_W` × 자르기 비용)이 가장 큰 자르기를 동적 계획법으로 찾는다. n 은 `열마다읽기` 가 확신 평균으로 고른다.
    """
    centers = geo["est"]
    열후보, 구간 = [], []
    for i, (x0, x1) in enumerate(geo["crop_cols"]):
        sp = geo["spans"][i]
        if sp is None:
            열후보.append(None); continue
        y0, y1 = sp
        cands = scan.cut_points(geo["sm"][i], y0, y1, geo["pitch"])
        pts = [y0] + [c for c in cands if y0 < c < y1] + [y1]
        ns = list(range(max(1, centers[i] - span), centers[i] + span + 1))
        lo, hi = (y1 - y0) / max(ns) * 0.45, (y1 - y0) / min(ns) * 2.0
        segs = []
        for a in range(len(pts)):
            for b in range(a + 1, len(pts)):
                h = pts[b] - pts[a]
                if h < lo:
                    continue
                if h > hi:
                    break
                segs.append((a, b, len(구간)))
                구간.append((x0, pts[a], x1, pts[b]))
        열후보.append((pts, segs, ns))
    lg = []
    if 구간:
        _, _, _, cf = mdl.read(geo["image"], 구간)
        lg = np.log(np.clip(cf, 1e-6, None)).tolist()
    plans, flat, NEG = [], [], -1e18
    for i, (x0, x1) in enumerate(geo["crop_cols"]):
        opts, e = [], 열후보[i]
        if e is not None:
            pts, segs, ns = e
            m, y0, y1 = len(pts), pts[0], pts[-1]
            for n in ns:
                p = (y1 - y0) / n
                lo, hi = p * 0.45, p * 2.0
                sm = geo["sm"][i]
                mx = max(1.0, float(np.max(sm[y0:min(y1, len(sm))])))
                쓸 = [(a, b, lg[k] - SEG_UNIF * ((pts[b] - pts[a] - p) / p) ** 2
                       - SEG_W * (1.2 * ((pts[b] - pts[a] - p) / p) ** 2
                                  + (sm[min(pts[b], len(sm) - 1)] / mx if b < m - 1 else 0.0)))
                      for a, b, k in segs if lo <= pts[b] - pts[a] <= hi]
                dp = [[NEG] * m for _ in range(n + 1)]
                prev = [[-1] * m for _ in range(n + 1)]
                dp[0][0] = 0.0
                for c in range(1, n + 1):
                    앞, 지금, 뒤 = dp[c - 1], dp[c], prev[c]
                    for a, b, v in 쓸:
                        if 앞[a] > NEG and 앞[a] + v > 지금[b]:
                            지금[b] = 앞[a] + v; 뒤[b] = a
                if dp[n][m - 1] <= NEG:
                    continue
                cuts, j = [], m - 1
                for c in range(n, 0, -1):
                    cuts.append(pts[j]); j = prev[c][j]
                cuts.append(pts[0])
                cuts.sort()
                bx = [(x0, a, x1, b) for a, b in zip(cuts[:-1], cuts[1:])]
                opts.append((n, bx, len(flat), len(bx), 0.0))
                flat.extend(bx)
            if not opts:                       # 한 열이 안 갈라져도 쪽을 버리지 않는다 — `build_plans` 와 같게
                n = max(1, centers[i])
                bx = [(x0, int(y0 + (y1 - y0) * k / n), x1, int(y0 + (y1 - y0) * (k + 1) / n)) for k in range(n)]
                opts = [(n, bx, len(flat), len(bx), 3.0 * n)]
                flat.extend(bx)
        plans.append(opts)
    return plans, flat


EDGE_MEDIAN = 0.6     # 끝 열 보호 — 글자 수가 열들 중앙값의 이 몫 넘고
EDGE_MEDIAN_LOW = 0.15  #   확신 0.5 미만 칸이 이 몫 이하인 열은 확신으로 떼지 않음. None = 끔


def 가장자리다듬기(geo, 열들, δ=EDGE_DROP, 최대=EDGE_MAX, 겹침=EDGE_OVERLAP,
                안δ=EDGE_DROP_IN):
    """
    읽을 때 쪽 양 끝의 열을 모델 확신도로 가린다. 반환: 남길 열 번호(차례대로).

    `scan._가장자리후보` 가 양 끝에 붙여 온 후보 열에서 ① 겹친 이웃은 점수 높은 쪽만 남기고
    ② 끝에서부터, 가운데 열들(양 끝 둘씩 뺀 것)의 중앙값보다 로그 확신이 `δ` 넘게 낮은 열을 뗀다(한쪽 `최대` 까지).
    끝 열 쪽 이웃 사이에 광곽 세로줄(`scan.세로줄있나`)이 있으면 그 너머를 버리고, 그쪽 남은 끝 열은 `안δ` 까지 봐준다.
    ⚠ 읽는 경로만 — 자르는 경로(`to_text`)는 열을 0 칸으로 버리는 선택지로 대신한다.
    """
    점 = lambda i: -9.0 if 열들[i] is None else 열들[i][0]
    보호 = lambda i, j: False
    if EDGE_MEDIAN:
        # 끝 열 보호 — 바로 바깥 이웃(j)이 광곽 세로줄 열('ㅣ' 막대)이고, 본문만큼 길고, 남은 칸이 거의 다 잘 읽힌
        #   열은 확신으로 떼지 않음. ⚠ 바깥 이웃 조건이 없으면 판심 글씨 열이 남는다.
        길이 = sorted(len(o[1]) for o in 열들 if o is not None)
        긴열 = (길이[len(길이) // 2] if 길이 else 0) * EDGE_MEDIAN
        def 보호(i, j):
            o = 열들[i]
            if o is None or len(o[2]) == 0 or len(o[1]) < 긴열 or not (0 <= j < len(열들)) or not 막대(j):
                return False
            return float(np.mean(np.asarray(o[2]) < 0.5)) <= EDGE_MEDIAN_LOW
    가운데 = lambda i: (geo["cols"][i][0] + geo["cols"][i][1]) / 2
    남 = list(range(len(열들)))
    k = 0
    while k < len(남) - 1:
        a, b = 남[k], 남[k + 1]
        if abs(가운데(a) - 가운데(b)) < geo["xpitch"] * 겹침:
            del 남[k + 1 if 점(a) >= 점(b) else k]
        else:
            k += 1
    안 = [열들[i][0] for i in 남[2:-2] if 열들[i] is not None]
    기준 = float(np.median(안)) if 안 else -1.0

    # 광곽 세로줄 — 양쪽마다 가장 안쪽 줄을 찾아 그 너머를 뗀다
    속 = [geo["spans"][i] for i in 남[2:-2] if geo["spans"][i]]
    d앞 = d뒤 = δ
    if 속 and len(남) > 4:
        g = np.array(geo["image"])
        T, B = min(s[0] for s in 속), max(s[1] for s in 속)
        줄 = lambda i, j: scan.세로줄있나(g, 가운데(i), 가운데(j), T, B)
        # 계선 판(열마다 세로줄) — 떼일 열들이 본문 같으면 떼지 않는다: 절반 이상 확신이 가운데만큼이고(기준 − δ)
        #   안쪽 열까지 자간 간격으로 고르게 이어지면. 맞은편 쪽 열은 제본 골에서 간격이 끊김.
        def 본문같음(떼일, 안쪽):
            if EDGE_GUIDE is None or len(떼일) < 2:      # 광곽 밖 한 열만 떼는 것은 그대로 — 여백의 큰 장 제목
                return False
            좋음 = sum(열들[i] is not None and 열들[i][0] >= 기준 - δ for i in 떼일)
            잇 = 떼일 + [안쪽]
            고름 = all(abs(abs(가운데(a) - 가운데(b)) - geo["xpitch"]) <= geo["xpitch"] * EDGE_GUIDE
                     for a, b in zip(잇, 잇[1:]))
            return 고름 and 좋음 * 2 >= len(떼일)
        for t in range(min(최대, len(남) - 5), 0, -1):            # 앞(오른쪽) 끝
            if 줄(남[t], 남[t - 1]) and not 본문같음(남[:t], 남[t]):
                del 남[:t]; d앞 = 안δ; break
        for t in range(min(최대, len(남) - 5), 0, -1):            # 뒤(왼쪽) 끝
            if 줄(남[-1 - t], 남[-t]) and not 본문같음(남[-t:][::-1], 남[-1 - t]):
                del 남[-t:]; d뒤 = 안δ; break

    # 광곽 세로줄을 한 열 통째 `ㅣ` 로 자신 있게 읽으면 확신으로는 못 떼므로 따로 뗀다(`EDGE_BAR`)
    막대 = lambda i: (EDGE_BAR is not None and 열들[i] is not None and len(열들[i][1]) > 0
                     and sum(자 == "ㅣ" for 자 in 열들[i][1]) > EDGE_BAR * len(열들[i][1]))
    def 막대줄(i):
        if EDGE_BAR_RUN is None or 열들[i] is None:
            return False
        n = 0
        for 자 in 열들[i][1]:
            n = n + 1 if 자 == "ㅣ" else 0
            if n > EDGE_BAR_RUN:
                return True
        return False
    나쁨 = lambda i, d, j: 열들[i] is None or (점(i) < 기준 - d and not 보호(i, j)) or 막대(i) or 막대줄(i)
    for _ in range(최대):
        if len(남) > 4 and 나쁨(남[0], d앞, 남[0] - 1): 남.pop(0)
        else: break
    for _ in range(최대):
        if len(남) > 4 and 나쁨(남[-1], d뒤, 남[-1] + 1): 남.pop()
        else: break
    return 남
