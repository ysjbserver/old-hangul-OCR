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
YX_RATIO = 0.867    # 세로 자간 ÷ 가로 자간 (셩경젼셔 신약 실측 평균, 편차 0.044)
GLYPH = 0.35        # 글자가 있는 줄은 열 폭의 이만큼 이상이 잉크다
# 읽을 때 구간 끝의 가는 글자 이어 붙이기 (_이어잡기, 2026-09-27)
SPAN_EXTEND = True  # 떼어 둔 쪽 4.62 → 4.13% · 고르는 쪽 6.39 → 6.01% (재학습 없음)
SPAN_LOW = 0.15     # 이만큼 넘는 줄을 잇는다 (고르는 쪽: 0.25 6.08 · 0.20 6.01 · 0.15 5.92% · 0.10 은 0.15 와 편차 안)
SPAN_REACH = 1.5    # 구간 밖으로 이 자간까지만 (1.0 · 2.0 과 같음)
SPAN_GAP = 0.4      # 빈 줄이 이 자간 넘게 이어지면 멈춤
# 읽을 때 광곽 높이를 열마다 따로 (_열광곽, 2026-09-29) — 기운·휜 광곽이 끝 열의 띠 안으로 들어오는 것
FRAME_LOCAL = True
FRAME_LOCAL_FILL = 0.6    # 열 + 안쪽 고랑 띠의 이만큼이 잉크인 줄을 광곽 가로줄로 (고르는 쪽: 0.85 4.42 · 0.6 4.37 · 0.5 4.39%)
FRAME_LOCAL_REACH = 0.35  # 쪽 광곽 줄에서 세로 자간의 이만큼 안에서만 찾음
FRAME_LOCAL_EDGE = 8      # 찬 줄에서 이 px 까지 흐린 줄(열 폭의 GLYPH 넘는 줄)도 광곽 줄로 친다

# ── 열 찾기 ──────────────────────────────────────────────────────────
def _columns_at(ink, W, th):
    """
    한 문턱으로 잉크 덩어리를 잡아 (덩어리들, 자간). 쓸 만하지 않으면 None.

    `find_columns` 의 ①②③ 앞부분이다 — 문턱을 바꿔 두 번 불러 보려고 뗐다.
    """
    runs, s = [], None
    for x, v in enumerate(ink):
        if v > th and s is None:
            s = x
        elif v <= th and s is not None:
            if x - s > 10: runs.append([s, x])
            s = None
    if s is not None and W - s > 10: runs.append([s, W])
    if len(runs) < 3: return None

    wmed = np.median([b - a for a, b in runs])          # ② 폭이 절반도 안 되면 여백
    runs = [r for r in runs if (r[1] - r[0]) > wmed * 0.55]
    if len(runs) < 3: return None

    cen = [(a + b) / 2 for a, b in runs]
    d = [gg for gg in np.diff(cen) if gg > 40]
    if not d: return None
    return runs, float(np.median(d))


