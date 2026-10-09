# -*- coding: utf-8 -*-
"""
스캔 쪽 — 이미지에서 열을 찾고, 열을 몇 칸으로든 자를 수 있게 준비한다.

여기서는 '몇 칸으로 자를지'를 정하지 않는다. 그것은 align.py 가 정한다.
이 파일이 하는 일은 자를 자리의 후보를 만들어 주는 것까지다.
"""
import numpy as np
from PIL import Image, ImageFile
ImageFile.LOAD_TRUNCATED_IMAGES = True

INK = 120           # 이보다 어두우면 잉크로 본다
YX_RATIO = 0.867    # 세로 자간 ÷ 가로 자간 기본값
GLYPH = 0.35        # 글자가 있는 줄은 열 폭의 이만큼 이상이 잉크다
# 읽을 때 구간 끝의 가는 글자 이어 붙이기 (_이어잡기)
SPAN_EXTEND = True
SPAN_LOW = 0.15     # 열 폭의 이만큼 넘는 줄을 잇는다
SPAN_REACH = 1.5    # 구간 밖으로 이 자간까지만
SPAN_GAP = 0.4      # 빈 줄이 이 자간 넘게 이어지면 멈춤
# 읽을 때 광곽 높이를 열마다 따로 (_열광곽) — 기운·휜 광곽 대비
FRAME_LOCAL = True
FRAME_LOCAL_FILL = 0.6    # 열 + 안쪽 고랑 띠의 이만큼이 잉크인 줄을 광곽 가로줄로
FRAME_LOCAL_REACH = 0.35  # 쪽 광곽 줄에서 세로 자간의 이만큼 안에서만 찾음
FRAME_LOCAL_EDGE = 8      # 찬 줄에서 이 px 까지 흐린 줄(열 폭의 GLYPH 넘는 줄)도 광곽 줄로 친다

# ── 열 찾기 ──────────────────────────────────────────────────────────
def _columns_at(ink, W, th, 얇음=0):
    """한 문턱으로 잉크 덩어리를 잡아 (덩어리들, 자간). 쓸 만하지 않으면 None. `find_columns` 의 ①② 부분.
    얇음: 이 폭(px) 안 되는 덩어리를 먼저 버림(점선 계선 — `PITCH_THIN`). 0 = 예전 그대로."""
    runs, s = [], None
    for x, v in enumerate(ink):
        if v > th and s is None:
            s = x
        elif v <= th and s is not None:
            if x - s > 10: runs.append([s, x])
            s = None
    if s is not None and W - s > 10: runs.append([s, W])
    if 얇음:
        runs = [r for r in runs if r[1] - r[0] >= 얇음]
    if len(runs) < 3: return None

    wmed = np.median([b - a for a, b in runs])          # ② 폭이 절반도 안 되면 여백
    runs = [r for r in runs if (r[1] - r[0]) > wmed * 0.55]
    if len(runs) < 3: return None

    cen = [(a + b) / 2 for a, b in runs]
    d = [gg for gg in np.diff(cen) if gg > 40]
    if not d: return None
    return runs, float(np.median(d))


PITCH_OFF, PITCH_ON = 0.15, 0.12     # 표준 자간에서 이 몫 넘게 벗어나면 / 이 몫 안인 다른 문턱으로 바꿈(읽을 때만)
PITCH_MORE = 1.5    # 간격이 표준 근처라도 다른 문턱이 열을 이 배 넘게 더 찾으면(간격은 PITCH_ON 안) 바꿈. 0 = 끔
# (읽을 때만, 2026-10-09) 위 두 문턱으로도 표준에서 PITCH_OFF 넘게 벗어나면 — 점선 계선이 가는 덩어리로 끼어 자간이 절반(쥬역언해 0127 ·
#   관셰음), 문턱이 낮아 이웃 열이 붙어 두 배(쥬역언해 0014) — 가는 덩어리(표준 자간의 PITCH_THIN 안 되는 폭)를 버리고, 더 높은 문턱
#   (최대값의 PITCH_SCAN 배)도 시험해 PITCH_ON 안인 첫 것을 씀. () = 끔. JS 짝 `열찾기` · 설정 `열다시찾기` · `열가는덩이`
PITCH_SCAN = (0.2, 0.3, 0.4, 0.5)
PITCH_THIN = 0.25
INK_EDGE = 0.0      # 스캔 양 끝 이 몫에 걸친 거의 위아래가 다 검은 띠(제본 그림자)를 열 찾기 전에 지움 — 판심떼기=True 일 때만. 0 = 끔
                    # ⚠ 늘 켜지 말 것 — 전사대조만 `find_columns(…, 끝띠=True)` 로 후보 하나로 씀
EDGE_ZONE = 0.03    # `끝띠=True` 로 부를 때의 그 몫
STRIP_FILL = 0.6    # 그 띠: 띠 높이의 이 몫 넘게 잉크인 세로줄(본문 열은 많아야 40% 안팎, 그림자 60~90%)


def _끝띠지우기(ink, 높이, W, 몫):
    """스캔 양 끝 `몫` 안에 걸친 진한 띠(`STRIP_FILL`)와 그 바깥을 0 으로 — 띠에 붙은 본문 열은 남는다."""
    e = int(W * 몫)
    if e <= 0:
        return ink
    진 = ink > 높이 * STRIP_FILL
    out = ink.copy()
    왼 = np.flatnonzero(진[:e])
    if 왼.size:
        b = int(왼[-1])
        while b < W and 진[b]:
            b += 1
        out[:b] = 0
    오 = np.flatnonzero(진[W - e:])
    if 오.size:
        a = W - e + int(오[0])
        while a >= 0 and 진[a]:
            a -= 1
        out[a + 1:] = 0
    return out


