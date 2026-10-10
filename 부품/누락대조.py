"""전사문과 독립적으로 읽은 스캔에서, 앞뒤가 맞는 1~3글자 누락만 찾는다.

기존 전사 글자 수에 맞춘 정렬의 밀림 후보와 별개. 본문 중간만 검사하고,
같은 열의 앞뒤 세 글자와 높은 확신, 잉크로 다시 자른 결과까지 확인한다.
"""
import difflib
import unicodedata
import numpy as np
import align
import scan


def 후보찾기(mdl, geo, 글자들, raw):
    norm = lambda c: unicodedata.normalize('NFC', c)
    전사 = [norm(g[0]) for g in 글자들]
    읽음 = []
    for 열, z in enumerate(align.열마다읽기(mdl, geo)):
        if z is not None:
            읽음.extend((norm(c), float(p), b, 열) for c, p, b in zip(z[1], z[2], z[3])
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
        주변 = 읽음[c - 3:d + 3]
        if len({z[3] for z in 주변}) != 1 or min(z[1] for z in 주변) < 0.8:
            continue                           # 열 경계/낮은 확신은 판단을 보류
        빠진 = 읽음[c:d]
        한글 = lambda c: any(0xAC00 <= ord(ch) <= 0xD7A3 or 0x1100 <= ord(ch) <= 0x11FF for ch in c)
        if min(z[1] for z in 빠진) < 0.90 or any(not 한글(z[0]) for z in 빠진):
            continue
        # 누락을 포함한 같은 열의 7~9칸을 잉크만으로 다시 잘라 확인한다.
        # 첫 독립 읽기는 경계 검출기를 쓰므로 자르기 오류의 두 번째 근거가 된다.
        열 = 주변[0][3]
        x0, x1 = geo['crop_cols'][열]
        y0, y1 = 주변[0][2][1], 주변[-1][2][3]
        sm = geo['sm'][열]
        pts = scan.cut_points(sm, y0, y1, geo['pitch'])
        cuts, _ = scan.split_column(sm, y0, y1, len(주변), pts)
        if not cuts:
            continue
        boxes = [(x0, s, x1, e) for s, e in zip(cuts[:-1], cuts[1:])]
        heights = [e - s for _, s, _, e in boxes]
        mid = max(1.0, float(np.median(heights)))
        if any(h < mid * 0.55 or h > mid * 1.7 for h in heights):
            continue
        L, V, T, cf = mdl.read(geo['image'], align._맞춤상자(np.asarray(geo['image']), boxes, geo))
        if [norm(mdl.letter(l, v, t)) for l, v, t in zip(L, V, T)] != [z[0] for z in 주변]:
            continue
        if min(cf) < 0.8 or min(cf[3:3 + d - c]) < 0.90:
            continue
        # 삽입할 위치는 다음 인쇄 글자 앞. 기존 글자를 바꾸는 후보와 구분한다.
        pos = 글자들[a][1]
        box = (x0, 빠진[0][2][1], x1, 빠진[-1][2][3])
        후보.append(dict(갈래='누락', 번호=a, 전사='', 스캔=''.join(z[0] for z in 빠진),
                         시작=pos, 끝=pos, 칸=d - c, 전사확률=0.0,
                         확신=float(min(min(z[1] for z in 빠진), min(cf[3:3 + d - c]))),
                         점수=float(d - c), 합의=True, 누락상자=box,
                         앞=''.join(g[0] for g in 글자들[max(0, a - 5):a]),
                         뒤=''.join(g[0] for g in 글자들[a:a + 5])))
    return 후보