PITCH_OFF, PITCH_ON = 0.15, 0.12     # PITCH_ON 0.10 → 0.12 (2026-10-01 — 아래 `find_columns` 의 ★)
PITCH_MORE = 1.5    # 간격이 표준 근처라도 다른 문턱이 열을 이 배 넘게 더 찾으면(간격은 PITCH_ON 안) 바꿈. 0 = 끔
INK_EDGE = 0.0      # 스캔 양 끝 이 몫에 걸친 **거의 위아래가 다 검은 띠**(제본 그림자)를 열 찾기 전에 지움 — 자르는 경로만(아래 ★). 0 = 끔
                    # ⚠ 늘 켜면 안 됨(아래 ★) — 기본은 끄고, 전사대조만 `find_columns(…, 끝띠=True)` 로 **다른 후보 하나**로 씀
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

    판심떼기=False 는 **읽을 때(한 단 판형)** 만 쓴다 — `page_geometry` 가
    대신 양 끝에 후보 열을 붙이고 `align.read_page` 가 확신도로 가린다.
    `_가장자리후보` 참고.
    """
    H, W = g.shape
    ink = (g[int(H*0.12):int(H*0.88), :] < INK).sum(axis=0).astype(float)
    # ★ (2026-10-02) **스캔 끝의 제본 그림자** — 거의 위아래가 다 검은 띠가 끝에 붙어 있으면 그 띠를 지우고 잰다(`_끝띠지우기`).
    #   권2 0003: 오른쪽 끝 띠(2,036줄 · 본문 열 565~925)가 ① 아래 문턱의 잣대가 되어 옅은 마지막 열이 빠지고 ② 그 자체가 열이 되어
    #   '빠진 열 채우기' 가 띠와 첫 열 사이에 없는 열 둘을 넣음 → 전사대조 일치 4%.
    #   ⚠ **판심떼기=True 일 때만**(자르는 경로 · 가장자리 후보 없는 기하 — 전사대조 · 교정 · 자동 라벨). 읽는 경로는 양 끝 후보 열 +
    #     `가장자리다듬기` 가 띠를 이미 가리고, 손대면 그 가림이 흐트러짐(해 봄: 권2 0327 2.1 → 12.7%).
    #   ⚠ 띠 '덩어리' 를 통째로 버리면 안 됨 — 낮은 문턱에서 띠와 바깥 열이 한 덩어리로 붙음(권1 1329). 잣대를 늘 양 끝 빼고 재도 안 됨 —
    #     여백 장 제목이 열로 잡힘(요한복음 0065, 떼어 둔 2.08 → 2.17%).
    #   ⚠⚠ **늘 켜면 안 됨** — 잣대(가장 진한 줄)가 바뀌면 문턱이 옮겨 가 결과가 양쪽으로 튐. 자르는 경로 표본 175쪽(바뀐 쪽만):
    #     일치 63.4 → 64.5% 지만 30쪽 나빠지고 11쪽은 무너짐(훈아진언 0046 89 → 10% — 왼쪽 끝 17px 띠가 잣대였음).
    #     → 기본 끔. 전사대조가 `끝띠=True` 기하를 **셋째 후보**로 만들어 전사문과 더 잘 맞을 때만 씀(표본 63.4 → 68.6%, 나빠짐 0).
    몫 = INK_EDGE if 끝띠 is None else (EDGE_ZONE if 끝띠 else 0.0)
    if 몫 and 판심떼기:
        ink = _끝띠지우기(ink, int(H*0.88) - int(H*0.12), W, 몫)
    if ink.max() <= 0:
        return None, []
    # ★ 문턱은 최대값에 맞추되, **실패하면 낮춰 다시 잡는다** (2026-09-08).
    #
    #   `ink.max() * 0.12` 가 기본이다. 최대값은 보통 **세로 광곽선**이라
    #   쪽 높이만큼 잉크가 차서 안정적이다. 그런데 **광곽선이 흐리거나 없는
    #   쪽**에서는 최대값이 본문 열에서 나오고, 문턱이 그 쪽 잉크의 75 백분위
    #   까지 올라가 열이 문턱 위로 **뾰족한 끝만 삐져나온다.**
    #   구약 권2 0309 에서 덩어리 폭이 12~17px 로 잡혔다(진짜 열은 80px).
    #   간격이 엉켜 자간이 193 으로 잘못 잡히고 열 13개가 5개로 뭉갰다.
    #
    #   ⚠ **문턱을 늘 낮추면 안 된다.** 90 백분위 기준(`p90*0.25`)으로 바꿔
    #   봤더니 권2 는 36.4% → 15.6% 로 좋아지는데 **여섯 문헌이 나빠졌다**
    #   (신약젼셔 6.0% → 13.2%). 멀쩡한 쪽에 없던 열이 생긴다.
    #   ⚠⚠ **`|짐작합 / 참글자수 − 1|` 로 고르지 마세요.** 그 지표로는 여덟
    #   문헌이 다 좋아진다고 나왔지만 실제 CER 은 여섯이 나빠졌습니다.
    #   **`성적재기.py` 로 고르세요.**
    #
    #   그래서 **자기 진단**을 쓴다 — 잡은 덩어리의 폭이 자간에 견줘 너무
    #   좁으면(정상 0.4 안팎, 권2 0309 는 **0.08**) 문턱이 높은 것이므로
    #   낮춰 다시 잡는다. 멀쩡한 쪽은 첫 번째에서 끝나 예전과 **한 픽셀도
    #   다르지 않다**(셩경젼셔 신약 40쪽 표본에서 37쪽이 15열 그대로).
    #
    #   ⚠ **'덮개'(열이 잉크 너비를 얼마나 덮나) 를 함께 보는 것은 해 봤고
    #      접었습니다. 다시 시도하지 마세요.** 평균은 12.4% → 12.1% 로 좋아
    #      보이는데(권2 29.9 → 23.6, 요한복음 12.9 → 10.7), **신약젼셔 0659
    #      한 쪽이 CER 6.4% → 161.5%** 가 됩니다. 글자 109자짜리 짧은 쪽이라
    #      열 4개가 맞는 답인데, 잉크 너비에 **광곽과 판심이 들어가** 덮개가
    #      0.23 으로 나오고, 되돌림이 16열로 부풀려 **없는 글자를 지어냅니다.**
    #      평균 0.3%p 보다 이쪽이 나쁩니다.
    #      '되돌림은 열을 1.5배 넘게 더 찾을 때만' 조건을 덧대면 0659 는
    #      막히지만 권2·요한복음을 돕던 되돌림까지 막혀 **넓이만 쓰는 것과
    #      점수가 같아집니다**(12.4%). 그러면 단순한 쪽이 낫습니다.
    #   ⚠ **'문헌 자간을 알려 주기' 는 해 봤고 걷어냈습니다. 다시 하지
    #      마세요.** 열 간격은 문헌 안에서 놀랍도록 일정하고(문헌 여덟·40쪽씩
    #      에서 25/75 백분위가 107/108, 104/105 처럼 몇 px 안), 권2 의 남은
    #      문제 쪽은 167·176·224·270·897 로 크게 벗어나(중앙값 113) 알아보기
    #      쉬워 **보입니다.** 그런데 성적이 **한 문헌도 안 움직였습니다**
    #      (12.4% → 12.4%). 까닭은 그 쪽들에서 **두 문턱 다 자간이 틀리기**
    #      때문입니다 — 알아봐야 고를 것이 없습니다. 자세한 것은
    #      `문서/실험_광곽뿌리.md`.
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
    # ★ **읽을 때만** — 고른 자간이 문헌 표준(`page.doc_layout`)에서 15% 넘게 벗어나고
    #   다른 문턱의 자간이 10% 안이면 그것으로 바꾼다 (2026-09-26).
    #   구약 권2 0196~0460 은 인쇄가 흐려 본문 열 잉크가 약한데, 최대값은 **제본 골의
    #   검은 띠**가 차지한다. 그러면 첫 문턱을 넘는 것이 진하게 찍힌 몇 열뿐이고(0327:
    #   15열 중 4열, 자간 94), 폭은 그럴듯해 위의 자기 진단에도 안 걸린다. 둘째 문턱은
    #   15열·자간 107 로 맞게 잡는다. 표준에 가까운 쪽은 **한 픽셀도 안 바뀐다.**
    #   ⚠ 예전의 '문헌 자간 알려 주기'(위 ⚠)는 두 문턱이 **다 틀린** 쪽들이라 실패했다.
    #     여기는 한쪽이 맞을 때만 바꾼다.
    # ★ (2026-10-01) **처음 보는 문헌**에서는 표준이 그림으로 잰 값이라 흔들린다 — 권2 는 열 간격이 책 앞
    #   110~115 · 뒤 97~106 이라 표준이 104.5 로 나오고, 그러면 0327(자간 94 · 4열)은 10% 뿐이라 안 걸리고
    #   0245 는 둘째 문턱(115)이 10.05% 로 0.05px 차이에 버려졌다. 그래서 둘을 더함:
    #   ① `PITCH_MORE` — 간격이 가까워도 다른 문턱이 **열을 1.5배 넘게 더 찾으면** 바꿈(0327: 4 → 15열).
    #     4열이 정답인 짧은 쪽(신약젼셔 0659)은 둘째 문턱도 5열이라 안 걸림.
    #   ② `PITCH_ON` 0.10 → 0.12.
    #   처음 보는 권2(표준 104.5) 떼어 둔 쪽 15.1 → 4.3%. 적힌 설정으로는 떼어 둔 2.43 · 고르는 4.37% 그대로
    #   (권2 떼어 둔 4.08 → 4.11 만) — `실험14` 로 둘 다 잼.
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

    # ⑤ 판심 걸러내기.
    # 쪽 이름·쪽 번호가 적힌 줄(판심)은 광곽 밖에 있어서, 본문 열보다 **멀리**
    # 떨어져 있다. 본문 열은 활자 간격이라 104~110px 처럼 일정한데
    # 판심은 133~148px 처럼 확 벌어진다. 양 끝에서 그런 열을 떼어낸다.
    # 이것을 남겨 두면 그 열이 전사문 글자를 20여 개 먹어 뒤가 통째로 밀린다.
    if 판심떼기:
        out = _drop_margin_column(out)
    return pitch, list(reversed(out))


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
    **읽을 때** 양 끝에 후보 열을 붙인다. 버릴지는 `align.가장자리다듬기` 가
    모델 확신도로 정한다. (2026-09-25)

    ★ 왜 — 쪽의 맨 오른쪽·맨 왼쪽 열이 **통째로** 빠지는 일이 잦았다
    (작업자가 실제로 쓰다 발견). 전사문과 대 보니 빠진 글자가 거의 늘 열
    하나 분량(25~30자)이었고, 뿌리는 가장자리 열을 **그림 모양만 보고**
    버리는 장치 둘이었다:
      · `_drop_margin_column` — 광곽 선에 붙은 가장자리 열은 덩어리가 선 쪽으로
        끌려가 이웃과의 간격이 1.3배쯤 된다. 판심과 **간격으로는 못 가른다**
        (진짜 판심도 1.25~1.4배). 요한복음 0049 · 훈아진언 0101 · 0113.
      · `page.테두리열버리기` — **제본 쪽 그림자**가 잉크로 세어져 진짜 열이
        2~6배로 나온다. 구약 권2 0088 · 0146 · 0668 · 권1 0361.
    그래서 읽을 때는 둘 다 끄고, 모자란 쪽을 후보로 채운다.

    붙이는 것 (한쪽에 둘):
      · **제자리** — 둘째 열에서 자간 하나 바깥. 가장자리 열의 덩어리가 광곽
        선이나 그림자에 끌려 **밀려 있을 때** 제자리를 준다(훈아진언 0101).
      · **한 칸 더 바깥** — 가장자리 열을 아예 못 찾았을 때.
    겹치는 것은 `align.가장자리다듬기` 가 점수 높은 쪽만 남긴다.
    그림 밖으로 나가는 후보와, **이미 있는 열과 똑같은** 후보는 붙이지 않는다.
    ⚠ 똑같은 상자 둘은 점수가 1e-6 쯤만 달라, 겹친 것 중 무엇을 남길지가
      CUDA 와 WASM 에서 뒤집혔다(대조 셩경젼셔 0262 · 시편촬요 0087). 글자는 같다.

    ⚠ **자를 때는 쓰지 마세요.** `to_text` 는 열을 0 칸으로 버릴 수 있어
      이 문제가 없고, 거기서 기하를 바꾸면 사람 교정이 무효가 됩니다.
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
FRAME_GUTTER_CUT = 0.6     # 자르는 경로(교정서버 · 자동 라벨 · 데이터셋)의 같은 규칙 — 0 = 끔 (2026-10-02 켬, 작업자 승인 · 옛 실험 조리법은 0 으로 고정)
# ★ (읽을 때만, 2026-10-06) 광곽이 없는 근대 책 — 쪽 머리(「默沈의님」) 밑 가로줄만 있거나 쪽 번호 줄표(「—( 40 )—」)만 있는 쪽.
#   옛 규칙은 열마다 위 · 아래 줄을 **둘 다** 찾아야 해서 기본값(6% · 95%)으로 떨어지고, 쪽 머리 · 쪽 번호가 열 안에 들어와
#   '으 · 아 · ㄱ' 로 읽혔다(님의 沈黙 13.4 → 11.8%). 옛 규칙이 **위 · 아래 둘 다 기본값으로 떨어진 쪽만** 한쪽씩 다시 찾음.
#   옛 여덟 문헌도 그런 쪽은 바뀜 — 떼어 둔 2.08 → 2.09%(권1 0593 3.7 → 2.0 · 0847 4.9 → 2.2 / 요한복음 0071 4.8 → 7.5 · 권2 1217 1.3 → 1.9),
#   고르는 4.09 → 3.94%(요한복음 3.70 → 2.83).
#   고랑 규칙(`FRAME_GUTTER`)도 같이 씀(글자 획은 고랑에서 끊김). False = 끔. JS 짝 `광곽` · 설정 `광곽한쪽`
FRAME_ONESIDE = True
FRAME_GUTTER = 0.6        # (읽을 때만) 옛 `_frame` 이 열마다 찾은 줄은 옆 고랑의 이 몫 넘게 찬 것만 광곽으로(0 = 끔, 2026-10-02 · `page_frame`)


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
    **읽을 때** 쪽 끝의 후보 열 상자 안으로 세로줄(광곽·제본 골의 검은 띠)이 지나면
    그 열을 줄 안쪽으로 옮긴다. (2026-09-26)

    제본 쪽 끝 열은 덩어리가 골의 검은 띠에 끌려 **글자에서 40~50px 벗어나 띠 위에**
    잡힌다(구약 권2 0164 · 1129). 그러면 오린 그림이 반은 띠, 반은 글자라 헛읽고,
    `align.가장자리다듬기` 가 버려 열 하나가 통째로 빠진다. 줄 안쪽 가장자리에서
    자간의 `EDGE_MOVE_GAP` 만큼 들어간 자리로 옮기되, 안쪽 이웃과 `EDGE_MOVE_MIN`
    보다 가까워지지 않게 한다(더 가까우면 `가장자리다듬기` 가 겹친 열로 보고 하나를 뗌).
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
            continue                                 # 옮길 자리가 빈 여백이면 둔다(시편촬요 0097)
        cols[k] = 새
    return cols


def 세로줄있나(g, xa, xb, T, B, 토막=FRAME_SEG, 덮개=FRAME_FILL, 합의=FRAME_AGREE):
    """
    x 가 [xa, xb) 인 띠에 **끊기지 않은 세로줄**(광곽 선·제본 골의 검은 띠)이 있는가.
    (2026-09-26, `align.가장자리다듬기` 가 광곽 안팎을 가를 때 씀)

    [T, B) 를 `토막` px 씩 나눠, 토막마다 어느 x 한 줄이라도 잉크가 `덮개` 이상이면
    그 토막에 줄이 있다고 본다. 토막의 `합의` 이상에 있으면 참.
    ★ 토막으로 나누는 까닭 — 제본 쪽으로 쪽이 휘어 줄이 기운다. 쪽 전체를 한 x 로
      재면 놓친다(쪽 전체로 재서 지우기를 해 봤다가 셩경 개역이 2.6 → 6.2%).
    글자 획은 글자 사이가 비어 300px(서너 자) 을 0.85 로 덮지 못한다.
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
    광곽(테두리) **안쪽** 위·아래를 '열들의 합의'로 찾는다. 못 찾으면 None.

    ⚠⚠ **읽을 때만 쓰세요**(`page_frame(읽기=True)`). 자를 때 쓰면 나빠집니다 —
    아래 `page_frame` 의 설명을 보세요.

    ★ **세로쓰기에서는 글자 줄이 열끼리 가로로 맞을 이유가 없습니다.**
    여러 열을 한꺼번에 가로지르는 것은 광곽뿐입니다 — `tier_peak` 이 두 단
    판형을 가려낼 때 쓰는 것과 같은 성질입니다.

    무엇이 잘못돼 있었나 — `_frame` 은 열마다 `top[0]`·`bot[-1]` 을 집는데,
    그것은 광곽이 쌍변일 때 **바깥 줄**이고 때로는 **스캔 가장자리의 검은 띠**
    입니다(훈아진언 0061: 아래 경계 4364 / 그림 높이 4371, 진짜 테두리는
    4155~4186). 그러면 테두리 선이 글자 구간을 재는 띠 안에 들어오고, 선은
    열 폭을 다 채우니 `spans_between` 이 '글자 줄'로 세어 짐작(`est`)이
    부풉니다. 그것이 읽기 자간 덧값·제목 열이 안 맞는 것·`to_text` 가 열
    하나를 제물로 버려야 했던 것의 **공통 뿌리**였습니다.

    문턱은 실측으로 골랐습니다(문헌 일곱·35쪽에서 `|est/참 − 1|`):
    fill 0.90 · agree 0.30 에서 19쪽이 걸리고 오차가 0.121 → 0.081.
    `fill` 을 0.60 까지 낮추면 글자 획이 섞여 들어와 0.222 로 크게 나빠집니다.
    0.90 은 `_frame` 이 쓰던 값이라 새로 들여온 생각은 '합의' 하나뿐입니다.
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

    ★★ **읽을 때와 자를 때가 일부러 다릅니다** (2026-09-08 실측).
    `page.테두리열버리기` 와 같은 모양의 비대칭입니다.

    | | 쓰는 것 | 왜 |
    |---|---|---|
    | **읽기**(4단계) | `_frame_read` — 광곽 **안쪽**까지 바짝 | 짐작(`est`)이 맞아야 칸 수를 고른다. 17.7% → **14.4%** |
    | **자르기**(2단계) | 옛 방식 — **넉넉하게** | 띠가 글자를 물면 상자가 통째로 밀린다 |

    ⚠⚠ **자르는 쪽에 `_frame_read` 를 쓰지 마세요.** 2026-09-08 에 넣어
    봤습니다. 읽기는 14.4% 로 좋아지는데, 그 기하로 상자를 다시 오려 학습하면
    **문헌 여덟이 다 나빠집니다**(14.4% → 16.2%). 띠가 글자를 한두 개 물기
    때문입니다 — 훈아진언 0061 에서 아래로 243px 인데 자간이 131 입니다.
    ⚠ '광곽 줄을 `ink_profile` 에서 지우기' 도 해 봤습니다. 자르기는 안
    망가지지만 읽기 이득이 절반뿐입니다(16.3%). 지금 판이 낫습니다.
    → 자세한 것은 `문서/실험_광곽뿌리.md`.
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
            # ★ (읽을 때만, 2026-10-02) 열마다 찾은 줄 중 **옆 고랑(열 사이)까지 찬 것만** 광곽으로 — 글자 획은 고랑에서 끊김.
            #   굵은 활자는 획이 열 폭의 90% 를 채워 `_frame` 에 걸림: 테두리 없는 딱지본(봉황대 0009 — 위 222~684 가 흩어졌는데
            #   중앙값 397 을 광곽으로 써 열마다 위 2자 · 아래 5자를 버림) · 기운 광곽에 획이 섞인 쪽(권2 0653).
            #   잰 고랑 몫: 진짜 광곽 0.75~1.0 · 글자 획 0~0.44. 위 · 아래 따로, 인정된 것이 둘 미만이면 기본값.
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