def find_columns(g, 판심떼기=True, 표준자간=None, 끝띠=None):
    """
    활자 조판이라 열 간격이 일정하다는 성질을 쓴다.
    ① 잉크로 대략 열을 잡고 ② 여백의 쪽번호를 폭으로 걸러내고
    ③ 쪼개진 열은 합치고 ④ 흐려서 빠진 열은 간격에 맞춰 끼워 넣는다.
    반환: (가로 자간, [(x0, x1), …])  — 오른쪽 열부터 읽는 순서대로

    판심떼기=False 는 읽을 때(한 단 판형) — 대신 양 끝 후보 열(`_가장자리후보`)을 확신도로 가린다.
    표준자간: 문헌 표준 가로 자간(읽을 때만). 끝띠: None 이면 INK_EDGE, True 면 EDGE_ZONE 로 끝 띠 지우기.
    """
    H, W = g.shape
    ink = (g[int(H*0.12):int(H*0.88), :] < INK).sum(axis=0).astype(float)
    # 스캔 끝의 제본 그림자 띠를 지우고 잰다(`_끝띠지우기`) — 띠가 문턱 잣대 · 헛열이 되는 것을 막음. 판심떼기=True 일 때만.
    #   ⚠ 잣대(가장 진한 줄)가 바뀌어 결과가 양쪽으로 튀므로 기본 끔 — 다른 후보 기하로만 씀.
    몫 = INK_EDGE if 끝띠 is None else (EDGE_ZONE if 끝띠 else 0.0)
    if 몫 and 판심떼기:
        ink = _끝띠지우기(ink, int(H*0.88) - int(H*0.12), W, 몫)
    if ink.max() <= 0:
        return None, []
    # 문턱은 최대값(보통 세로 광곽선)의 0.12. 광곽선이 흐리거나 없으면 문턱이 높아 열의 뾰족한 끝만 잡히므로,
    #   잡은 덩어리 폭이 자간의 0.18 이하면(자기 진단) 90 백분위 기준 문턱으로 다시 잡는다.
    #   ⚠ 문턱을 늘 낮추면 멀쩡한 쪽에 없던 열이 생긴다.
    골랐 = None
    잡은 = []
    for 문턱 in (ink.max() * 0.12, float(np.percentile(ink, 90)) * 0.25):
        got = _columns_at(ink, W, 문턱)
        잡은.append(got)
        if got is None:
            continue
        if 골랐 is None:
            골랐 = got                       # 둘 다 통과 못 하면 첫 번째를 쓴다
        r, p = got
        if np.median([b - a for a, b in r]) > p * 0.18:
            골랐 = got; break
    if 골랐 is None:
        return None, []
    # 읽을 때만 — 고른 자간이 문헌 표준에서 PITCH_OFF 넘게 벗어나거나(흐린 쪽에서 제본 골 띠가 최대값을 차지해
    #   진한 몇 열만 잡힌 경우), 다른 문턱이 열을 PITCH_MORE 배 넘게 더 찾으면, 자간이 표준의 PITCH_ON 안인 다른 문턱으로 바꾼다.
    if 표준자간:
        r0, p0 = 골랐
        멀다 = abs(p0 - 표준자간) > 표준자간 * PITCH_OFF
        if 멀다 or PITCH_MORE:
            if len(잡은) < 2:                         # 위 반복이 첫 문턱에서 끝났으면 둘째도 잡아 본다
                잡은.append(_columns_at(ink, W, float(np.percentile(ink, 90)) * 0.25))
            for got in 잡은:
                if got is not None and got is not 골랐 and \
                        abs(got[1] - 표준자간) <= 표준자간 * PITCH_ON and \
                        (멀다 or len(got[0]) >= len(r0) * PITCH_MORE):
                    골랐 = got; break
        if PITCH_SCAN and abs(골랐[1] - 표준자간) > 표준자간 * PITCH_OFF:
            얇 = 표준자간 * PITCH_THIN
            문턱들 = [ink.max() * 0.12, float(np.percentile(ink, 90)) * 0.25] + [ink.max() * f for f in PITCH_SCAN]
            시험 = [(t, 얇) for t in 문턱들[:2]] + [(t, 0) for t in 문턱들[2:]] + [(t, 얇) for t in 문턱들[2:]]
            넓다, n0 = 골랐[1] > 표준자간, _열수(*골랐)
            for t, w in 시험:
                got = _columns_at(ink, W, t, w)
                # 간격이 넓게(열을 묶어) 잡혔던 쪽은 열이 줄어드는 후보를 받지 않음 — 열은 맞는데 간격 셈만 벗어난 쪽(쥬역언해 3책 0024)
                if got is not None and abs(got[1] - 표준자간) <= 표준자간 * PITCH_ON and                         not (넓다 and _열수(*got) < n0):
                    골랐 = got; break
    runs, pitch = 골랐

    merged = [runs[0]]                                   # ③ 쪼개진 열 합치기
    for r in runs[1:]:
        if (r[0]+r[1])/2 - (merged[-1][0]+merged[-1][1])/2 < pitch * 0.6:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    cen = [(a + b) / 2 for a, b in merged]
    if len(cen) > 2: pitch = float(np.median(np.diff(cen)))

    wmed2 = float(np.median([b - a for a, b in merged]))
    boxes = [tuple(merged[0])]                           # ④ 사이에 빠진 열 채우기
    for r in merged[1:]:
        c = (r[0] + r[1]) / 2
        prev_c = (boxes[-1][0] + boxes[-1][1]) / 2
        k = max(1, int(round((c - prev_c) / pitch)))
        for t in range(1, k):
            mid = prev_c + (c - prev_c) * t / k
            boxes.append((int(mid - wmed2/2), int(mid + wmed2/2)))
        boxes.append(tuple(r))
    out = []
    for a, b in boxes:                                   # 지나치게 넓어진 열은 가운데만
        if b - a > pitch * 0.8:
            c = (a + b) / 2; a, b = int(c - wmed2/2), int(c + wmed2/2)
        out.append((max(0, a), min(W, b)))

    # ⑤ 판심 걸러내기 — 판심(쪽 이름·쪽 번호 줄)은 광곽 밖이라 이웃 열과 간격이 확 벌어진다. 양 끝에서 그런 열을 뗀다.
    if 판심떼기:
        out = _drop_margin_column(out)
    return pitch, list(reversed(out))


def _열수(runs, pitch):
    """`find_columns` ③④ 를 거친 뒤의 열 수(합치고 빠진 열 끼운 뒤) — 후보를 견줄 때만."""
    merged = [list(runs[0])]
    for r in runs[1:]:
        if (r[0]+r[1])/2 - (merged[-1][0]+merged[-1][1])/2 < pitch * 0.6:
            merged[-1][1] = r[1]
        else:
            merged.append(list(r))
    cen = [(a + b) / 2 for a, b in merged]
    if len(cen) > 2: pitch = float(np.median(np.diff(cen)))
    return 1 + sum(max(1, int(round((b - a) / pitch))) for a, b in zip(cen, cen[1:]))


def _drop_margin_column(cols, ratio=1.18):
    """양 끝에서, 이웃과의 거리가 자간보다 훨씬 먼 열을 떼어낸다."""
    for _ in range(2):
        if len(cols) < 5:
            break
        cen = [(a + b) / 2 for a, b in cols]
        gaps = [cen[i+1] - cen[i] for i in range(len(cen) - 1)]
        med = float(np.median(gaps))
        if med <= 0:
            break
        if gaps[0] > med * ratio:
            cols = cols[1:]
        elif gaps[-1] > med * ratio:
            cols = cols[:-1]
        else:
            break
    return cols


def _가장자리후보(cols, pitch, W):
    """
    읽을 때 양 끝에 후보 열을 붙인다 — 버릴지는 `align.가장자리다듬기` 가 확신도로 정한다.
    한쪽에 둘: 제자리(둘째 열에서 자간 하나 바깥 — 끌려 밀린 가장자리 열 대신) · 한 칸 더 바깥(못 찾은 열).
    그림 밖 후보와 이미 있는 열과 똑같은 후보는 붙이지 않는다(똑같은 상자는 점수 동점이라 CUDA · WASM 에서 갈림).
    ⚠ 자를 때는 쓰지 말 것.
    """
    w = int(np.median([b - a for a, b in cols]))
    c = lambda ab: (ab[0] + ab[1]) / 2
    def 상자(x):
        a, b = int(x - w / 2), int(x + w / 2)
        return (a, b) if a >= 0 and b <= W and (a, b) not in cols else None
    오른 = [상자(c(cols[0]) + pitch)]
    왼 = [상자(c(cols[-1]) - pitch)]
    if len(cols) > 2:
        오른.append(상자(c(cols[1]) + pitch))     # 제자리
        왼.insert(0, 상자(c(cols[-2]) - pitch))
    out = [x for x in 오른 if x] + list(cols) + [x for x in 왼 if x]
    out.sort(key=lambda ab: -(ab[0] + ab[1]))    # 오른쪽 → 왼쪽 (같으면 붙인 차례)
    return out


def 칸모양(g, b):
    """
    상자 b=(x0,y0,x1,y1) 안 잉크의 (가로 폭 비율, 한 행이 폭을 채운 최대 비율).
    잉크가 없으면 (0, 0). `align.열마다읽기` 가 '글자가 아닌 칸' 을 가릴 때 쓴다.
    """
    c = g[b[1]:b[3], b[0]:b[2]] < INK
    if c.size == 0 or not c.any():
        return 0.0, 0.0
    xs = np.where(c.any(axis=0))[0]
    return (xs[-1] - xs[0] + 1) / c.shape[1], float(c.sum(axis=1).max()) / c.shape[1]


FRAME_SEG, FRAME_FILL, FRAME_AGREE = 300, 0.85, 0.6
FRAME_GUTTER_CUT = 0.6     # 자르는 경로(교정서버 · 자동 라벨 · 데이터셋)의 `FRAME_GUTTER` — 0 = 끔
# (읽을 때만) 옛 규칙이 위 · 아래 둘 다 기본값(6% · 95%)으로 떨어진 쪽만 한쪽씩 다시 찾음 — 광곽 없이 쪽 머리 줄 · 쪽 번호 줄표만 있는 책.
#   고랑 규칙(`FRAME_GUTTER`)도 같이 씀. False = 끔. JS 짝 `광곽` · 설정 `광곽한쪽`
FRAME_ONESIDE = True
FRAME_GUTTER = 0.6        # (읽을 때만) 옛 `_frame` 이 열마다 찾은 줄은 옆 고랑의 이 몫 넘게 찬 것만 광곽으로(0 = 끔 · `page_frame`)


