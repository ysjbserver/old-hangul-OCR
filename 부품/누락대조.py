"""전사문과 독립적으로 읽은 스캔에서, 앞뒤가 맞는 1~3글자 누락만 찾는다.

같은 열의 앞뒤 글자가 맞고 확신이 높으며 잉크로 다시 잘라도 같을 때만.
"""
import difflib
import unicodedata
import numpy as np
import align
import scan


def _글자(c):
    """모델 글자표가 같은 글자로 다루는 둥근 부호와 한글 조합을 맞춘다."""
    return unicodedata.normalize('NFC', c).replace('〇', '○')


def _재확인(mdl, geo, 주변, 앞수, 칸수, 촘촘=False):
    """독립 OCR 구간을 경계 검출기 없이 다시 잘라, 이웃까지 같은지 확인한다."""
    열 = 주변[0][3]
    x0, x1 = geo['crop_cols'][열]
    y0, y1 = 주변[0][2][1], 주변[-1][2][3]
    sm = geo['sm'][열]
    if 촘촘:
        pts = list(range(y0 + 1, y1, max(1, (y1 - y0 + 1023) // 1024)))
    else:
        pts = scan.cut_points(sm, y0, y1, geo['pitch'])
    cuts, _ = scan.split_column(sm, y0, y1, len(주변), pts)
    if not cuts:
        return None
    boxes = [(x0, s, x1, e) for s, e in zip(cuts[:-1], cuts[1:])]
    heights = [e - s for _, s, _, e in boxes]
    mid = max(1.0, float(np.median(heights)))
    if any(h < mid * 0.55 or h > mid * 1.7 for h in heights):
        return None
    L, V, T, cf = mdl.read(geo['image'], align._맞춤상자(align.잉크판(geo), boxes, geo))
    if [_글자(mdl.letter(l, v, t)) for l, v, t in zip(L, V, T)] != [z[0] for z in 주변]:
        return None
    if min(cf) < 0.8 or min(cf[앞수:앞수 + 칸수]) < 0.90:
        return None
    return float(min(cf[앞수:앞수 + 칸수]))


def 후보찾기(mdl, geo, 글자들, raw):
    전사 = [_글자(g[0]) for g in 글자들]
    읽음 = []
    for 열, z in enumerate(align.열마다읽기(mdl, geo)):
        if z is not None:
            읽음.extend((_글자(c), float(p), b, 열) for c, p, b in zip(z[1], z[2], z[3])
                        if c not in align.PUNCT_DROP)
    ops = difflib.SequenceMatcher(None, 전사, [z[0] for z in 읽음], autojunk=False).get_opcodes()
    후보 = []
    for i, (tag, a, b, c, d) in enumerate(ops):
        if tag != 'insert' or not 1 <= d - c <= 3 or i == 0 or i + 1 == len(ops):
            continue
        앞, 뒤 = ops[i - 1], ops[i + 1]
        if 앞[0] != 'equal' or 뒤[0] != 'equal' or 앞[2] - 앞[1] < 3 or 뒤[2] - 뒤[1] < 3:
            continue
        if any(g[3] for g in 글자들[a - 3:a + 3]):
            continue                           # SIC/의도적 원문 오식 주변은 제외
        if raw[글자들[a - 1][2]:글자들[a][1]].strip():
            continue                           # 걷어낸 틀/태그 안 글자를 누락으로 복원하지 않음
        시작, 끝 = c - 3, d + 3
        열경계 = len({z[3] for z in 읽음[시작:끝]}) != 1
        if 열경계:
            열 = 읽음[c][3]
            if any(z[3] != 열 for z in 읽음[c:d]):
                continue                       # 누락 자체가 열을 건너면 보류
            왼, 오른 = c, d
            while 왼 > 앞[3] and c - 왼 < 6 and 읽음[왼 - 1][3] == 열:
                왼 -= 1
            while 오른 < 뒤[4] and 오른 - d < 6 and 읽음[오른][3] == 열:
                오른 += 1
            앞수, 뒤수 = min(3, c - 왼), min(3, 오른 - d)
            뒤수 += min(6 - 앞수 - 뒤수, 오른 - d - 뒤수)
            앞수 += min(6 - 앞수 - 뒤수, c - 왼 - 앞수)
            if 앞수 < 1 or 뒤수 < 1 or 앞수 + 뒤수 < 6:
                continue                       # 같은 열의 양쪽 이웃 · 합계 여섯 글자 필요
            시작, 끝 = c - 앞수, d + 뒤수
            if any(g[3] for g in 글자들[a - 앞수:a + 뒤수]):
                continue
        주변 = 읽음[시작:끝]
        if min(z[1] for z in 주변) < 0.8:
            continue
        빠진 = 읽음[c:d]
        한글 = lambda c: any(0xAC00 <= ord(ch) <= 0xD7A3 or 0x1100 <= ord(ch) <= 0x11FF for ch in c)
        if min(z[1] for z in 빠진) < 0.90 or any(not 한글(z[0]) for z in 빠진):
            continue
        # 누락과 같은 열의 이웃 여섯 글자를 잉크만으로 다시 잘라 확인
        열 = 주변[0][3]
        x0, x1 = geo['crop_cols'][열]
        확인 = _재확인(mdl, geo, 주변, c - 시작, d - c)
        if 확인 is None and 열경계:
            확인 = _재확인(mdl, geo, 주변, c - 시작, d - c, 촘촘=True)
        if 확인 is None:
            continue
        # 넣을 자리 = 다음 인쇄 글자 앞
        pos = 글자들[a][1]
        box = (x0, 빠진[0][2][1], x1, 빠진[-1][2][3])
        # 그림용 — 같은 열의 앞 한 칸 · 누락 칸 · 뒤 한 칸
        이웃 = [읽음[c - 1][2], box, 읽음[d][2]]
        후보.append(dict(갈래='누락', 번호=a, 전사='', 스캔=''.join(z[0] for z in 빠진),
                         시작=pos, 끝=pos, 칸=d - c, 전사확률=0.0,
                         확신=float(min(min(z[1] for z in 빠진), 확인)),
                         점수=float(d - c), 합의=True, 누락상자=box, 누락이웃=이웃,
                         앞=''.join(g[0] for g in 글자들[max(0, a - 5):a]),
                         뒤=''.join(g[0] for g in 글자들[a:a + 5])))
    return 후보