# ★ (읽을 때만, 2026-10-06) 쌍줄 광곽의 **가는 안쪽 줄**은 열 폭의 74% 쯤만 채워 `_frame`(90%)에 안 걸리고, 글자 구간이 그 줄 끝자락부터
#   시작해 열 머리마다 헛글자 '나 · 니'(증남포 장정). 열 폭의 이 몫 + **옆 고랑**의 이 몫을 함께 채운 줄이 열의 30% 넘게 같은 높이에
#   있으면 광곽 줄로 봄(글자 획은 고랑에서 끊김 — `FRAME_GUTTER` 와 같은 생각). 옛 경계보다 **조금 안쪽**(쪽 높이 10% 안)일 때만 옮김.
#   ⚠ '열 머리의 가는 덩이 떼기' 는 2026-09-29 에 크게 실패(가는 글자 '이' 를 뗌) — 이것은 고랑을 건너는 줄만 봄. 0 = 끔
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
    **열마다** 광곽 안쪽 위·아래 — 읽을 때만, `_frame_read` 가 쪽 광곽을 찾았을 때만(2026-09-29).
    반환: (Ts, Bs) 열마다. 쪽 값보다 **안쪽으로만** 옮긴다(광곽 줄이 띠 안에 들어온 열만 바뀐다).

    `_frame_read` 는 쪽 하나에 T·B 한 쌍이라, 광곽이 조금만 기울어도(신약젼셔 0012: 가로 1,700px 에 20px)
    한쪽 끝 열에서는 광곽 줄이 띠 안에 들어온다. 그러면 `spans_between` 이 그 줄을 글자 줄로 세어
    반쯤 빈 끝 열의 구간이 쪽 끝까지 늘고(408~1568 → 235~2907), 빈 칸을 억지로 읽어 열 점수가
    떨어져 `align.가장자리다듬기` 가 **제대로 읽은 열을 통째로** 버렸다.
    그래서 쪽 광곽 줄(T−4 · B+4) 근처 `FRAME_LOCAL_REACH` 자간 안에서, 열마다 **열 + 쪽 가운데 쪽 고랑**을
    합친 띠가 `FRAME_LOCAL_FILL` 넘게 찬 줄을 찾는다 — 고랑까지 가로지르는 것은 광곽뿐이라 글자 획을
    광곽으로 잘못 집지 않는다. 못 찾은 열은 x 로 양옆(찾은 열)을 곧게 잇는다(`잇기`).
    ⚠ 2026-09-28 에 해 보고 버린 '기운 광곽을 한 높이로 찾기' 와 다르다 — 그것은 쪽 광곽을 **못 찾은**
      쪽에서 새로 찾으려다 글자 획을 집었다. 이것은 찾은 쪽 광곽을 열마다 다듬기만 한다.
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
    구간 끝의 **가는 글자**를 이어 붙인다 — 읽을 때만 (`SPAN_EXTEND`, 2026-09-27).
    `GLYPH`(열 폭의 35%) 를 못 넘는 첫·끝 글자(`이` 처럼 획이 열 밖으로 나가는 것 — 0.30~0.34)가
    구간에서 빠져 열마다 한 글자씩 통째로 안 읽혔다(요한복음 0011: 17열 중 8열). 구간 밖으로
    `SPAN_REACH` 자간 안에서 `SPAN_LOW` 를 넘는 줄을, 빈 줄이 `SPAN_GAP` 자간 넘게 끊기기 전까지 잇는다.
    ⚠ 광곽을 못 찾은 쪽에서 옛 방식(`_frame`)이 **글자 획을 광곽으로 집어** 열 머리 두세 글자를 버리는
      일이 있다(권2 0653 — 떼어 둔·고르는 쪽 약 220쪽 중 6쪽). T 너머로 3 자간까지 이어 보기를 해 봤지만
      낱말 사이 빈칸에서 멈추거나 광곽 줄까지 삼켜 버림(2026-09-27). 고치려면 기운 광곽을 찾는 쪽으로.
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

    종이 뒷면이 비쳐 보이는 것(배접)과 열 사이 계선 때문에, '잉크가 조금이라도
    있는 곳'으로 재면 늘 테두리 끝까지 나온다. 그래서 **열 폭의 35% 이상이
    잉크인 줄**만 글자 줄로 본다. 그래야 {{왼쪽 여백}}(들여쓴 인용)처럼
    중간에서 시작하거나 일찍 끝나는 열을 제대로 잡는다.
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

    ⚠ **열 하나만 보면 못 가립니다.** 획이나 계선도 '열 폭을 채운 가로줄'로
    잡히기 때문입니다 — 셩경젼셔(한 단짜리)에서 그렇게 세면 후보가 144개
    나옵니다. 열들의 합의로 보면 깨끗하게 갈립니다.
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
# 2026-09-26 시험 — 독립신문. `단` 자리에 **가름줄 높이 목록**(쪽 높이에 대한
# 비율)이 오면 이 갈래를 탄다. 1단·2단 경로는 건드리지 않는다.
#
# ★ 잣대는 **열 사이 고랑**이다. 글자 획은 고랑에서 끊기지만 가름줄은 고랑까지
#   가로지른다. '열을 채운 줄의 합의'(`tier_peak`)로는 독립신문의 가늘고 끊긴
#   줄(중앙값 0.35)과 한 단 성경의 가로획(최대 0.50)이 갈리지 않았다.
#   고랑으로 재면 한 단 문헌 여섯은 쪽 중앙값이 전부 0.00, 독립신문 0.78,
#   셩경 개역 1.00 (문헌마다 80쪽).
# ⚠ 쪽 하나로는 못 가른다 — 약한 가름줄(0.22)이 글자 잡음(~0.4)보다 약한
#   쪽이 있다. 그래서 문헌 단위로 '어느 높이인가' 를 먼저 정하고(`가름줄판정`)
#   쪽에서는 그 근처만 찾는다. 셩경 개역의 두 단 찾기와 같은 얼개다.
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
    # ⚠ 판정은 **채움 0.6** 으로 — 1896년 독립신문의 가름줄은 가늘고 끊겨 0.8 로는
    #   다섯에 하나가 0.4 를 못 넘는다(0.6 이면 95% 가 넘는다). 쪽을 **자를 때**는
    #   0.8 그대로 둔다(`_가름판_geometry`) — 느슨하면 글자 잡음이 '꽉 찬 줄'이 된다.
    #   한 단 문헌 일곱(516쪽)의 봉우리는 0.6 으로도 중앙 0.07 · 99% 0.46.
    G = 고랑곡선(g, cols, 채움=0.6)
    덩 = [((s + e) / 2 / H, m) for s, e, m in _줄덩이(G) if a <= (s + e) / 2 < b]
    return float(G[a:b].max()), 덩