EDGE_MOVE = True 
EDGE_MOVE_GAP = 0.45     # 줄 안쪽 가장자리에서 자간의 이만큼 들어간 자리로
EDGE_MOVE_MIN = 0.6      # 안쪽 이웃과는 적어도 자간의 이만큼 떨어뜨린다
EDGE_MOVE_INK = 0.45     # 옮길 자리의 잉크가 가운데 열들의 이만큼은 돼야 옮긴다


def 세로줄자리(g, xa, xb, T, B, 토막=FRAME_SEG, 덮개=FRAME_FILL, 합의=FRAME_AGREE):
    """
    `세로줄있나` 와 같되 줄이 있으면 (줄 왼끝, 줄 오른끝) — 토막마다 잡힌 x 들의
    가장 왼쪽·가장 오른쪽의 중앙값. 없으면 None.
    """
    xa, xb = int(min(xa, xb)), int(max(xa, xb))
    if xb - xa < 3:
        return None
    칸, 왼, 오 = 0, [], []
    for y in range(T, B - 토막 // 2, 토막):
        blk = g[y:min(B, y + 토막), xa:xb] < INK
        칸 += 1
        xs = np.where(blk.sum(axis=0) >= 덮개 * blk.shape[0])[0]
        if len(xs):
            왼.append(xa + int(xs[0])); 오.append(xa + int(xs[-1]))
    if 칸 == 0 or len(왼) < 칸 * 합의:
        return None
    return float(np.median(왼)), float(np.median(오))


def _줄에서비키기(g, cols, xpitch, T, B, 최대=3):
    """
    읽을 때 쪽 끝 후보 열 상자 안으로 세로줄(광곽·제본 골 띠)이 지나면 그 열을 줄 안쪽으로 옮긴다
    — 덩어리가 띠에 끌려 띠 위에 잡힌 열. 줄 안쪽 가장자리에서 자간의 `EDGE_MOVE_GAP` 만큼 들어간 자리로,
    안쪽 이웃과는 `EDGE_MOVE_MIN` 보다 가까워지지 않게(더 가까우면 `가장자리다듬기` 가 겹친 열로 봄).
    cols 는 오른쪽 → 왼쪽 차례. 한쪽에서 `최대` 열까지만 본다.
    """
    cols = list(cols)
    n = len(cols)
    if n < 6:
        return cols
    w = int(np.median([b - a for a, b in cols]))
    가 = lambda ab: (ab[0] + ab[1]) / 2
    잉크 = lambda a, b: float((g[T:B, max(0, a):max(0, b)] < INK).mean()) if b > a else 0.0
    기준잉크 = float(np.median([잉크(a, b) for a, b in cols[3:-3]])) if n > 6 else 0.0
    for k in list(range(min(최대, n // 2))) + list(range(n - 1, n - 1 - min(최대, n // 2), -1)):
        a, b = cols[k]
        줄 = 세로줄자리(g, a, b, T, B)
        if 줄 is None:
            continue
        오른끝 = k < n // 2                       # 쪽 오른쪽 끝 → 안쪽은 왼쪽(x 작은 쪽)
        안 = cols[k + 1] if 오른끝 else cols[k - 1]
        if 오른끝:
            c = max(줄[0] - xpitch * EDGE_MOVE_GAP, 가(안) + xpitch * EDGE_MOVE_MIN)
            if c >= 가((a, b)):
                continue                             # 안쪽으로 가는 것이 아니면 둔다
        else:
            c = min(줄[1] + xpitch * EDGE_MOVE_GAP, 가(안) - xpitch * EDGE_MOVE_MIN)
            if c <= 가((a, b)):
                continue
        새 = (int(c - w / 2), int(c + w / 2))
        if 잉크(*새) < 기준잉크 * EDGE_MOVE_INK:
            continue                                 # 옮길 자리가 빈 여백이면 둔다
        cols[k] = 새
    return cols


def 세로줄있나(g, xa, xb, T, B, 토막=FRAME_SEG, 덮개=FRAME_FILL, 합의=FRAME_AGREE):
    """
    x 가 [xa, xb) 인 띠에 끊기지 않은 세로줄(광곽 선·제본 골의 검은 띠)이 있는가 — `align.가장자리다듬기` 가 씀.

    [T, B) 를 `토막` px 씩 나눠, 토막마다 어느 x 한 줄이라도 잉크가 `덮개` 이상이면
    그 토막에 줄이 있다고 본다. 토막의 `합의` 이상에 있으면 참.
    토막으로 나누는 까닭 — 쪽이 휘어 줄이 기운다. 글자 획은 글자 사이가 비어 토막을 덮지 못한다.
    """
    xa, xb = int(min(xa, xb)), int(max(xa, xb))
    if xb - xa < 3:
        return False
    칸 = 맞 = 0
    for y in range(T, B - 토막 // 2, 토막):
        blk = g[y:min(B, y + 토막), xa:xb] < INK
        칸 += 1
        맞 += int((blk.sum(axis=0) >= 덮개 * blk.shape[0]).any())
    return 칸 > 0 and 맞 >= 칸 * 합의


# ── 열 안에서 글자가 있는 구간 찾기 ──────────────────────────────────
def _frame(g, x0, x1, 한쪽=False):
    """이 열에서 광곽(테두리) 가로줄의 위·아래. 못 찾으면 None. 한쪽=True 면 (위 또는 None, 아래 또는 None)."""
    H = g.shape[0]
    p = (g[:, x0:x1] < INK).sum(axis=1).astype(float)
    hits = np.where(p >= (x1 - x0) * 0.90)[0]      # 테두리는 열 폭을 거의 다 채운다
    top = [y for y in hits if y < H * 0.25]
    bot = [y for y in hits if y > H * 0.75]
    if 한쪽:
        return (top[0] + 6 if top else None, bot[-1] - 6 if bot else None)
    if not top or not bot:
        return None
    return top[0] + 6, bot[-1] - 6


def _고랑찬몫(g, 순, c, y0, y1):
    """열 c 의 양옆 고랑(순 = x 로 늘어놓은 열들)에서 y0..y1 줄 중 가장 많이 찬 줄의 잉크 몫 — 둘 중 큰 쪽."""
    j, 몫 = 순.index(c), 0.0
    for k in (j - 1, j + 1):
        if 0 <= k < len(순):
            x0, x1 = (순[k][1], c[0]) if k < j else (c[1], 순[k][0])
            if x1 - x0 < 3 or y1 <= max(0, y0):
                continue
            띠 = g[max(0, y0):y1, x0:x1] < INK
            몫 = max(몫, float(띠.mean(axis=1).max()))
    return 몫


def _frame_read(g, cols, fill=0.90, agree=0.30):
    """
    광곽(테두리) 안쪽 위·아래를 '열들의 합의'로 찾는다. 못 찾으면 None. 읽을 때만(`page_frame(읽기=True)`).

    세로쓰기에서 여러 열을 한꺼번에 가로지르는 것은 광곽뿐이다. 행마다 열 폭의 `fill` 넘게 찬 열의
    비율이 `agree` 이상인 줄을 모아, 위 30% · 아래 30% 에서 가장 안쪽 줄의 안쪽을 쓴다
    (`_frame` 의 바깥 줄 · 스캔 가장자리 띠를 피함).
    """
    H = g.shape[0]
    표 = np.zeros(H)
    for x0, x1 in cols:
        표 += ((g[:, x0:x1] < INK).sum(axis=1) >= (x1 - x0) * fill)
    표 /= len(cols)
    줄, ys = [], np.where(표 >= agree)[0].tolist()
    for y in ys:                                   # 이어진 행 = 굵은 선 하나
        if 줄 and y - 줄[-1][1] <= 3: 줄[-1][1] = y
        else: 줄.append([y, y])
    줄 = [r for r in 줄 if r[0] > H * 0.01 and r[1] < H * 0.99]   # 스캔 가장자리
    위 = [r for r in 줄 if r[1] < H * 0.30]
    아래 = [r for r in 줄 if r[0] > H * 0.70]
    if not 위 or not 아래:
        return None
    T, B = 위[-1][1] + 4, 아래[0][0] - 4            # 가장 안쪽 줄의 안쪽
    return (T, B) if B - T > H * 0.4 else None


def page_frame(g, cols, 읽기=False):
    """
    이 쪽의 광곽(테두리) 안쪽 위·아래.

    읽을 때와 자를 때가 일부러 다르다:
      · 읽기 — `_frame_read` 로 광곽 안쪽까지 바짝(짐작 `est` 이 맞아야 칸 수를 고른다).
      · 자르기 — 옛 방식(`_frame` 중앙값)으로 넉넉하게.
    ⚠ 자르는 쪽에 `_frame_read` 를 쓰지 말 것 — 띠가 글자를 물어 상자가 밀린다.
    """
    if 읽기:
        got = _frame_read(g, cols)
        if got:
            return got
    H = g.shape[0]
    frames = [_frame(g, x0, x1) for x0, x1 in cols]
    got = [f for f in frames if f]
    T기본 = B기본 = False
    if len(got) < max(2, len(cols) // 3):
        T, B = int(H * 0.06), int(H * 0.95)
        T기본 = B기본 = True
    else:
        T = int(np.median([f[0] for f in got]))
        B = int(np.median([f[1] for f in got]))
        문턱 = FRAME_GUTTER if 읽기 else FRAME_GUTTER_CUT
        if 문턱:
            # 열마다 찾은 줄 중 옆 고랑(열 사이)까지 찬 것만 광곽으로 — 굵은 글자 획은 열 폭을 채워도 고랑에서 끊김.
            #   위 · 아래 따로, 인정된 것이 둘 미만이면 기본값.
            순 = sorted(cols)
            위 = [f[0] for f, c in zip(frames, cols) if f and _고랑찬몫(g, 순, c, f[0] - 10, f[0] - 2) >= 문턱]
            아래 = [f[1] for f, c in zip(frames, cols) if f and _고랑찬몫(g, 순, c, f[1] + 2, f[1] + 10) >= 문턱]
            T = int(np.median(위)) if len(위) >= 2 else int(H * 0.06)
            B = int(np.median(아래)) if len(아래) >= 2 else int(H * 0.95)
            T기본, B기본 = len(위) < 2, len(아래) < 2
    if 읽기 and FRAME_ONESIDE and FRAME_GUTTER and T기본 and B기본:
        순 = sorted(cols)
        한쪽 = [_frame(g, x0, x1, True) for x0, x1 in cols]
        if T기본:
            위 = [f[0] for f, c in zip(한쪽, cols) if f[0] is not None and _고랑찬몫(g, 순, c, f[0] - 10, f[0] - 2) >= FRAME_GUTTER]
            if len(위) >= 2:
                T = int(np.median(위))
        if B기본:
            아래 = [f[1] for f, c in zip(한쪽, cols) if f[1] is not None and _고랑찬몫(g, 순, c, f[1] + 2, f[1] + 10) >= FRAME_GUTTER]
            if len(아래) >= 2:
                B = int(np.median(아래))
    if 읽기 and FRAME_GUTTER_LINE:
        위, 아래 = _고랑줄(g, cols, FRAME_GUTTER_LINE)
        if 위 is not None and T < 위 < T + H * 0.1:
            T = 위
        if 아래 is not None and B - H * 0.1 < 아래 < B:
            B = 아래
    if B - T < H * 0.4:
        T, B = int(H * 0.06), int(H * 0.95)
    return T, B


# (읽을 때만) 쌍줄 광곽의 가는 안쪽 줄 — `_frame`(90%)에 안 걸리는 줄. 열 폭의 이 몫 + 옆 고랑의 이 몫을 함께 채운 줄이
#   열의 30% 넘게 같은 높이에 있으면 광곽 줄로 봄. 옛 경계보다 조금 안쪽(쪽 높이 10% 안)일 때만 옮김. 0 = 끔
FRAME_GUTTER_LINE = 0.6


def _고랑줄(g, cols, fill, agree=0.3):
    """열 폭 · 옆 고랑을 함께 채운 가로줄이 여러 열에 걸친 높이 — (위 안쪽, 아래 안쪽), 없으면 None."""
    H = g.shape[0]
    순 = sorted(cols)
    if len(순) < 3:
        return None, None
    ink = g < INK
    표 = np.zeros(H)
    for k, (x0, x1) in enumerate(순):
        if x1 - x0 < 3:
            continue
        열찬 = ink[:, x0:x1].mean(axis=1) >= fill
        고랑찬 = np.zeros(H, dtype=bool)
        for j in (k - 1, k + 1):
            if 0 <= j < len(순):
                a, b = (순[j][1], x0) if j < k else (x1, 순[j][0])
                if b - a >= 3:
                    고랑찬 |= ink[:, a:b].mean(axis=1) >= fill
        표 += 열찬 & 고랑찬
    표 /= len(순)
    줄, ys = [], np.where(표 >= agree)[0].tolist()
    for y in ys:
        if 줄 and y - 줄[-1][1] <= 3: 줄[-1][1] = y
        else: 줄.append([y, y])
    줄 = [r for r in 줄 if r[0] > H * 0.01 and r[1] < H * 0.99]
    위 = [r for r in 줄 if r[1] < H * 0.30]
    아래 = [r for r in 줄 if r[0] > H * 0.70]
    return (위[-1][1] + 4 if 위 else None), (아래[0][0] - 4 if 아래 else None)


def _열광곽(g, cols, T, B, xpitch, pitch):
    """
    열마다 광곽 안쪽 위·아래 — 읽을 때만, `_frame_read` 가 쪽 광곽을 찾았을 때만.
    반환: (Ts, Bs) 열마다. 쪽 값보다 안쪽으로만 옮긴다(기운 광곽 줄이 끝 열 띠 안에 들어온 것).

    쪽 광곽 줄(T−4 · B+4) 근처 `FRAME_LOCAL_REACH` 자간 안에서, 열마다 열 + 쪽 가운데 쪽 고랑을
    합친 띠가 `FRAME_LOCAL_FILL` 넘게 찬 줄을 찾는다 — 고랑까지 가로지르는 것은 광곽뿐.
    못 찾은 열은 x 로 양옆(찾은 열)을 곧게 잇는다(`잇기`).
    """
    W = g.shape[1]
    R = max(6, int(FRAME_LOCAL_REACH * pitch))
    쪽가운데 = np.mean([(a + b) / 2 for a, b in cols])
    위, 아래, xs = [], [], []
    for x0, x1 in cols:
        고랑 = max(0, int(xpitch - (x1 - x0)))
        if (x0 + x1) / 2 < 쪽가운데: a, b = x0, min(W, x1 + 고랑)
        else:                        a, b = max(0, x0 - 고랑), x1
        찬 = (g[:, a:b] < INK).sum(axis=1) >= (b - a) * FRAME_LOCAL_FILL
        획 = (g[:, x0:x1] < INK).sum(axis=1) > (x1 - x0) * GLYPH      # `spans_between` 이 글자 줄로 세는 줄
        y0 = max(0, T - 4 - R)
        윗줄 = np.where(찬[y0:T - 4 + R])[0]
        if len(윗줄):
            y = y0 + int(윗줄[-1])                                 # 줄 한가운데(찬 줄) → 흐린 가장자리까지
            e = y
            while e + 1 < len(획) and e + 1 - y <= FRAME_LOCAL_EDGE and 획[e + 1]: e += 1
            위.append(max(y + 4, e + 2))
        else:
            위.append(None)
        y0 = max(0, B + 4 - R)
        아랫줄 = np.where(찬[y0:min(len(찬), B + 4 + R)])[0]
        if len(아랫줄):
            y = y0 + int(아랫줄[0])
            e = y
            while e - 1 >= 0 and y - (e - 1) <= FRAME_LOCAL_EDGE and 획[e - 1]: e -= 1
            아래.append(min(y - 4, e - 2))
        else:
            아래.append(None)
        xs.append((x0 + x1) / 2)

    def 잇기(v, 쪽값, 안쪽):
        """못 찾은 열은 x 로 가장 가까운 양옆(찾은 열)을 곧게 잇는다 — 한쪽뿐이면 그 값. `읽기.js` 짝이라 손으로."""
        있 = [i for i, t in enumerate(v) if t is not None]
        if not 있:
            return [쪽값] * len(v)
        out = []
        for i, t in enumerate(v):
            if t is None:
                왼 = [j for j in 있 if xs[j] <= xs[i]]
                오 = [j for j in 있 if xs[j] >= xs[i]]
                l = max(왼, key=lambda j: xs[j]) if 왼 else None
                r = min(오, key=lambda j: xs[j]) if 오 else None
                if l is None or r is None or xs[r] == xs[l]:
                    t = v[l if r is None else r]
                else:
                    t = int(np.floor(v[l] + (v[r] - v[l]) * (xs[i] - xs[l]) / (xs[r] - xs[l])))
            out.append(안쪽(쪽값, t))
        return out
    return 잇기(위, T, max), 잇기(아래, B, min)


def ink_profile(g, cols):
    """열마다 '그 줄에 잉크가 몇 픽셀인가'. 뒤 계산이 모두 이것을 돌려쓴다."""
    return [(g[:, x0:x1] < INK).sum(axis=1).astype(float) for x0, x1 in cols]


def _이어잡기(p, a, b, w, T, B, pitch):
    """
    구간 끝의 가는 글자를 이어 붙인다 — 읽을 때만 (`SPAN_EXTEND`).
    `GLYPH` 를 못 넘는 첫·끝 글자(`이` 처럼 획이 열 밖으로 나가는 것)가 구간에서 빠지지 않게, 구간 밖으로
    `SPAN_REACH` 자간 안에서 `SPAN_LOW` 를 넘는 줄을, 빈 줄이 `SPAN_GAP` 자간 넘게 끊기기 전까지 잇는다.
    """
    reach = SPAN_REACH
    lim, 끝 = max(T, int(a - reach * pitch)), a
    for y in range(a - 1, lim - 1, -1):
        if p[y] > w * SPAN_LOW: 끝 = y
        elif 끝 - y > SPAN_GAP * pitch: break
    a = 끝
    lim, 끝 = min(B, int(b + reach * pitch)), b
    for y in range(b, lim):
        if p[y] > w * SPAN_LOW: 끝 = y + 1
        elif y - 끝 > SPAN_GAP * pitch: break
    return a, 끝


def spans_between(prof, cols, T, B, pitch, 이어=False):
    """
    T~B 안에서 열마다 글자가 실제로 시작하고 끝나는 y 범위.

    뒷면 비침 · 계선 때문에 열 폭의 `GLYPH` 이상이 잉크인 줄만 글자 줄로 본다
    (그래야 중간에서 시작하거나 일찍 끝나는 열을 잡는다).
    `이어=True`(읽을 때) 면 구간 끝의 가는 글자를 `_이어잡기` 로 붙인다.
    T · B 는 열마다의 목록이어도 된다(`_열광곽` — 읽을 때).
    """
    Ts = list(T) if isinstance(T, (list, tuple)) else [T] * len(cols)
    Bs = list(B) if isinstance(B, (list, tuple)) else [B] * len(cols)
    spans = []
    for i, (x0, x1) in enumerate(cols):
        p, t, b = prof[i], Ts[i], Bs[i]
        hit = np.where(p[t:b] > (x1 - x0) * GLYPH)[0]
        s = None if len(hit) == 0 else (t + int(hit[0]), t + int(hit[-1]) + 1)
        if s and 이어 and SPAN_EXTEND:
            s = _이어잡기(p, s[0], s[1], x1 - x0, t, b, pitch)
        spans.append(s)
    real = [s for s in spans if s]
    if not real:
        return None
    Emax = max(e for _, e in real)
    out = []
    for i, s in enumerate(spans):
        if s is None:
            out.append(None); continue
        a, b = s
        if a - Ts[i] < pitch * 0.5:   a = Ts[i]        # 첫 글자가 흐릿해도 위에서 시작한 것으로
        if Emax - b < pitch * 0.6:    b = min(Emax, Bs[i])   # 끝도 마찬가지 (열 광곽 너머로는 안 감)
        out.append((a, b))
    return out


def text_spans(g, cols, pitch):
    prof = ink_profile(g, cols)
    T, B = page_frame(g, cols)
    return spans_between(prof, cols, T, B, pitch), prof


# ── 두 단짜리 판형 ───────────────────────────────────────────────────
def tier_peak(g, cols, lo=0.30, hi=0.70):
    """
    쪽 가운데 띠에서 **열들이 가장 많이 합의하는 가로줄**. (합의도, y, 위, 아래).
    합의도는 '그 줄이 열 폭을 거의 다 채운 열의 비율'이다.

    ⚠ 열 하나만 보면 획이나 계선도 '열 폭을 채운 가로줄'로 잡히므로 열들의 합의로 본다.
    """
    H = g.shape[0]
    if len(cols) < 3:
        return None
    hit = np.zeros(H)
    for x0, x1 in cols:
        p = (g[:, x0:x1] < INK).sum(axis=1)
        hit += (p >= (x1 - x0) * 0.90)
    frac = hit / len(cols)
    y0, y1 = int(H * lo), int(H * hi)
    band = frac[y0:y1]
    if len(band) == 0:
        return None
    k = int(np.argmax(band)) + y0
    peak = float(frac[k])
    th = max(0.10, peak * 0.6)                  # 줄에 두께가 있으니 위아래로 넓힌다
    a = b = k
    while a > y0 and frac[a-1] >= th:
        a -= 1
    while b + 1 < y1 and frac[b+1] >= th:
        b += 1
    return peak, k / H, a, b + 1


def tier_divider(g, cols, agree=0.70):
    """단을 가르는 가운데 가로줄의 (위, 아래). 합의도가 모자라면 None."""
    r = tier_peak(g, cols)
    if r is None or r[0] < agree:
        return None
    return r[2], r[3]


def tier_measure(path):
    """
    이 쪽에서 (가운데 가로줄의 합의도, 쪽 높이에서의 자리). 못 재면 None.
    문헌이 두 단인지 정할 때 몇 쪽에 물어보는 용도다 — `page.doc_tiers` 참고.
    """
    g = np.array(Image.open(path).convert("L"))
    xpitch, cols = find_columns(g)
    if not cols:
        return None
    r = tier_peak(g, cols)
    return None if r is None else (r[0], r[1])


# ── 가름줄 판형 (신문처럼 가로줄로 단을 여럿 나눈 것) ──────────────────
# `단` 자리에 가름줄 높이 목록(쪽 높이에 대한 비율)이 오면 이 갈래를 탄다.
# 잣대는 열 사이 고랑 — 글자 획은 고랑에서 끊기지만 가름줄은 고랑까지 가로지른다.
# ⚠ 쪽 하나로는 못 가른다 — 문헌 단위로 높이를 먼저 정하고(`가름줄판정`) 쪽에서는 그 근처만 찾는다.
def 고랑곡선(g, cols, 띠=4, 채움=0.8):
    """행마다, 열 사이 고랑 중 **가로로 잉크가 꽉 찬** 것의 비율. 위아래 `띠` 줄을 함께 본다(기울기)."""
    ink = (g < INK).astype(np.int32)
    H, W = ink.shape
    cs = np.vstack([np.zeros((1, W), np.int32), np.cumsum(ink, 0)])
    y = np.arange(H)
    any_ = (cs[np.minimum(y + 띠 + 1, H)] - cs[np.maximum(y - 띠, 0)]) > 0
    cx = np.hstack([np.zeros((H, 1), np.int32), np.cumsum(any_, 1)])
    c = sorted(cols)
    고랑 = [(c[i][1], c[i + 1][0]) for i in range(len(c) - 1) if c[i + 1][0] - c[i][1] >= 4]
    G = np.zeros(H)
    for a, b in 고랑:
        G += (cx[:, b] - cx[:, a]) >= (b - a) * 채움
    return G / max(1, len(고랑))


def _줄덩이(G, 문턱=0.15):
    """곡선이 문턱을 넘는 이어진 행들 → [(시작, 끝, 최대값), …]"""
    out, y, H = [], 0, len(G)
    while y < H:
        if G[y] >= 문턱:
            e = y
            while e + 1 < H and G[e + 1] >= 문턱:
                e += 1
            out.append((y, e + 1, float(G[y:e + 1].max())))
            y = e + 1
        else:
            y += 1
    return out


def 가름줄측정(path):
    """(쪽 안쪽의 가장 센 봉우리, [(가운데 높이 비율, 세기), …]). 못 재면 None."""
    g = np.array(Image.open(path).convert("L"))
    H = g.shape[0]
    xp, cols = find_columns(g)
    if not cols:
        return None
    T, B = page_frame(g, cols, True)
    a, b = int(T + 3 * xp), int(B - 3 * xp)
    if b <= a:
        return None
    # ⚠ 판정은 채움 0.6(가늘고 끊긴 가름줄), 쪽을 자를 때는 0.8(`_가름판_geometry` — 느슨하면 글자 잡음이 줄이 됨).
    G = 고랑곡선(g, cols, 채움=0.6)
    덩 = [((s + e) / 2 / H, m) for s, e, m in _줄덩이(G) if a <= (s + e) / 2 < b]
    return float(G[a:b].max()), 덩


def 가름줄판정(paths, 문턱=0.5, 센줄=0.4, 모음=0.03):
    """
    문헌이 가름줄 판형이면 **가름줄 높이 비율 목록**, 아니면 None.
    쪽들의 봉우리 중앙값이 `문턱` 이상이어야 하고, 가름줄은 쪽의 **절반 넘게**
    같은 높이(±`모음`)에 `센줄` 이상으로 나와야 한다. 쪽 위아래 20% 는 안 본다(제호·날짜 상자 줄).
    """
    return 가름줄정하기([가름줄측정(p) for p in paths], 문턱, 센줄, 모음)


def 최소쪽(n):
    """판정에 쓸 쪽이 몇 개는 있어야 하나. 보통 4, **쪽이 적은 파일**(신문 한 호 3~4쪽)은 있는 만큼 — 단 2 이상."""
    return max(2, min(4, n))


def 가름줄정하기(잰것들, 문턱=0.5, 센줄=0.4, 모음=0.03):
    """`가름줄판정` 의 뒤 절반 — 쪽마다 `가름줄측정` 한 것(못 잰 쪽은 None)을 받는다. 읽기.js 짝."""
    got = [v for v in 잰것들 if v]
    if len(got) < 최소쪽(len(잰것들)) or float(np.median([v[0] for v in got])) < 문턱:
        return None
    점 = sorted((p, k) for k, (_, 덩) in enumerate(got) for p, m in 덩
               if m >= 센줄 and 0.2 <= p <= 0.8)
    줄 = []                                  # 이웃 점과 `모음` 안으로 붙은 것끼리 한 무리
    for p, k in 점:
        if 줄 and p - 줄[-1][-1][0] <= 모음:
            줄[-1].append((p, k))
        else:
            줄.append([(p, k)])
    out = [round(float(np.median([p for p, _ in z])), 4) for z in 줄
           if len({k for _, k in z}) * 2 > len(got)]
    return out or None


def _가름판_geometry(path, g, ratio, 가름):
    """가름줄 판형의 쪽 기하 — 단을 가르고 **단마다 열을 따로** 찾는다(단끼리 열 자리가 어긋난다)."""
    H, W = g.shape
    xp0, cols0 = find_columns(g)
    if not cols0:
        return None
    덩 = _줄덩이(고랑곡선(g, cols0))
    자름 = []
    for p in 가름:                                     # 문헌이 정한 높이 근처의 가장 센 줄
        y = p * H
        곁 = [d for d in 덩 if abs((d[0] + d[1]) / 2 - y) <= 2 * xp0]
        if 곁:
            d = max(곁, key=lambda d: d[2]); 자름.append((d[0], d[1]))
        else:
            자름.append((int(y) - 4, int(y) + 4))
    자름 += [(s, e) for s, e, m in 덩 if m >= 0.9]      # 광곽·제호 상자처럼 꽉 찬 줄
    자름.sort()
    구간, 끝 = [], 0
    for s, e in 자름:
        if s > 끝:
            구간.append((끝, s))
        끝 = max(끝, e)
    구간.append((끝, H))
    키 = max(b - a for a, b in 구간)
    구간 = [(a, b) for a, b in 구간 if b - a >= max(6 * xp0, 0.4 * 키)]   # 제호·날짜 줄 버림

    단들 = []
    for a, b in 구간:
        xp, cols = find_columns(g[a:b])
        if cols and xp:
            단들.append((a, b, xp, cols))
    if not 단들:
        return None
    xpitch = float(np.median([d[2] for d in 단들]))
    pitch = xpitch * ratio
    half = xpitch * 0.45
    cols_all, spans_all, sm_all = [], [], []
    for a, b, _, cols in 단들:
        prof = ink_profile(g, cols)
        sp = spans_between(prof, cols, a + 2, b - 2, pitch)
        if sp is None:
            continue
        cols_all += cols; spans_all += sp
        sm_all += [smooth(p, max(2.0, pitch / 9)) for p in prof]
    if not cols_all:
        return None
    est = [0 if s is None else max(1, int(round((s[1] - s[0]) / pitch))) for s in spans_all]
    crop_cols = [(max(0, int((a + b) / 2 - half)), min(W, int((a + b) / 2 + half)))
                 for a, b in cols_all]
    return dict(cols=cols_all, crop_cols=crop_cols, spans=spans_all, sm=sm_all, pitch=pitch,
                xpitch=xpitch, est=est, 단=len(단들), 가장자리=False, 본열수=len(cols0),
                image=Image.open(path).convert("L"))


# ── 자를 자리 후보 ───────────────────────────────────────────────────
# ── 분주(열 안의 두 줄) 후보 (`분주후보`, 2026-10-09) ────────────────────────
# 열 가운데 좁은 띠는 비고 좌우 양쪽에 글자 반쪽 넘는 잉크가 있는 가로 띠가 이어진 구간. 판정은 느슨하게 — 받을지는
# `align.분주읽기` 가 모델 확신으로 정함(그림 모양만으로는 쪽 끝 열 · 판심 · '이 · 니' 같은 글자에 헛잡음).
BUNJU_BAND = 0.25    # 가로 띠 높이(세로 자간의 몫)
BUNJU_WIDE = 1.25    # 열 가운데에서 좌우로 글자 폭의 이 배까지 봄(분주 글자는 열 밖으로 삐져나옴 — 증남포)
BUNJU_MID = 0.3      # 두 줄 사이 빈틈을 열 가운데에서 글자 폭의 ± 이 몫 안에서 찾음(정가운데가 아닐 수 있음 — 증남포 0018)
BUNJU_GAP = 3        # 그 빈틈은 적어도 이 px
BUNJU_SIDE = 0.3     # 좌우 잉크가 각각 글자 폭의 이 몫은 넘어야
BUNJU_MIN = 0.6      # 구간이 세로 자간의 이 배는 돼야


def _가름자리(occ, m0, m1, cx):
    """occ 의 [m0, m1) 안 빈 자리 중 cx 에 가장 가까운 빈틈(BUNJU_GAP 넘는)의 가운데 — 없으면 None."""
    best, x = None, m0
    while x < m1:
        if occ[x]:
            x += 1; continue
        e = x
        while e < m1 and not occ[e]:
            e += 1
        if e - x >= BUNJU_GAP:
            c = (x + e) / 2
            if best is None or abs(c - cx) < abs(best - cx):
                best = c
        x = e
    return best


def 분주후보(g, cols, i, sp, pitch):
    """열 i 의 글자 구간 sp 에서 분주처럼 보이는 [(y0, y1, 왼끝, 가름 x, 오른끝)] — `cols` 는 열 잉크 덩어리(글자 폭)."""
    c0, c1 = cols[i]
    w = c1 - c0
    if w < 8 or not sp:
        return []
    cx = (c0 + c1) / 2
    lo, hi = cx - w * BUNJU_WIDE, cx + w * BUNJU_WIDE
    for j in (i - 1, i + 1):                         # 이웃 열과의 가운데를 넘지 않게
        if 0 <= j < len(cols):
            n = (cols[j][0] + cols[j][1]) / 2
            if abs(n - cx) < 1:
                continue
            if n > cx: hi = min(hi, (cx + n) / 2)
            else: lo = max(lo, (cx + n) / 2)
    lo, hi = int(max(0, lo)), int(min(g.shape[1], hi))
    y0, y1 = sp
    blk = g[y0:y1, lo:hi] < INK
    c = cx - lo
    m0, m1 = int(max(1, c - w * BUNJU_MID)), int(min(blk.shape[1] - 1, c + w * BUNJU_MID))
    if m1 - m0 < BUNJU_GAP:
        return []
    h = max(2, int(pitch * BUNJU_BAND))
    상태, 가름 = [], []
    for y in range(0, blk.shape[0], h):
        occ = blk[y:y + h].any(axis=0)
        if not occ.any():
            상태.append(0); 가름.append(None); continue
        x = _가름자리(occ, m0, m1, c)
        if x is None:
            상태.append(-1); 가름.append(None); continue
        왼 = np.flatnonzero(occ[:int(x)]); 오 = np.flatnonzero(occ[int(x) + 1:])
        wl = (x - 왼[0]) if len(왼) else 0
        wr = (오[-1] + 1) if len(오) else 0
        ok = wl >= w * BUNJU_SIDE and wr >= w * BUNJU_SIDE
        # 가운데가 비고 한쪽 줄에만 글자가 있는 띠(두 줄 길이가 다름 — 증남포 0018 「증남포 / 목포」)는 끊지 않음
        상태.append(1 if ok else 0); 가름.append(x if ok else None)
    out, k = [], 0
    while k < len(상태):
        if 상태[k] != 1:
            k += 1; continue
        e, n1 = k, 0
        while e < len(상태) and 상태[e] != -1:
            n1 += 상태[e] == 1; e += 1
        while e > k and 상태[e - 1] == 0:
            e -= 1
        if n1 >= 2 and (e - k) * h >= pitch * BUNJU_MIN:
            xs = [v for v in 가름[k:e] if v is not None]
            out.append((y0 + k * h, y0 + min(e * h, blk.shape[0]), lo, int(round(lo + float(np.median(xs)))), hi))
        k = max(e, k + 1)
    return out


def smooth(a, s):
    k = np.exp(-0.5 * (np.arange(-3*s, 3*s+1) / s) ** 2); k /= k.sum()
    return np.convolve(a, k, 'same')


def cut_points(sp, y0, y1, pitch):
    """글자 사이 골짜기(잉크가 적은 자리)를 자를 자리 후보로 삼는다."""
    c = [y for y in range(y0 + 1, min(y1 - 1, len(sp) - 1))
         if sp[y] <= sp[y-1] and sp[y] < sp[y+1]]
    if len(c) < 4:
        c = list(range(y0 + int(pitch*0.5), y1 - int(pitch*0.5), max(4, int(pitch/6))))
    return c


def split_column(sp, y0, y1, n, cands, lam=1.2):
    """
    한 열을 정확히 n 칸으로 가른다.
    비용 = 자른 자리의 잉크량 + lam × (칸 높이가 고르지 못한 정도)
    반환: (자른 y 좌표 n+1 개, 비용). 못 하면 (None, 큰 값)
    """
    INF = 1e9
    if n <= 0: return None, INF
    span = y1 - y0
    pitch = span / n
    if n == 1: return [y0, y1], 0.0
    pts = [y0] + [c for c in cands if y0 < c < y1] + [y1]
    m = len(pts)
    if m < n + 1: return None, INF
    mx = max(1.0, sp[y0:min(y1, len(sp))].max())
    lo, hi = pitch * 0.45, pitch * 2.0
    dp = np.full((n + 1, m), INF)
    prev = np.full((n + 1, m), -1, dtype=int)
    dp[0][0] = 0.0
    for c in range(1, n + 1):
        for j in range(1, m):
            yj = pts[j]
            best, bi = INF, -1
            for i in range(j - 1, -1, -1):
                h = yj - pts[i]
                if h < lo: continue
                if h > hi: break
                if dp[c-1][i] >= INF: continue
                cost = dp[c-1][i] + ((h - pitch) / pitch) ** 2 * lam
                if c < n: cost += sp[min(yj, len(sp) - 1)] / mx
                if cost < best: best, bi = cost, i
            dp[c][j], prev[c][j] = best, bi
    if dp[n][m-1] >= INF: return None, INF
    out, c, j = [], n, m - 1
    while c > 0:
        out.append(pts[j]); j = prev[c][j]; c -= 1
    out.append(pts[0])
    return sorted(out), float(dp[n][m-1])


# ── 그림만으로 세로 자간 재기 ────────────────────────────────────────
def _fold_contrast(prof, y0, y1, period):
    """
    글자가 period 간격으로 늘어서 있다면, 그 간격으로 접었을 때
    '글자 자리'와 '글자 사이'가 또렷하게 갈린다. 그 또렷함을 점수로 준다.
    """
    P = int(round(period))
    if P < 8:
        return -1.0
    seg = np.asarray(prof[y0:y1], dtype=float)
    k = len(seg) // P
    if k < 4:
        return -1.0
    x = seg[:k * P]
    idx = np.arange(k * P) % P
    m = np.bincount(idx, weights=x, minlength=P)
    c = np.bincount(idx, minlength=P)
    curve = m / np.maximum(c, 1)
    return float(curve.std() / max(1e-6, curve.mean()))


# 참 간격의 두 배로 접어도 또렷해서 두 배를 집을 수 있다 — 열마다 고른 t 의 절반으로 접은 점수가
# 최고 점수의 이 몫 이상이면 t/2 (절반이 lo 안일 때만). None = 끔
RATIO_HALF = 0.9
# 열에서 고른 주기가 글자 폭(`글자폭몫` × 상자 폭)의 RATIO_FIT_OVER 배를 넘으면 그 열만 글자 폭의 RATIO_FIT 배 안에서 다시 찾음
#   — 행간이 넓은 책에서 두세 글자 주기를 고르는 것. 그때는 `RATIO_HALF` 를 안 봄. None = 끔
RATIO_FIT = (1.0, 1.7)
RATIO_FIT_OVER = 2.0


def page_ratio(path, lo=0.55, hi=1.45, steps=120, 단=1):
    """
    이 쪽의 '세로 자간 ÷ 가로 자간'을 **그림만 보고** 잰다. 전사문이 필요 없다.
    열마다 여러 간격으로 접어 보고 가장 또렷한 것을 고른 뒤, 열들의 중앙값을 쓴다.

    단=2 일 때는 단을 나눈 뒤에 잰다(이어 붙인 채면 가운데 줄 · 여백이 무늬를 흩뜨림).
    """
    g = np.array(Image.open(path).convert("L"))
    xpitch, cols = find_columns(g)
    if not cols or not xpitch:
        return None
    geo = page_geometry(path, YX_RATIO, 단)
    if geo is None:
        return None
    spans, prof, cols = geo["spans"], None, geo["cols"]
    prof = [np.asarray(p) for p in ink_profile(g, cols)]
    q = geo.get("글자폭몫")
    gw = 0.9 * q * geo["xpitch"] / xpitch if RATIO_FIT and q is not None else None   # 글자 폭 ÷ 열 간격
    out = []
    for i, sp in enumerate(spans):
        if not sp:
            continue
        y0, y1 = sp
        if y1 - y0 < xpitch * 6:          # 너무 짧은 열은 주기를 잴 수 없다
            continue
        p = smooth(prof[i], max(2.0, xpitch / 12))
        best = (-1.0, None)
        for t in np.linspace(lo, hi, steps):
            sc = _fold_contrast(p, y0, y1, xpitch * t)
            if sc > best[0]:
                best = (sc, t)
        if gw and best[1] and best[1] > gw * RATIO_FIT_OVER:
            best = (-1.0, None)               # 글자 폭에 견줘 있을 수 없는 주기 — 글자 폭 범위 안에서 다시
            for t in np.linspace(gw * RATIO_FIT[0], gw * RATIO_FIT[1], steps):
                sc = _fold_contrast(p, y0, y1, xpitch * t)
                if sc > best[0]:
                    best = (sc, t)
        elif best[1] and RATIO_HALF and best[1] / 2 >= lo \
                and _fold_contrast(p, y0, y1, xpitch * best[1] / 2) >= RATIO_HALF * best[0]:
            best = (best[0], best[1] / 2)     # 두 배 착각 — 절반 간격도 거의 그만큼 또렷함
        if best[1]:
            out.append(best[1])
    return float(np.median(out)) if len(out) >= 3 else None


def estimate_ratio(paths, 단=1):
    """여러 쪽에서 재서 중앙값. 못 재면 None."""
    vals = []
    for p in paths:
        try:
            v = page_ratio(p, 단=단)
        except Exception:
            v = None
        if v:
            vals.append(v)
    return float(np.median(vals)) if vals else None


# ── 쪽 하나의 기하 정보 ──────────────────────────────────────────────
CROP_FIT = 0.62      # 글자 폭 ÷ 상자 폭(열마다 세로로 모은 잉크가 최대의 10% 넘는 범위, 열 중앙값)이 이보다 작고 — 0 = 끔
CROP_FIT_RATIO = 0.70  #   자간비도 이보다 작은 쪽만 상자를 맞춤
CROP_FIT_TO = 0.78   #   그때 글자가 상자 폭의 이만큼이 되게 좁힘 · 칸 높이도 같은 크기로(`align._맞춤상자`)


def _글자폭몫(g, crop_cols, spans):
    """열마다 상자 폭에서 글자가 차지하는 몫의 중앙값 — 못 재면 None."""
    v = []
    for (x0, x1), sp in zip(crop_cols, spans):
        if not sp or x1 - x0 < 4 or sp[1] - sp[0] < 4:
            continue
        col = (g[sp[0]:sp[1], x0:x1] < INK).sum(axis=0).astype(float)
        if col.max() <= 0:
            continue
        on = np.where(col >= 0.1 * col.max())[0]
        v.append((on[-1] - on[0] + 1) / (x1 - x0))
    return float(np.median(v)) if len(v) >= 3 else None


def page_geometry(path, ratio=YX_RATIO, 단=1, 읽기=False, 가장자리=True, 표준자간=None, 이어=None, 끝띠=None, 판심=None):
    """
    쪽 이미지 → 열·글자 구간·세로 자간. 못 읽으면 None.
    무거운 계산은 여기 한 번뿐이고, 뒤 단계는 이 결과를 돌려쓴다.

    ratio 는 그 문헌의 '세로 자간 ÷ 가로 자간'.

    단=2 는 위아래 두 단 판형 — 열 하나를 위·아래로 쪼개 위 단을 오른쪽부터 다 읽은 뒤 아래 단 차례로
    늘어놓는다(뒤 단계에는 열이 두 배인 쪽으로 보임). 단이 목록이면 가름줄 판형(`_가름판_geometry`).

    읽기=True 는 전사문 없이 읽을 때 — 광곽 경계를 다르게 잡는다(`page_frame`). 자를 때 켜지 말 것.
    한 단 판형이면 판심을 떼지 않고 양 끝에 후보 열도 붙인다(`_가장자리후보`, `가장자리=True` 가 섬).
    `본열수` 는 판심만 뗀 원래 열 수 — `page.쪽건강` 이 판짜임과 견줄 때 쓴다.
    가장자리=False 는 후보를 안 붙인다(`to_text` 로 잴 때 — 겹친 후보를 가릴 장치가 없음).
    이어=None 이면 `읽기` 를 따른다. 이어=True 는 자를 때 가는 글자 이어 붙이기(`_이어잡기`)만 켠다(자동 라벨용).
    판심=False 는 판심 걸러내기만 끈다(가장자리 후보 없이).
    """
    이어 = bool(읽기) if 이어 is None else bool(이어)
    g = np.array(Image.open(path).convert("L"))
    if isinstance(단, (list, tuple)):             # 가름줄 판형 — 위 `_가름판_geometry`
        return _가름판_geometry(path, g, ratio, 단)
    후보 = bool(읽기) and 단 == 1 and 가장자리
    # 판심=False 는 판심 걸러내기만 끔(가장자리 후보 없이)
    xpitch, cols = find_columns(g, 판심떼기=(not 후보) if 판심 is None else 판심, 표준자간=표준자간 if 읽기 else None, 끝띠=끝띠)
    if not cols or not xpitch:
        return None
    본열수 = None
    if 후보:
        본열수 = len(_drop_margin_column(list(reversed(cols))))
        cols = _가장자리후보(cols, xpitch, g.shape[1])
    pitch = xpitch * ratio
    prof = ink_profile(g, cols)
    T, B = page_frame(g, cols, 읽기)
    쪽광곽 = bool(읽기) and FRAME_LOCAL and _frame_read(g, cols) is not None   # 열마다 다듬을 수 있나(`_열광곽`)
    if 후보 and EDGE_MOVE:
        cols = _줄에서비키기(g, cols, xpitch, T, B)
        prof = ink_profile(g, cols)

    # 두 단인 것은 문헌 단위로 이미 정해져 있으니 '어디인가'만 찾는다(문턱을 낮게 둔다).
    div = tier_divider(g, cols, agree=0.10) if 단 >= 2 else None
    if div:
        da, db = div
        위 = spans_between(prof, cols, T, max(T + 1, da - 6), pitch)
        아래 = spans_between(prof, cols, min(B - 1, db + 6), B, pitch)
        div = None if (위 is None or 아래 is None) else div
    if div:
        spans = list(위) + list(아래)
        cols = list(cols) + list(cols)          # 같은 x 자리를 두 번 쓴다
        sm = [smooth(p, max(2.0, pitch / 9)) for p in prof]
        sm = sm + sm
    else:
        TT, BB = T, B
        if 쪽광곽:
            TT, BB = _열광곽(g, cols, T, B, xpitch, pitch)
        spans = spans_between(prof, cols, TT, BB, pitch, 이어=이어)
        sm = [smooth(p, max(2.0, pitch / 9)) for p in prof]
    if spans is None:
        return None
    est = [0 if s is None else max(1, int(round((s[1] - s[0]) / pitch))) for s in spans]

    # 글자를 오려낼 상자는 열보다 넓어야 한다 — 모음(ㅏ ㅓ ㅣ)의 가는 획이 열 밖으로 밀려나 잘리면
    # ㅏ·ㅓ·ㅣ 와 아래아를 못 가른다. 넓이는 가로 자간(열 간격)에 맞춘다.
    half = xpitch * 0.45
    W = g.shape[1]
    crop_cols = [(max(0, int((a + b) / 2 - half)), min(W, int((a + b) / 2 + half)))
                 for a, b in cols]
    맞춤 = 글자폭 = None
    if CROP_FIT:
        # 행간이 넓은 책 — 글자가 상자 폭의 반도 안 차는 쪽만 상자를 글자 크기로 좁힌다.
        q = _글자폭몫(g, crop_cols, spans)
        글자폭 = q
        if q is not None and q < CROP_FIT and ratio < CROP_FIT_RATIO:
            half = half * q / CROP_FIT_TO
            crop_cols = [(max(0, int((a + b) / 2 - half)), min(W, int((a + b) / 2 + half)))
                         for a, b in cols]
            맞춤 = 2 * half
    out = dict(cols=cols, crop_cols=crop_cols, spans=spans, sm=sm, pitch=pitch,
               xpitch=xpitch, est=est, 단=2 if div else 1, 가장자리=후보,
               image=Image.open(path).convert("L"))
    if 맞춤:
        out["맞춤"] = 맞춤
    if 글자폭 is not None:
        out["글자폭몫"] = 글자폭
    if 본열수 is not None:
        out["본열수"] = 본열수
    return out
