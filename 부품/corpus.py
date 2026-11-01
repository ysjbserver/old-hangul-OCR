# -*- coding: utf-8 -*-
"""
자료 쪽 — 내려받은 문헌 폴더와 교정 기록을 다루는 잔심부름.

    data/<문헌>/img/0123.jpg     스캔
    data/<문헌>/text/0123.txt    위키문헌 전사문
    교정/<문헌>_0123.json        사람이 확인·교정한 결과
    교정/_확인.json              쪽마다 확인 여부
    교정/_일치.json              쪽마다 모델과 전사문이 얼마나 맞았는지
"""
import glob, json, os, threading, time
from contextlib import contextmanager

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
    [(문헌, 쪽, 이미지경로), …] — 전사문이 없는 쪽도(`pages()` 는 있는 쪽만).
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
    쓸 수 있는(자를 수 있는) 쪽만 남긴다. 검사 결과는 파일에 남겨 다시 쓴다.
    반환: (쓸 수 있는 쪽 목록, 뺀 쪽 수)
    """
    known = _read_json(SCAN, {})
    todo = [t for t in items if f"{t[0]}_{t[1]}" not in known]
    if todo:
        print(f"쓸 수 있는 쪽을 검사합니다… ({len(todo)}쪽, 처음 한 번만 걸립니다)")
        새 = {}
        for k, t in enumerate(todo, 1):
            try:
                새[f"{t[0]}_{t[1]}"] = bool(check(t[2], t[3]))
            except Exception:
                새[f"{t[0]}_{t[1]}"] = False
            if k % 25 == 0 or k == len(todo):
                print(f"   {k}/{len(todo)}쪽")
        known = _고치기(SCAN, {}, lambda d: d.update(새))      # 그사이 남이 적은 것도 살림
    ok = [t for t in items if known.get(f"{t[0]}_{t[1]}")]
    return ok, len(items) - len(ok)


def unusable():
    """못 쓰는 쪽으로 적어 둔 것들의 '문헌_쪽' 이름. 추천이 이 쪽들을 뺀다."""
    return {k for k, v in _read_json(SCAN, {}).items() if not v}


def mark_unusable(slug, page):
    """열어 봤더니 못 쓰는 쪽이었을 때. 다음부터 목록에 나오지 않는다."""
    _고치기(SCAN, {}, lambda d: d.__setitem__(f"{slug}_{page}", False))


# ── 교정 기록 ────────────────────────────────────────────────────────
def _read_json(path, default, 엄격=False):
    """엄격=True 면 깨진 파일을 default 로 치지 않고 오류(고쳐 쓰다 기록을 지우지 않게)."""
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        if 엄격:
            raise RuntimeError(f"{path} 를 읽지 못했습니다(깨진 JSON) — 덮어쓰지 않습니다. 파일을 살펴 고쳐 주세요.")
        return default


def _write_json(path, obj):
    """임시 파일에 다 쓴 뒤 바꿔치기 — 읽는 쪽이 반쯤 쓴 파일을 보지 않게."""
    os.makedirs(FIXDIR, exist_ok=True)
    임시 = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
    with open(임시, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    for _ in range(50):
        try:
            os.replace(임시, path); return
        except PermissionError:                  # Windows: 누가 막 읽는 중
            time.sleep(0.1)
    os.replace(임시, path)


_스레드잠금 = threading.RLock()
_잠근수 = 0


@contextmanager
def _기록잠금():
    """교정 기록 고치기를 한 번에 하나만 — 스레드 · 프로세스 사이(`교정/_잠금` 파일). 같은 스레드는 겹쳐 잠가도 됨."""
    global _잠근수
    with _스레드잠금:
        if _잠근수:
            _잠근수 += 1
            try:
                yield
            finally:
                _잠근수 -= 1
            return
        os.makedirs(FIXDIR, exist_ok=True)
        fd = os.open(os.path.join(FIXDIR, "_잠금"), os.O_RDWR | os.O_CREAT)
        try:
            if os.name == "nt":
                import msvcrt
                for _ in range(600):
                    try:
                        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1); break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("교정 기록 잠금을 1분 동안 얻지 못했습니다")
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX)
            _잠근수 = 1
            try:
                yield
            finally:
                _잠근수 = 0
                if os.name == "nt":
                    os.lseek(fd, 0, 0)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)


def _고치기(path, default, 고침):
    """읽기 → 고침(d) → 쓰기를 잠근 채 한 번에. 고친 d 를 돌려줌."""
    with _기록잠금():
        d = _read_json(path, default, 엄격=True)
        고침(d)
        _write_json(path, d)
        return d


def fix_path(slug, page):
    return os.path.join(FIXDIR, f"{slug}_{page}.json")


def 제자리만(옛, 새):
    """같은 길이 두 글자열의 차이가 제자리 바꿔치기뿐인가 — 편집 거리가 자리마다 다른 수와 같으면 글자 번호가 안 밀림."""
    if len(옛) != len(새):
        return False
    다른 = sum(a != b for a, b in zip(옛, 새))
    if not 다른:
        return True
    앞 = list(range(len(새) + 1))
    for i, a in enumerate(옛, 1):
        지금 = [i]
        for j, b in enumerate(새, 1):
            지금.append(min(앞[j] + 1, 지금[j - 1] + 1, 앞[j - 1] + (a != b)))
        앞 = 지금
    return 앞[-1] == 다른


def fix_matches(d, nchars, letters=None):
    """교정 d 가 지금 전사문에 맞나. 교정 때 글자열(`letters`)이 적혀 있으면 그것과 견줌
    (지우기 + 더하기로 길이만 같아진 것은 안 맞음) · 없으면(옛 교정) 글자 수만."""
    if d.get("nchars") != nchars:
        return False
    if letters is None or d.get("letters") is None:
        return True
    return 제자리만(list(d["letters"]), list(letters))


def load_fix(slug, page, nchars, letters=None):
    """
    저장해 둔 교정. 지금 전사문과 안 맞으면(글자 번호가 밀림 — `fix_matches`) None.
    """
    d = _read_json(fix_path(slug, page), None)
    if not d or not d.get("assign"):
        return None
    if not fix_matches(d, nchars, letters):
        return None
    return d


def save_fix(d, boxes=None, letters=None):
    """boxes = 교정할 때 본 상자들(나중에 상자가 바뀌었는지 가리려고 함께 적음) · letters = 그때 전사 글자열."""
    if boxes is not None:
        d = dict(d, boxes=[[int(v) for v in b] for b in boxes])
    if letters is not None:
        d = dict(d, letters=list(letters))
    _write_json(fix_path(d["slug"], d["page"]), d)


BOX_TOL = 2     # 상자 좌표가 이만큼(px) 안에서만 달라졌으면 같은 상자로 본다


def same_boxes(saved, boxes, tol=BOX_TOL):
    """
    교정할 때 본 상자(saved)와 지금 상자(boxes)가 같은가(좌표 차이 tol px 안).
    좌표가 없는 교정(saved=None)은 다르다고 봄.
    """
    if not saved or len(saved) != len(boxes):
        return False
    return all(abs(int(a) - int(b)) <= tol for s, c in zip(saved, boxes) for a, b in zip(s, c))


def read_state():
    return _read_json(STATE, {})


def mark_verified(slug, page, ok=True):
    _고치기(STATE, {}, lambda st: st.__setitem__(f"{slug}_{page}", "ok" if ok else ""))


def doc_ratio(slug, default=None):
    """그 문헌의 세로/가로 자간 비율. 재 둔 것이 없으면 default."""
    return _read_json(RATIO, {}).get(slug, default)


def save_ratio(slug, r):
    _고치기(RATIO, {}, lambda d: d.__setitem__(slug, round(float(r), 4)))


READKEY = "_읽기자간"      # 전사문 없이 읽을 때만 쓰는 자간


def read_ratio(slug, default=None):
    """
    전사문 없이 읽을 때만 쓰는 자간. 없으면 default.
    """
    return _read_json(RATIO, {}).get(READKEY, {}).get(slug, default)


def save_read_ratio(slug, r):
    _고치기(RATIO, {}, lambda d: d.setdefault(READKEY, {}).__setitem__(slug, round(float(r), 4)))


LAYOUT = os.path.join(FIXDIR, "_판짜임.json")   # 문헌의 표준 판짜임 (자간·열수)


def doc_layout(slug, default=None):
    """
    그 문헌의 표준 판짜임 {"자간": px, "열수": n}. 없으면 default. `page.쪽건강` 이 씀.
    """
    v = _read_json(LAYOUT, {}).get(slug)
    return v if v else default


def save_layout(slug, 자간, 열수):
    _고치기(LAYOUT, {}, lambda d: d.__setitem__(slug, {"자간": round(float(자간), 1), "열수": int(열수)}))


HEADING = os.path.join(FIXDIR, "_제목.json")   # 편·장 제목이 종이에 인쇄되는가


def heading_printed(slug, default=False):
    """
    이 문헌은 `== 제목 ==` 이 본문 열에 인쇄되어 있는가(`wikitext.printed_text`).
    """
    return bool(_read_json(HEADING, {}).get(slug, default))


def save_heading_printed(slug, v):
    _고치기(HEADING, {}, lambda d: d.__setitem__(slug, bool(v)))


TIERS = os.path.join(FIXDIR, "_판형.json")     # 한 쪽이 몇 단인가 (거의 다 1단)


def doc_tiers(slug, default=None):
    """
    이 문헌은 한 쪽이 몇 단인가(보통 1). 없으면 default.
    가름줄 판형이면 가름줄 높이 목록(쪽 높이 비율). ⚠ 쪽마다가 아니라 문헌마다 한 번만 정할 것.
    """
    v = _read_json(TIERS, {}).get(slug, default)
    if isinstance(v, list):
        return tuple(v)
    return int(v) if v else default


def save_tiers(slug, n):
    v = [float(x) for x in n] if isinstance(n, (list, tuple)) else int(n)
    _고치기(TIERS, {}, lambda d: d.__setitem__(slug, v))


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
    _고치기(HELD, {}, lambda d: d.__setitem__(slug, sorted(pages)))


def slug_of(path):
    """data/<문헌>/img/0001.jpg 처럼 생긴 경로에서 문헌 이름만."""
    parts = os.path.normpath(path).split(os.sep)
    return parts[parts.index("data") + 1] if "data" in parts else ""


def read_rates():
    return _read_json(RATES, {})


def save_rate(slug, page, rate):
    _고치기(RATES, {}, lambda r: r.__setitem__(f"{slug}_{page}", round(float(rate), 3)))