def 가름줄판정(paths, 문턱=0.5, 센줄=0.4, 모음=0.03):
    """
    문헌이 가름줄 판형이면 **가름줄 높이 비율 목록**, 아니면 None.
    쪽들의 봉우리 중앙값이 `문턱` 이상이어야 하고, 가름줄은 쪽의 **절반 넘게**
    같은 높이(±`모음`)에 `센줄` 이상으로 나와야 한다. 쪽 위아래 20% 는 안 본다
    — 독립신문 첫 쪽의 제호·날짜 상자 줄(0.12 · 0.15 · 0.17)이 거기 있다. 15% 로는
    3쪽짜리 한 호에서 0.17 이 가름줄로 잡혔다(첫 쪽과 광고 쪽 둘에 걸림).
    """
    return 가름줄정하기([가름줄측정(p) for p in paths], 문턱, 센줄, 모음)


def 최소쪽(n):
    """판정에 쓸 쪽이 몇 개는 있어야 하나. 보통 4, **쪽이 적은 파일**(신문 한 호 3~4쪽)은 있는 만큼 — 단 2 이상."""
    return max(2, min(4, n))


def 가름줄정하기(잰것들, 문턱=0.5, 센줄=0.4, 모음=0.03):
    """`가름줄판정` 의 뒤 절반 — 쪽마다 `가름줄측정` 한 것(못 잰 쪽은 None)을 받는다. 브라우저판도 이것을 옮겼다."""
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


