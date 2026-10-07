# -*- coding: utf-8 -*-
"""
정렬 — 열을 몇 칸으로 자를지 정한다. 이 프로젝트의 심장이다.

이미지만 보고 정하려 하면 실패한다. 쪽마다 활자 크기가 10%까지 다르고,
한 열에서 한 칸이 밀리면 그 뒤가 통째로 어긋나기 때문이다.

그래서 **위키문헌 전사문을 정답지로 쓴다.**
열마다 여러 개수로 잘라 본 다음, 모델이 읽은 글자가 전사문과 가장 잘 맞는
조합을 쪽 전체에서 한꺼번에 고른다(열을 순서대로 훑는 동적 계획법).

정답지가 없을 때(4단계, 새 쪽을 실제로 읽을 때)는 같은 후보들 중에서
모델이 가장 자신 있어 하는 것을 고른다.
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
EDGE_BAR     = 0.5    # 끝 열의 글자가 이 몫 넘게 `ㅣ` 면 광곽 세로줄로 보고 뗀다 (None = 끔, 2026-09-27)
EDGE_GUIDE   = 0.3    # 세로줄 너머 떼일 열(둘 이상)이 본문처럼 보이면(확신 · 간격이 자간 ±이 몫) 떼지 않음 — 계선 판 (None = 끔, 2026-10-01)

# ── 읽을 때 글자가 아닌 칸 빼기 (`열마다읽기`) ────────────────────────
NOTCHAR_CONF  = 0.5   # 확신이 이보다 낮고
NOTCHAR_WIDTH = 0.5   # 잉크 폭이 상자의 이만큼 안 되면 → 작은 절 번호(十八 · 三十)
NOTCHAR_ROW   = 0.9   # 또는 한 행이 폭의 이만큼을 채우면 → 광곽 가로줄
NOTCHAR_KEEP  = ("ㅣ",)  # 모델이 이 글자로 읽은 칸은 빼지 않는다 — 주격 조사 ㅣ 는 가늘다
# ⚠ 가로줄 판정에 '잉크 높이 < 상자의 절반' 을 더해 보았다가 나빠짐(떼어 둔 4.05 → 4.12%, 2026-09-27) — 하지 말 것

# ── 읽을 때 두 열에 걸친 큰 활자 편 제목 (`큰제목읽기`, 2026-09-28) ────────
HEADING      = True   # 이웃한 두 열이 함께 확신이 낮을 때 '두 열을 합친 넓은 칸' 으로 위쪽을 다시 읽어 본다
                      # 떼어 둔 3.76 → 3.63% · 고르는 5.15 → 5.08%(시편촬요 8.71 → 7.92 · 권2 6.77 → 6.43, 다섯 문헌 그대로)
HEADING_LOW  = 0.25   # 두 열의 로그 확신이 쪽 가운데값보다 이만큼 넘게 낮을 때만 해 본다
HEADING_GAIN = 0.10   # 다시 읽은 쪽의 로그 확신 평균이 이만큼 넘게 나을 때만 바꾼다
HEADING_K    = (2, 3, 4, 5, 6)          # 큰 글자 수 후보
HEADING_H    = (1.5, 1.7, 1.9, 2.1)     # 큰 글자 높이 후보(열 간격의 배)
HEADING_CONF = 0.5    # 큰 글자 칸들의 확신(기하평균)이 이보다 낮으면 버린다 — 진짜 큰 제목은 넓은 칸으로 읽으면 자신 있다

# ── 읽을 때 자를 자리를 모델이 고르기 (`모델자르기계획`, 2026-09-28 · 시험 중) ────────
SEG_MODEL = False     # 켜면 열마다 골짜기 사이 구간을 모두 읽어, 칸 수마다 **모델 확신 합이 가장 큰** 자르기를 고른다
SEG_UNIF  = 0.0       # 칸 높이가 고르지 않은 만큼의 벌점(칸마다, ((h − p)/p)² 배) — 0 이면 모델만 본다
# ── 읽을 때 자를 자리를 배운 경계 검출기로 (`근원/부품/경계검출.py`, 2026-09-28 · 시험 중) ────────
CUT_LEARN = True      # 자를 후보·비용에 검출기의 '경계가 아닐 확률' 을 섞는다(몫 `CUT_MIX`) — 읽는 경로에만
                      # 떼어 둔 3.63 → 2.52% · 고르는 5.08 → 4.47%(여덟 문헌 다 좋아짐 · 고르는 쪽 훈아진언만 +0.3)
CUT_MIX   = 0.5       # 1 = 검출기만(떼어 둔 쪽에서 비슷 · 고르는 4.52%) · 0 = 잉크 그림자만(예전)
CUT_CLIP  = 0.0       # 경계 확률을 [이것, 1 − 이것] 으로 자른다 — 0 = 자르지 않음(아래 ⚠)
CUT_ROUND = 10000     # 경계 확률을 1/이것 단위로 반올림(은행가) — 빈 종이에서 검출기가 내는 '평평한' 값을 정확히 평평하게
CUT_LEARN_PATH = os.path.join(경로.모델, "경계검출.pt")    # `제작/실험/실험27_경계검출.py` 로 만듦 — 사본 `모델/백업/실험_20260928_경계검출.pt`
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
        # ⚠ 브라우저판과 맞추기(2026-09-28): 처음 대조에서 916칸 중 19칸 · 글자 1,652개가 갈렸는데, 뿌리는 **검출기를
        #   GPU 로 돌린 것**(합성곱 TF32 → ONNX 와 로짓 7e-3 차이)이었다 — `경계검출.검출기` 를 CPU FP32 로(차이 1.5e-5).
        #   반올림(1e-3)·자르기([0.02, 0.98])는 **오히려 나빴다** — 계단·평평한 구간을 만들어 그 끝(자를 후보)이
        #   작은 차이에 한 줄씩 옮겨 갔다(자르기로 23칸 · 1,530자) — 그때는 GPU 잡음(7e-3)이 커서였다.
        #   CPU FP32 + float64 시그모이드(차이 2e-5)에서는 **1e-4 반올림이 딱 맞는다** — 빈 종이에서 검출기가 내는
        #   거의 일정한 값(0.05~0.3)이 정확히 평평해져, 파이토치 · ONNX 후보가 165열 중 0열 다름(반올림 없이는 32열).
        p = np.clip(_검출기.경계확률(g, x0, x1)[:len(sm)], CUT_CLIP, 1 - CUT_CLIP)
        p = np.round(p * CUT_ROUND) / CUT_ROUND
        크기 = max(1.0, float(sm[sp[0]:sp[1]].max())) if sp[1] > sp[0] else 1.0
        out.append((1 - CUT_MIX) * sm + CUT_MIX * (1 - p) * 크기)
    return out


SEG_W     = 20.0      # `scan.split_column` 의 비용(자른 자리 잉크 + 1.2 × 칸 높이 고르지 않음)을 이 무게로 섞는다
                      # 고르는 쪽에서 고름(끔 5.08 · w3 5.23 · w6 5.12 · w10 5.03 · w20 4.99 · w40 5.02%) — 0 이면 모델만(나쁨)


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
    ⚠ **자동 라벨을 만들 때만** 켠다(2026-10-01, `실험29`) — 교정서버 · 사람 교정의 자르기는 꺼 둔 그대로여야
      저장된 교정의 상자 좌표가 맞는다(`corpus.same_boxes`).
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
    for centers, sp in tries:
        # 열을 버리는 선택지는 모델이 있을 때만. 모델 없이는 진짜 본문 열을
        # 버려도 알아챌 수가 없다.
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
        best["맞춤"] = geo.get("맞춤")              # 행간 넓은 쪽 — 학습 그림도 같은 상자로 오리게(`실험12`)
        return best
    return dict(사유=why)


# ── 정답지가 없을 때 (4단계) ─────────────────────────────────────────
def read_page(mdl, geo, span=3):
    """
    전사문 없이 쪽을 읽는다(4단계). 정답지가 없으니 열마다 여러 개수로 잘라 보고
    **모델이 가장 자신 있어 한 것**을 고른다. 잘못 자르면 반쪽짜리 그림이 되어
    확신도가 뚝 떨어지기 때문에 이것만으로도 꽤 잘 골라진다.

    (쪽 안에서 자간이 고를 것이라는 조건을 얹어 봤지만 오히려 나빠졌다.
     열마다 글자 수가 실제로 다르기 때문이다. 그래서 확신도만 쓴다.)

    기하에 `가장자리=True` 가 서 있으면(읽는 경로의 한 단 판형) 양 끝 열을
    `가장자리다듬기` 로 가린다.

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


