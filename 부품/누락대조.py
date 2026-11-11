"""전사문과 독립적으로 읽은 스캔에서, 앞뒤가 맞는 1~3글자 누락과 글자 수가 다른 곳만 찾는다.

같은 열의 이웃과 독립 재자르기로 확인한다. 열 첫/끝은 한쪽 여섯 글자와 칸수 대안도 확인한다.
"""
import difflib
import unicodedata
import numpy as np
import align
import scan


글자수찾기 = True   # 전사문과 스캔의 글자 수가 다른 곳(덧글자 · 두 글자 ↔ 한 글자)도 낸다


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


def _끝확인(mdl, geo, 주변, 앞수, 칸수):
    """한쪽 이웃만 있는 누락은 두 잉크 자르기와, 누락이 없다는 칸수 대안으로 확인한다."""
    g = align.잉크판(geo)
    for z in 주변[앞수:앞수 + 칸수]:
        폭, 가로 = scan.칸모양(g, z[2])
        if 폭 < 0.45 or 가로 >= 0.85:
            return None                       # 작은 여백 글자 · 광곽 획은 보류
    확인들 = [_재확인(mdl, geo, 주변, 앞수, 칸수, 촘촘=v) for v in (False, True)]
    if any(v is None or v < 0.93 for v in 확인들):
        return None
    열 = 주변[0][3]
    x0, x1 = geo['crop_cols'][열]
    y0, y1 = 주변[0][2][1], 주변[-1][2][3]
    sm = geo['sm'][열]
    이웃글 = [z[0] for z in 주변[:앞수] + 주변[앞수 + 칸수:]]
    for 촘촘 in (False, True):
        pts = (list(range(y0 + 1, y1, max(1, (y1 - y0 + 1023) // 1024))) if 촘촘
               else scan.cut_points(sm, y0, y1, geo['pitch']))
        cuts, _ = scan.split_column(sm, y0, y1, len(이웃글), pts)
        if not cuts:
            continue
        boxes = [(x0, s, x1, e) for s, e in zip(cuts[:-1], cuts[1:])]
        L, V, T, cf = mdl.read(geo['image'], align._맞춤상자(g, boxes, geo))
        글 = [_글자(mdl.letter(l, v, t)) for l, v, t in zip(L, V, T)]
        if 글 == 이웃글 and min(cf) >= 0.8:
            return None                       # 더 적은 칸으로도 전사문이 맞으면 불확실
    return min(확인들)


def _한글(c):
    return any(0xAC00 <= ord(ch) <= 0xD7A3 or 0x1100 <= ord(ch) <= 0x11FF for ch in c)


def _다시읽기(mdl, geo, 열, y0, y1, 칸수, 촘촘):
    """열의 y0~y1 을 잉크만으로 칸수만큼 잘라 읽는다 → (글자들, 확신들) 또는 None."""
    x0, x1 = geo['crop_cols'][열]
    sm = geo['sm'][열]
    pts = (list(range(y0 + 1, y1, max(1, (y1 - y0 + 1023) // 1024))) if 촘촘
           else scan.cut_points(sm, y0, y1, geo['pitch']))
    cuts, _ = scan.split_column(sm, y0, y1, 칸수, pts)
    if not cuts:
        return None
    boxes = [(x0, s, x1, e) for s, e in zip(cuts[:-1], cuts[1:])]
    L, V, T, cf = mdl.read(geo['image'], align._맞춤상자(align.잉크판(geo), boxes, geo))
    return [_글자(mdl.letter(l, v, t)) for l, v, t in zip(L, V, T)], [float(v) for v in cf], boxes


열끝높이 = (0.75, 1.25)   # 열 머리 · 끝 칸의 높이가 그 열 가운데 높이의 이 범위를 벗어나면(합친 칸 · 잘린 칸) 그 자리 글자 수 후보를 버린다
열끝잉크 = 0.45           # 열 머리 · 끝 칸 바깥 한 자간에 열 폭의 이만큼 넘는 잉크(가로줄 빼고)가 있으면 읽기가 글자를 놓친 것으로 본다


def _바깥글자(geo, g, 상자, 위):
    """열 머리(위=True) · 끝 칸 바깥 한 자간 안에 글자만 한 잉크가 있는가 — 가로줄은 빼고 본다."""
    x0, y0, x1, y1 = [int(v) for v in 상자[:4]]
    자간 = max(1, int(round(geo['pitch'])))
    ya, yb = (max(0, y0 - 자간), y0) if 위 else (y1, min(g.shape[0], y1 + 자간))
    c = g[ya:yb, x0:x1] < scan.INK
    if c.size == 0:
        return False
    c = c[c.mean(axis=1) < 0.6]
    return bool(c.size) and c.any(axis=0).mean() >= 열끝잉크 and c.any(axis=1).sum() >= 0.3 * 자간


def _열끝성함(geo, 읽음, 앞끝, 뒤머리):
    """열이 바뀌는 자리(읽음[앞끝] | 읽음[뒤머리])의 두 칸이 제 높이이고 그 바깥에 놓친 글자가 없는가."""
    g = align.잉크판(geo)
    for k, 위 in ((앞끝, False), (뒤머리, True)):
        높이 = [z[2][3] - z[2][1] for z in 읽음 if z[3] == 읽음[k][3]]
        비 = (읽음[k][2][3] - 읽음[k][2][1]) / max(1.0, float(np.median(높이)))
        if not 열끝높이[0] <= 비 <= 열끝높이[1] or _바깥글자(geo, g, 읽음[k][2], 위):
            return False
    return True


def 글자수후보(mdl, geo, 글자들, raw, 전사, 읽음, ops):
    """전사문 1~3글자 자리에 스캔은 다른 수(0~3)의 글자 — 앞뒤가 맞고, 다시 잘라도 같고, 전사문 칸수로는 안 읽힐 때만. 열 머리 · 끝은 `_열끝성함` 까지."""
    후보 = []
    for i, (tag, a, b, c, d) in enumerate(ops):
        n전, n읽 = b - a, d - c
        if tag not in ('delete', 'replace') or n전 == n읽 or not 1 <= n전 <= 3 or n읽 > 3:
            continue
        if not 0 < i < len(ops) - 1:
            continue
        앞, 뒤 = ops[i - 1], ops[i + 1]
        if 앞[0] != 'equal' or 앞[2] - 앞[1] < 3 or 뒤[0] != 'equal' or 뒤[2] - 뒤[1] < 3:
            continue
        if any(g[3] for g in 글자들[a - 3:b + 3]):
            continue
        틈 = raw[글자들[a - 1][2]:글자들[a][1]] + raw[글자들[b - 1][2]:글자들[b][1]]
        if (any(ch in 틈 for ch in "<>{|")
                or "".join(raw[글자들[a][1]:글자들[b - 1][2]].split()) != "".join(g[0] for g in 글자들[a:b])):
            continue                           # 각주 · 틀이 시작되거나 낀 자리는 내지 않음
        if min(z[1] for z in 읽음[c - 3:d + 3]) < 0.8:
            continue
        스캔 = 읽음[c:d]
        if any(z[1] < 0.90 or not _한글(z[0]) for z in 스캔) or any(not _한글(t) for t in 전사[a:b]):
            continue
        # 같은 열끼리 묶어 따로 확인 — (읽음 구간, 그 구간에 전사문대로라면 있을 글자들)
        열 = 읽음[c][3]
        if any(z[3] != 열 for z in 스캔):
            continue
        머리, 끝 = 읽음[c - 1][3] != 열, d > c and 읽음[d][3] != 열
        if 머리 and 끝:
            continue
        왼, 오른 = c, d
        while 왼 > c - 3 and 읽음[왼 - 1][3] == 열:
            왼 -= 1
        while 오른 < d + 3 and 읽음[오른][3] == 열:
            오른 += 1
        if (c - 왼) + (오른 - d) < 3:
            continue
        묶음 = [(왼, 오른, 전사[a - (c - 왼):b + (오른 - d)])]
        if 머리 or 끝:                           # 열 머리 · 끝 — 읽기가 글자를 놓치거나 합친 흔적이 없을 때만
            경계 = c if 머리 else d
            if min(z[1] for z in 읽음[c - 3:d + 3]) < 0.93 or not _열끝성함(geo, 읽음, 경계 - 1, 경계):
                continue
            if 머리 and not 스캔:                # 덧글자가 앞 열 끝에 있었을 수도 — 앞 열 쪽도 확인
                if len({z[3] for z in 읽음[c - 3:c]}) != 1:
                    continue
                묶음.insert(0, (c - 3, c, 전사[a - 3:b]))
        확인값, 탈락 = [], False
        for 시, 끝, 전사글 in 묶음:
            열 = 읽음[시][3]
            y0, y1 = 읽음[시][2][1], 읽음[끝 - 1][2][3]
            읽은글 = [z[0] for z in 읽음[시:끝]]
            확인 = None
            for 촘촘 in (False, True):
                r = _다시읽기(mdl, geo, 열, y0, y1, len(읽은글), 촘촘)
                if r is not None and r[0] == 읽은글 and min(r[1]) >= 0.8:
                    높이 = [e - s0 for _, s0, _, e in r[2]]
                    mid = max(1.0, float(np.median(높이)))
                    if all(mid * 0.55 <= h <= mid * 1.7 for h in 높이):
                        확인 = min(r[1]) if 확인 is None else max(확인, min(r[1]))
                r = _다시읽기(mdl, geo, 열, y0, y1, len(전사글), 촘촘)
                if r is not None and r[0] == 전사글 and min(r[1]) >= 0.8:
                    탈락 = True
            if 확인 is None:
                탈락 = True
            확인값.append(확인)
        if 탈락:
            continue
        확인 = min(확인값)
        열 = 읽음[c][3] if not 스캔 else 스캔[0][3]
        x0, x1 = geo['crop_cols'][열]
        box = (x0, 스캔[0][2][1], x1, 스캔[-1][2][3]) if 스캔 else 읽음[c][2]
        후보.append(dict(갈래='글자수', 번호=a, 끝번호=b - 1, 전사=''.join(g[0] for g in 글자들[a:b]),
                         스캔=''.join(z[0] for z in 스캔), 칸=n읽, 전사확률=0.0,
                         확신=float(min([확인] + [z[1] for z in 스캔])), 점수=float(abs(n전 - n읽)), 합의=True,
                         누락상자=box, 누락이웃=[읽음[c - 1][2], box, 읽음[d][2]]))
    return 후보


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
        if tag != 'insert' or not 1 <= d - c <= 3:
            continue
        앞 = ops[i - 1] if i else None
        뒤 = ops[i + 1] if i + 1 < len(ops) else None
        if (앞 is not None and (앞[0] != 'equal' or 앞[2] - 앞[1] < 3)
                or 뒤 is not None and (뒤[0] != 'equal' or 뒤[2] - 뒤[1] < 3)):
            continue
        if any(g[3] for g in 글자들[max(0, a - 3):a + 3]):
            continue                           # SIC/의도적 원문 오식 주변은 제외
        원문앞 = 글자들[a - 1][2] if a else 0
        원문뒤 = 글자들[a][1] if a < len(글자들) else len(raw)
        if raw[원문앞:원문뒤].strip():
            continue                           # 걷어낸 틀/태그 안 글자를 누락으로 복원하지 않음
        열 = 읽음[c][3]
        if any(z[3] != 열 for z in 읽음[c:d]):
            continue                           # 누락 자체가 열을 건너면 보류
        첫 = c == 0 or 읽음[c - 1][3] != 열
        마지막 = d == len(읽음) or 읽음[d][3] != 열
        외끝 = 첫 or 마지막
        if 외끝:
            if 첫 == 마지막:
                continue                       # 열 전체 누락 · 짧은 열은 판단 안 함
            if 첫:
                시작, 끝 = c, d + 6
                if 뒤 is None or 끝 > 뒤[4] or 끝 > len(읽음):
                    continue
            else:
                시작, 끝 = c - 6, d
                if 앞 is None or 시작 < 앞[3]:
                    continue
            if len({z[3] for z in 읽음[시작:끝]}) != 1:
                continue
            if any(g[3] for g in 글자들[a - (c - 시작):a + 끝 - d]):
                continue
            열경계 = True
        else:
            if 앞 is None or 뒤 is None:
                continue
            시작, 끝 = c - 3, d + 3
            열경계 = len({z[3] for z in 읽음[시작:끝]}) != 1
        if 열경계 and not 외끝:
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
        if min(z[1] for z in 주변) < (0.93 if 외끝 else 0.8):
            continue
        빠진 = 읽음[c:d]
        한글 = lambda c: any(0xAC00 <= ord(ch) <= 0xD7A3 or 0x1100 <= ord(ch) <= 0x11FF for ch in c)
        if min(z[1] for z in 빠진) < 0.90 or any(not 한글(z[0]) for z in 빠진):
            continue
        # 누락과 같은 열의 이웃 여섯 글자를 잉크만으로 다시 잘라 확인
        열 = 주변[0][3]
        x0, x1 = geo['crop_cols'][열]
        확인 = (_끝확인(mdl, geo, 주변, c - 시작, d - c) if 외끝
                else _재확인(mdl, geo, 주변, c - 시작, d - c))
        if 확인 is None and 열경계 and not 외끝:
            확인 = _재확인(mdl, geo, 주변, c - 시작, d - c, 촘촘=True)
        if 확인 is None:
            continue
        # 넣을 자리 = 다음 인쇄 글자 앞
        pos = 글자들[a][1] if a < len(글자들) else 글자들[-1][2]
        box = (x0, 빠진[0][2][1], x1, 빠진[-1][2][3])
        # 그림용 — 같은 열의 앞 한 칸 · 누락 칸 · 뒤 한 칸
        이웃 = [box if 첫 else 읽음[c - 1][2], box, box if 마지막 else 읽음[d][2]]
        후보.append(dict(갈래='누락', 번호=a, 전사='', 스캔=''.join(z[0] for z in 빠진),
                         시작=pos, 끝=pos, 칸=d - c, 전사확률=0.0,
                         확신=float(min(min(z[1] for z in 빠진), 확인)),
                         점수=float(d - c), 합의=True, 누락상자=box, 누락이웃=이웃,
                         앞=''.join(g[0] for g in 글자들[max(0, a - 5):a]),
                         뒤=''.join(g[0] for g in 글자들[a:a + 5])))
    return 후보 + (글자수후보(mdl, geo, 글자들, raw, 전사, 읽음, ops) if 글자수찾기 else [])