# 참 간격의 두 배로 접어도 또렷해서, 참값이 0.725 아래면 두 배를 집을 수 있다(구대소설봉황대: 그림 1.446 · 전사문 0.711).
# 열마다 고른 t 의 절반으로 접은 점수가 최고 점수의 이 몫 이상이면 t/2 (절반이 lo 안일 때만). None = 끔 (2026-10-02, `실험30`)
# 봉황대 1.446 → 0.725 · 권1 0.868 → 0.864 · 나머지 열셋 그대로. 0.8 은 신약젼셔도 옮기나 엇나간 열이 중앙값 아래로 간 우연
RATIO_HALF = 0.9
# ★ (2026-10-06) 열에서 고른 주기가 **글자 폭(`글자폭몫` × 상자 폭)의 RATIO_FIT_OVER 배를 넘으면** 그 열만 글자 폭의 RATIO_FIT 배 안에서 다시 찾음 —
#   행간이 넓고 띄어 쓴 근대 책에서 접기가 두세 글자 주기를 고르던 것(불상한 동무 1.106 · 님의 沈黙 1.382 · 증남포 1.185).
#   빽빽한 문헌의 글자 주기 ÷ 글자 폭은 1.04~1.53 이라 걸리지 않음. 그때는 `RATIO_HALF` 를 안 봄. None = 끔
RATIO_FIT = (1.0, 1.7)
RATIO_FIT_OVER = 2.0   # 1.7 이면 빽빽한 문헌도 몇 열이 걸려 값이 움직임(누가복음젼 1893 0.921 → 0.887) — 두 배 착각은 2.2 배 넘음