# 읽은 결과에서 뺄 글자 (2026-10-06, 작업자 결정 — 문장부호는 사람이 넣음). 모델은 이 부호를 알아보고(그래야 부호 칸을
# 엉뚱한 한글로 읽지 않음) 결과 글에서만 지운다. 칸 나누기 · 열 고르기 · 띄어쓰기 계산은 부호 칸까지 넣고 끝낸 뒤라 그대로.
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


# ── 띄어쓰기 (2026-09-29) ─────────────────────────────────────────────
# 띄어 쓴 자리는 종이에 **빈틈**으로 찍혀 있다 — 모델 없이, 한 열 안 이웃 글자의 잉크 사이 빈틈 ÷ 그 열 칸 높이
# 중앙값으로 가른다. 문턱은 **쪽마다** 그 쪽 빈틈을 둘로 가르는 자리(오츠). 잘 안 갈리거나 붙은 무리의 빈틈이 넓으면
# (붙여 쓴 책 — 훈아진언) 띄우지 않는다. 떼어 둔 쪽: 여섯 문헌 97~99% · 셩경 개역 93% · 훈아진언 헛띄움 0.
# 열 끝은 못 본다(뒤에 글자가 없음). 재고 고른 기록은 `띄어쓰기실험/README.md`.
SPACE      = True           # `읽기.py`·브라우저판이 띄어쓰기를 넣는가
SPACE_ROW  = 0.03           # 상자 안 한 행의 잉크가 폭의 이 몫(적어도 2px)을 넘으면 잉크 행
SPACE_ETA  = 0.5            # 쪽의 빈틈이 둘로 이만큼(급간 분산 몫) 잘 갈려야 띄운다 — 띄어 쓴 쪽은 대개 0.67~0.93
SPACE_LOW  = 0.2            # 붙은 무리 빈틈의 중앙값이 이보다 작아야(촘촘한 활자 — 띄어 쓴 책 0.10~0.15, 훈아진언 0.35)
SPACE_FRAC = (0.08, 0.6)    # 띄울 자리가 이웃 쌍의 이 몫 안이어야
SPACE_CLIP = (-0.5, 1.5)    # 가를 때 빈틈 값을 이 안으로 자름
# 글자 모양 고침 — 잉크가 칸 안에서 납작하거나 한쪽에 몰린 글자(으 · 오)는 빈틈이 커 보인다. 중성 + 받침 유무마다
# '붙여 쓴 자리의 빈틈이 보통보다 얼마나 큰가'(고르는 쪽 109쪽에서 잼)를 앞 글자 · 뒤 글자로 빼 준다.
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
    반환: 열마다 (로그 확신 평균, 글자들, 확신들, 글자마다 상자) — 읽을 것이 없는 열은 None.

    ★ **글자가 아닌 칸은 글자에서 뺀다** (2026-09-26, `문서/실험_오류분류.md`).
    확신이 `NOTCHAR_CONF` 보다 낮은 칸 중 ① 잉크 폭이 상자의 `NOTCHAR_WIDTH` 가
    안 되는 것 — 본문 열 안에 한 칸을 차지하고 찍힌 **작은 한자 절 번호**
    (十八 · 三十 · 百四五; 전사문에서는 `{{절}}` 이라 빠진다) — 과 ② 한 행이 폭의
    `NOTCHAR_ROW` 를 채우는 것 — **광곽 가로줄** — 을 뺀다. 시편촬요에서 전사보다
    더 읽던 글자의 2/3 가 ①, 15% 가 ② 였다.
    ⚠ 열 점수(첫 값)는 **뺀 칸까지 다 넣어** 낸다 — `가장자리다듬기` 의 판단을
      바꾸지 않으려고.
      떼어 둔 쪽: 평균 8.3 → 7.3% (시편촬요 16.4 → 11.9 · 훈아진언 9.4 → 7.0 ·
      셩경 개역 2.6 → 2.2 · 요한복음 6.2 → 5.8 · 셩경젼셔 신약·신약젼셔 한 글자씩 나빠짐)
      고르는 쪽(따로 15쪽씩, 문턱을 여기서 고름): 11.6 → 9.3%.
      폭 0.5 · 확신 0.5~0.6 이 가장 낫고, 폭 0.4 · 0.6 은 조금 못하다.
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
    # 넷째 값 = 글자를 낸 칸의 상자들(글자와 같은 차례) — 읽기에는 안 쓰고 `실험26` 이 자르기를 잴 때 씀
    # 다섯째 = 잘라 본 칸 수(글자 아닌 칸으로 뺀 것 포함) — `가장자리다듬기` 의 끝 열 보호가 씀
    return [None if o is None else (o[0], o[1], o[2], o[4], o[3]) for o in out]


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
    **두 열에 걸쳐 찍힌 큰 활자 편 제목**을 넓은 칸으로 다시 읽는다 — 읽는 경로에만(2026-09-28).

    시편촬요는 「뎨팔편」 같은 편 제목이 **작은 글씨 두 열 위에 걸쳐** 큰 활자로 찍히고, 그 아래로 두 열이
    작은 글씨로 이어진다(「다빗의 지은 시니…」 · 「가뎃 풍류로…」). 열 찾기는 이 자리를 보통 두 열로 보아 큰
    글자를 반쪽씩 읽어 두 열이 함께 무너졌다(`실험13` 의 '무너짐' — 시편촬요 떼어 둔 쪽 8곳).
    그래서 이웃한 두 열이 **함께** 확신이 낮으면 두 열을 합친 x 범위 위쪽에 큰 글자 k 개(높이 h)를 두고,
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
                if any(x in NOTCHAR_KEEP for x in 제):   # 큰 제목 칸이 `ㅣ` = 광곽 세로줄을 읽은 것(시편촬요 0047)
                    continue
                lg = np.log(np.clip(cf, 1e-6, None))
                if float(lg.mean()) < np.log(HEADING_CONF):   # 본문 글자 둘을 큰 글자 하나로 읽은 것(훈아진언 0042)
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
    `build_plans` 와 같은 모양(allow_empty=False)이되 **자를 자리를 모델이 고른다**(2026-09-28 · 시험 중).

    `build_plans` 는 칸 수 n 마다 `scan.split_column` 으로 **잉크 골짜기와 칸 높이의 고름만 보고** 자른다 — 모델은
    n 을 고를 때만 쓰이고 자를 자리에는 관여하지 않는다(`실험11`: 참 칸 수를 줘도 틀린 열은 45~48% — 자리가 틀림).
    여기서는 같은 골짜기 후보(`scan.cut_points`) 사이의 구간을 칸 높이 0.45~2 배 안에서 **모두 읽어**, n 마다
    로그 확신 합이 가장 큰 자르기를 동적 계획법으로 찾는다. n 을 고르는 것은 지금처럼 확신 평균(뒤 `열마다읽기`).
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
EDGE_MEDIAN_LOW = 0.15  #   확신 0.5 미만 칸이 이 몫 이하인 열은 확신으로 떼지 않음(2026-10-06 시험). None = 끔


