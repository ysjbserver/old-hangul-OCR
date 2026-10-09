# -*- coding: utf-8 -*-
"""
자료 쪽 — 내려받은 문헌 폴더와 교정 기록을 다루는 잔심부름.

    data/<문헌>/img/0123.jpg     스캔
    data/<문헌>/text/0123.txt    위키문헌 전사문
    교정/<문헌>_0123.json        사람이 확인·교정한 결과
    교정/_확인.json              쪽마다 확인 여부
    교정/_일치.json              쪽마다 모델과 전사문이 얼마나 맞았는지
"""
import glob, json, os

import 경로

FIXDIR = 경로.교정
STATE = os.path.join(FIXDIR, "_확인.json")
RATES = os.path.join(FIXDIR, "_일치.json")
SCAN = os.path.join(FIXDIR, "_쪽목록.json")    # 쓸 수 있는 쪽인지 한 번 검사해 두고 재사용
RATIO = os.path.join(FIXDIR, "_자간.json")      # 문헌마다 세로/가로 자간 비율


def documents(only=None):
    out = []
    for idir in sorted(glob.glob(os.path.join(경로.데이터, "*", "img"))):
        slug = os.path.basename(os.path.dirname(idir))
        if only and slug != only:
            continue
        out.append((slug, idir, os.path.join(경로.데이터, slug, "text")))
    return out


def images(only=None):
    """
    [(문헌, 쪽, 이미지경로), …] — 전사문이 없어도 그림이 있으면 다 준다
    (`pages()` 는 전사문 있는 쪽만). 전사문 없이 읽기 · `page.doc_*` 이 씀.
    """
    out = []
    for slug, idir, _ in documents(only):
        for ip in sorted(glob.glob(os.path.join(idir, "*.jpg"))):
            out.append((slug, os.path.basename(ip)[:-4], ip))
    return out


def pages(only=None, verified_only=False):
    """[(문헌, 쪽, 이미지경로, 전사문경로), …] — 전사문이 있는 쪽만."""
    st = read_state() if verified_only else {}
    out = []
    for slug, idir, tdir in documents(only):
        for ip in sorted(glob.glob(os.path.join(idir, "*.jpg"))):
            page = os.path.basename(ip)[:-4]
            tp = os.path.join(tdir, page + ".txt")
            if not os.path.exists(tp):
                continue
            if verified_only and st.get(f"{slug}_{page}") != "ok":
                continue
            out.append((slug, page, ip, tp))
    return out