def page_ratio(path, lo=0.55, hi=1.45, steps=120, 단=1):
    """
    이 쪽의 '세로 자간 ÷ 가로 자간'을 **그림만 보고** 잰다. 전사문이 필요 없다.
    열마다 여러 간격으로 접어 보고 가장 또렷한 것을 고른 뒤, 열들의 중앙값을 쓴다.

    단=2 일 때는 **단을 나눈 뒤에** 잰다. 두 단을 이어 붙인 채로 재면 가운데
    가로줄과 단 사이 여백이 무늬를 흩뜨려 값이 작게 나온다
    (셩경 개역에서 0.815 대 0.96).
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
CROP_FIT = 0.62      # ★ 글자 폭 ÷ 상자 폭(열마다 세로로 모은 잉크가 최대의 10% 넘는 범위, 열 중앙값)이 이보다 작고 — 0 = 끔
CROP_FIT_RATIO = 0.70  #   자간비도 이보다 작은 쪽만 상자를 맞춤(빽빽한 문헌은 모두 0.71 넘음 — 훈아진언에는 글자폭몫 0.55 인 쪽이 있음)
CROP_FIT_TO = 0.78   #   그때 글자가 상자 폭의 이만큼이 되게 좁힘(빽빽한 문헌의 보통 값) · 칸 높이도 같은 크기로(`align._맞춤상자`)


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

    ratio 는 그 문헌의 '세로 자간 ÷ 가로 자간'. 문헌마다 다르므로
    step2_cut.py 자간 으로 재서 넣어 준다. 기본값은 셩경젼셔 신약 실측값.

    단=2 는 **한 쪽이 위아래 두 단으로 나뉜 판형**(셩경 개역). 그때는 열 하나를
    위·아래 둘로 쪼개고 **위 단을 오른쪽부터 다 읽은 뒤 아래 단**의 차례로
    늘어놓는다. 뒤 단계는 이것이 그냥 '열이 두 배로 늘어난 쪽'으로 보이므로
    align·sheet 는 아무것도 달라지지 않는다.
    문헌마다 정해 두는 값이다 — `corpus.doc_tiers` 참고.

    읽기=True 는 **전사문 없이 읽을 때(4단계)**. 광곽 경계를 다르게 잡는다 —
    `page_frame` 의 ★★ 를 보세요. 자를 때 켜면 학습이 망가집니다.
    한 단 판형이면 판심을 떼지 않고 양 끝에 후보 열도 붙인다(`_가장자리후보`).
    그때 `가장자리=True` 가 서고, `align.read_page` 가 확신도로 가장자리를 가린다.
    `본열수` 는 판심만 뗀 원래 열 수 — `page.쪽건강` 이 판짜임과 견줄 때 쓴다.
    가장자리=False 는 후보를 안 붙인다 — **재는 쪽**(`실험도구` 의 '일치')만 쓴다.
    `to_text` 에는 겹친 후보를 가려 줄 장치가 없어 일치가 무너진다(99% → 74%).
    이어=None 이면 `읽기` 를 따른다. 이어=True 는 **자를 때** 가는 글자 이어 붙이기(`_이어잡기`)만 따로 켠다 —
    자동 라벨을 만들 때만(2026-10-01, `page.prepare(…, 이어=True)`). 교정서버 · 사람 교정의 자르기는 끈 그대로.
    """
    이어 = bool(읽기) if 이어 is None else bool(이어)
    g = np.array(Image.open(path).convert("L"))
    if isinstance(단, (list, tuple)):             # 가름줄 판형 — 위 `_가름판_geometry`
        return _가름판_geometry(path, g, ratio, 단)
    후보 = bool(읽기) and 단 == 1 and 가장자리
    # 판심=False 는 판심 걸러내기만 끔(가장자리 후보 없이) — 전사대조의 후보 기하(훈아진언 1894 PDF 58쪽: 광곽에 붙은 끝 열을 판심으로 뗌)
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

    # 문헌이 두 단이라는 것은 이미 정해져 **알고** 들어온다. 그러니 여기서는
    # '있는가'를 다시 묻지 않고 **어디인가**만 찾는다(문턱을 낮게 둔다).
    # 셩경 개역에서 합의도는 쪽마다 0.14~1.00 으로 크게 흔들리지만 자리는 늘
    # 쪽 높이의 0.50~0.53 이라, 낮은 문턱으로도 제자리를 찾는다.
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

    # 글자를 오려낼 상자는 열보다 넓어야 한다.
    # 열은 '잉크가 진한 곳'으로 잡히는데, 세로쓰기 한글은 모음(ㅏ ㅓ ㅣ)이
    # 오른쪽에 가는 획 하나로 서 있어서 그 부분이 열 밖으로 밀려난다.
    # 그대로 오리면 모음이 잘려 나가 ㅏ·ㅓ·ㅣ 와 아래아(ᆞ)를 구별할 수 없다.
    # 활자는 네모꼴이므로 세로 자간만큼 넓히면 글자 한 벌이 온전히 들어온다.
    # 넓이는 세로 자간이 아니라 **가로 자간(열 간격)** 에 맞춘다.
    # 문헌마다 세로/가로 비율이 달라서, 세로 자간을 쓰면 어떤 문헌에서는 또 좁아진다.
    half = xpitch * 0.45
    W = g.shape[1]
    crop_cols = [(max(0, int((a + b) / 2 - half)), min(W, int((a + b) / 2 + half)))
                 for a, b in cols]
    맞춤 = 글자폭 = None
    if CROP_FIT:
        # ★ 행간이 넓은 근대 책(2026-10-06) — 글자가 상자 폭의 반도 안 차서(빽빽한 문헌 0.65~1.00 · 이런 책 0.42~0.52) 모델이
        #   작고 치우친 글자를 보고 확신이 떨어지고, '글자 아닌 칸' 규칙이 멀쩡한 글자를 버렸다. 이런 쪽만 상자를 글자 크기로.
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