def 가장자리다듬기(geo, 열들, δ=EDGE_DROP, 최대=EDGE_MAX, 겹침=EDGE_OVERLAP,
                안δ=EDGE_DROP_IN):
    """
    **읽을 때 쪽 양 끝의 열을 모델 확신도로 가린다.** 남길 열 번호를 차례대로.
    (2026-09-25)

    `scan._가장자리후보` 가 판심을 떼지 않고 양 끝에 후보 열을 붙여 온다.
    여기서 ① 겹친 이웃은 점수 높은 쪽만 남기고 ② 끝에서부터, 가운데 열들
    (양 끝 둘씩 뺀 것)의 중앙값보다 로그 확신이 `δ` 넘게 낮은 열을 뗀다.
    광곽 선·빈 여백·판심은 읽혀도 확신이 바닥이라 저절로 떨어지고,
    그림자 진 본문 열·광곽에 붙은 본문 열은 남는다.

    ★ `page.테두리열버리기` 와 `scan._drop_margin_column` 을 **읽는 경로에서**
    대신한다. 둘 다 그림 모양만 보고 가장자리 열을 버려서 진짜 본문 열을
    자주 버렸다(쪽 머리·꼬리가 열 하나씩 통째로 빠짐 — 작업자가 쓰다 발견).

    실측(재학습 없음 · 떼어 둔 88쪽 · δ 는 따로 뗀 202쪽에서 골라 고정):
        평균 CER 11.4% → 9.7% · 머리/꼬리 통째 빠짐 22쪽 → 15쪽
        구약 권2 28.3 → 22.9 · 권1 7.4 → 5.1 · 시편촬요 22.6 → 20.5 ·
        훈아진언 11.2 → 9.5 · 신약젼셔 5.6 → 4.5 · 요한복음 11.0 → 10.2 ·
        셩경젼셔 신약 2.1 → 1.8 · 셩경 개역(두 단 — 안 씀) 그대로.
    δ 는 0.2~0.5 가 평평하다(0.8 부터 진짜 열을 남겨 두어 나빠지고, 0.1 은
    진짜 열까지 버린다). 자세한 것은 `문서/실험_가장자리열.md`.

    ⚠ **남는 것** — 그림자가 아주 짙은 열(권2 에 많음)은 찾기는 해도 확신이
      −0.8 쯤이라 여전히 떨어진다. 그 열은 읽어 봐야 거의 틀린다.
    ⚠ **자르는 경로(`to_text`)에는 쓰지 마세요.** 거기는 열을 0 칸으로 버리는
      선택지가 있어 이 문제가 없습니다.

    ★ **광곽 세로줄로 안팎을 가른다** (2026-09-26, `문서/실험_오류분류.md`).
    끝 열 쪽으로 이웃 둘 사이에 끊기지 않은 세로줄(`scan.세로줄있나` — 광곽 선이나
    제본 골의 검은 띠)이 있으면 **그 너머는 광곽 밖**이라 버리고(여백 주석·맞은편
    쪽), 그쪽의 남은 끝 열은 `안δ`(0.7)까지 봐준다. 광곽에 붙은 본문 열은 줄이나
    그림자가 오린 그림에 들어가 확신이 −0.55~−0.70 으로 떨어져 `δ` 에 걸렸다
    (구약 권2 떼어 둔 9쪽 중 5쪽이 열 하나씩 잃음). 줄을 못 찾은 쪽은 예전과 같다.
      떼어 둔 쪽: 권2 22.9 → 20.6% · 훈아진언 9.5 → 9.4% · 나머지 그대로
      고르는 쪽(따로 15쪽씩, `안δ` 는 여기서 0.5~0.9 가 평평): 권2 22.5 → 19.2%
    ⚠ 해 보고 버린 것 — 줄 바깥 한 자간까지 더 보기, 줄이 가운데를 지나는 후보
      버리기(훈아진언 0015 · 0097 이 1.5 → 9.5%), 오린 그림에서 줄 지우기·그림자
      밝히기(읽기는 좋아지나 확신이 안 올라감). 남은 것 — 줄이 후보 **한가운데**를
      지나는 쪽(권2 0164 · 1129)은 진짜 열이 상자 밖으로 밀려 있어 여기서는 못 푼다.
    """
    점 = lambda i: -9.0 if 열들[i] is None else 열들[i][0]
    보호 = lambda i, j: False
    if EDGE_MEDIAN:
        # ★ (2026-10-06) 끝 열 보호 — **바로 바깥 이웃(j)이 광곽 세로줄 열**('ㅣ' 막대)이고, 본문만큼 길고, 남은 칸이 거의 다 잘 읽힌
        #   열은 확신으로 떼지 않음. 증남포: 쌍줄 광곽 안쪽 끝 본문 열을 네모 안 글자 · 작은 두 줄 글씨 몇 칸이 평균을 끌어내려 통째로 뗐음.
        #   ⚠ 바깥 이웃 조건 없이는 판심 글씨 열(시편촬요 「시편촬요 뎨일ᄇᆡᆨ칠편 이십이」 · 권2 0475)이 남아 기존 문헌이 나빠짐
        #   (점수를 중앙값으로 바꾸면 시편촬요 4.70 → 5.49% · 낮은 칸 조건만으로는 권2 고르는 0475 12.0 → 16.4%).
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
        # ★ 계선 판(열마다 세로줄)에서는 안쪽 계선에 걸려 **잘 읽은 본문 끝 열을 셋씩** 버렸다(누가복음젼 1893
        #   16.1% — `문서/인계_계선판형_20261001.md`). 계선은 흐려 일부만 줄로 잡혀서 '가운데에도 줄이 많은가' 로는
        #   못 가림(계선 없는 판과 겹침). 그래서 **떼일 열들이 본문 같으면 떼지 않는다** — 절반 이상 확신이 가운데
        #   만큼이고(기준 − δ) 안쪽 열까지 자간 간격으로 고르게 이어지면. 맞은편 쪽 열은 제본 골에서 간격이 끊김.
        def 본문같음(떼일, 안쪽):
            if EDGE_GUIDE is None or len(떼일) < 2:      # 광곽 밖 한 열만 떼는 것은 그대로 — 여백의 큰 장 제목(요한복음 0018)
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

    # ★ 광곽 세로줄을 한 열 통째 `ㅣ` 로 **자신 있게** 읽으면 확신으로는 못 뗀다 — AI Hub 를 섞은
    #   모델에서 요한복음 0047·0065 · 권2 0164·0490 이 그랬다(2026-09-27, CLAUDE.md '두 트랙').
    막대 = lambda i: (EDGE_BAR is not None and 열들[i] is not None and len(열들[i][1]) > 0
                     and sum(자 == "ㅣ" for 자 in 열들[i][1]) > EDGE_BAR * len(열들[i][1]))
    나쁨 = lambda i, d, j: 열들[i] is None or (점(i) < 기준 - d and not 보호(i, j)) or 막대(i)
    for _ in range(최대):
        if len(남) > 4 and 나쁨(남[0], d앞, 남[0] - 1): 남.pop(0)
        else: break
    for _ in range(최대):
        if len(남) > 4 and 나쁨(남[-1], d뒤, 남[-1] + 1): 남.pop()
        else: break
    return 남