def sample(items, n):
    """앞쪽만 보지 않도록 문헌 전체에 고르게 n 개를 뽑는다."""
    if n <= 0 or len(items) <= n:
        return items
    step = max(1, len(items) // n)
    return items[::step][:n]


def usable_pages(items, check):
    """
    쓸 수 있는 쪽만 남긴다. 자르지 못하는 쪽이 목록에 섞여 있으면
    ← → 로 넘기다 막혀서 일이 안 된다. 한 번 검사한 결과는 파일에 남겨 다시 쓴다.
    반환: (쓸 수 있는 쪽 목록, 뺀 쪽 수)
    """
    known = _read_json(SCAN, {})
    todo = [t for t in items if f"{t[0]}_{t[1]}" not in known]
    if todo:
        print(f"쓸 수 있는 쪽을 검사합니다… ({len(todo)}쪽, 처음 한 번만 걸립니다)")
        for k, t in enumerate(todo, 1):
            try:
                known[f"{t[0]}_{t[1]}"] = bool(check(t[2], t[3]))
            except Exception:
                known[f"{t[0]}_{t[1]}"] = False
            if k % 25 == 0 or k == len(todo):
                print(f"   {k}/{len(todo)}쪽")
        _write_json(SCAN, known)
    ok = [t for t in items if known.get(f"{t[0]}_{t[1]}")]
    return ok, len(items) - len(ok)


def unusable():
    """못 쓰는 쪽으로 적어 둔 것들의 '문헌_쪽' 이름. 추천이 이 쪽들을 뺀다."""
    return {k for k, v in _read_json(SCAN, {}).items() if not v}


def mark_unusable(slug, page):
    """열어 봤더니 못 쓰는 쪽이었을 때. 다음부터 목록에 나오지 않는다."""
    d = _read_json(SCAN, {})
    d[f"{slug}_{page}"] = False
    _write_json(SCAN, d)


# ── 교정 기록 ────────────────────────────────────────────────────────
def _read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, obj):
    os.makedirs(FIXDIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def fix_path(slug, page):
    return os.path.join(FIXDIR, f"{slug}_{page}.json")


def load_fix(slug, page, nchars):
    """
    저장해 둔 교정. 글자 수가 지금과 다르면 못 쓴다 — None 을 준다.
    (전사문이 고쳐졌거나 글자 세는 규칙이 바뀌면 글자 번호가 통째로 밀린다)
    """
    d = _read_json(fix_path(slug, page), None)
    if not d or not d.get("assign"):
        return None
    if d.get("nchars") != nchars:
        return None
    return d


def save_fix(d, boxes=None):
    """boxes = 사람이 그 교정을 할 때 본 상자들. 함께 적어 두어야 나중에 상자가 바뀐 것을 안다."""
    if boxes is not None:
        d = dict(d, boxes=[[int(v) for v in b] for b in boxes])
    _write_json(fix_path(d["slug"], d["page"]), d)


BOX_TOL = 2     # 상자 좌표가 이만큼(px) 안에서만 달라졌으면 같은 상자로 본다


def same_boxes(saved, boxes, tol=BOX_TOL):
    """
    교정을 할 때 본 상자(saved)와 지금 자른 상자(boxes)가 같은가(좌표 차이 tol px 안).
    `assign` 은 '몇 번째 상자 = 몇 번째 글자' 라 상자가 달라지면 뜻이 없음 — 상자 수로는 못 가리므로 좌표로.
    좌표가 없는 교정(saved=None)은 같다고 보지 않는다.
    """
    if not saved or len(saved) != len(boxes):
        return False
    return all(abs(int(a) - int(b)) <= tol for s, c in zip(saved, boxes) for a, b in zip(s, c))


def read_state():
    return _read_json(STATE, {})


def mark_verified(slug, page, ok=True):
    st = read_state()
    st[f"{slug}_{page}"] = "ok" if ok else ""
    _write_json(STATE, st)


def doc_ratio(slug, default=None):
    """그 문헌의 세로/가로 자간 비율. 재 둔 것이 없으면 default."""
    return _read_json(RATIO, {}).get(slug, default)


def save_ratio(slug, r):
    d = _read_json(RATIO, {})
    d[slug] = round(float(r), 4)
    _write_json(RATIO, d)


READKEY = "_읽기자간"      # 전사문 없이 읽을 때만 쓰는 자간 (아래 설명)


def read_ratio(slug, default=None):
    """
    전사문 없이 읽을 때만 쓰는 자간. 없으면 default(보통 자간을 씀).
    자를 때는 전사문이 글자 수를 주지만, 읽을 때는 자간이 몇 칸으로 자를지의 출발점이라 따로 둔다.
    """
    return _read_json(RATIO, {}).get(READKEY, {}).get(slug, default)


def save_read_ratio(slug, r):
    d = _read_json(RATIO, {})
    d.setdefault(READKEY, {})[slug] = round(float(r), 4)
    _write_json(RATIO, d)


LAYOUT = os.path.join(FIXDIR, "_판짜임.json")   # 문헌의 표준 판짜임 (자간·열수)


def doc_layout(slug, default=None):
    """
    그 문헌의 표준 판짜임 {"자간": px, "열수": n}. 없으면 default.
    잘못 잘린 쪽을 가려내는 데 씀(`page.쪽건강`). `page.doc_layout` 이 처음 쓸 때 재서 적어 둔다.
    """
    v = _read_json(LAYOUT, {}).get(slug)
    return v if v else default


def save_layout(slug, 자간, 열수):
    d = _read_json(LAYOUT, {})
    d[slug] = {"자간": round(float(자간), 1), "열수": int(열수)}
    _write_json(LAYOUT, d)


HEADING = os.path.join(FIXDIR, "_제목.json")   # 편·장 제목이 종이에 인쇄되는가


def heading_printed(slug, default=False):
    """
    이 문헌은 `== 제목 ==` 이 본문 열에 인쇄되어 있는가(`wikitext.printed_text`). 기본값은 '인쇄 안 됨'.
    """
    return bool(_read_json(HEADING, {}).get(slug, default))


def save_heading_printed(slug, v):
    d = _read_json(HEADING, {})
    d[slug] = bool(v)
    _write_json(HEADING, d)


TIERS = os.path.join(FIXDIR, "_판형.json")     # 한 쪽이 몇 단인가 (거의 다 1단)


def doc_tiers(slug, default=None):
    """
    이 문헌은 한 쪽이 몇 단인가(보통 1). 적혀 있지 않으면 default(`page.doc_tiers` 가 재서 적어 둠).
    가름줄 판형이면 정수 대신 가름줄 높이 목록(쪽 높이 비율, 예: (0.34, 0.66)).
    ⚠ 쪽마다 판단하지 말 것 — 가로줄이 획·계선과 헷갈려 한 단 문헌을 잘못 쪼갬. 문헌마다 한 번만.
    """
    v = _read_json(TIERS, {}).get(slug, default)
    if isinstance(v, list):
        return tuple(v)
    return int(v) if v else default


def save_tiers(slug, n):
    d = _read_json(TIERS, {})
    d[slug] = [float(x) for x in n] if isinstance(n, (list, tuple)) else int(n)
    _write_json(TIERS, d)


HELD = os.path.join(FIXDIR, "_시험쪽.json")   # 성능을 잴 때만 쓰는 쪽 — 확인하지 말 것


def held_out(slug=None):
    """
    성능을 재려고 떼어 놓은 고정 표본 쪽 — 사람이 확인하면 안 된다.
    반환: slug 를 주면 그 문헌의 쪽 집합, 안 주면 "문헌_쪽" 전체 집합.
    """
    d = _read_json(HELD, {})
    if slug is None:
        return {f"{k}_{p}" for k, v in d.items() for p in v}
    return set(d.get(slug, []))


def save_held_out(slug, pages):
    d = _read_json(HELD, {})
    d[slug] = sorted(pages)
    _write_json(HELD, d)


def slug_of(path):
    """data/<문헌>/img/0001.jpg 처럼 생긴 경로에서 문헌 이름만."""
    parts = os.path.normpath(path).split(os.sep)
    return parts[parts.index("data") + 1] if "data" in parts else ""


def read_rates():
    return _read_json(RATES, {})


def save_rate(slug, page, rate):
    r = read_rates()
    r[f"{slug}_{page}"] = round(float(rate), 3)
    _write_json(RATES, r)
