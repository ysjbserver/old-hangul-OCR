# -*- coding: utf-8 -*-
"""
옛한글 OCR — Toolforge 웹 도구

위키문헌 편집 창의 소도구(OCR · 전사대조)와 영역 지정 화면이 이 서버에 묻는다. 모델은 서버에서 돈다(ONNX · CPU).
셈은 `부품/` 의 파이썬 코드(전사대조는 `대조.py`) 그대로, torch 대신 `onnx모델.py` 를 끼운다.

  ⚠ 원본은 프로젝트의 `근원/툴포지/app.py` — 이 묶음은 만들기 스크립트가 만드는 사본이니 손으로 고치지 말 것.

돌리기
  · Toolforge(빌드 서비스) — `Procfile` 의 gunicorn 이 `app:app` 을 띄움(포트 8000)
  · 내 컴퓨터 — `python old-hangul-ocr-toolforge/app.py` → http://localhost:8761/

주소
  /                       첫 화면(쓰는 법)
  /ocr.js  /소도구.js       OCR 소도구 — 위키문헌 common.js 에서 불러옴(서버 주소를 스스로 채움)
  /compare.js /전사대조.js  전사대조 소도구
  /area/ /영역지정/          영역 지정 화면 (옛 주소 /region/ 은 /area/ 로 넘김)
  GET  /api/inspect?file=     파일의 판형 · 자간비 · 판짜임 (처음 한 번 뒤에서 잼 — 부르는 쪽은 되물음)
  POST /api/read            {file, page}            → OCR 결과(브라우저판 `한쪽` 과 같은 꼴)
  POST /api/compare         {file, page, text}      → 전사대조 결과
  POST /api/boxes           {file, page, boxes}     → 상자마다 글자(영역 지정 화면)
  POST /api/edge            {file, page, x0, x1}    → 열의 글자 경계 확률(영역 지정 화면)
  GET  /api/tables?model=   그 모델의 글자표(영역 지정 화면이 번호를 글자로 바꿈)
  GET  /api/health          모델 · 판 정보
  ★ read · compare · boxes 는 선택 값 둘을 더 받음 — model("hangul" 근대 순한글 · 기본 / "hanmun" 근대 국한문),
    tiers(몇 단짜리인지 — 없으면 "자동": 파일을 살펴 정한 값), spacing(/api/read 만 — false 면 띄어쓰기 자동 감지를 끔)
"""
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
from collections import OrderedDict

여기 = os.path.dirname(os.path.abspath(__file__))
os.chdir(여기)
for p in (여기, os.path.join(여기, "부품")):      # 부품/ — 엔진 · 대조(전사대조) · step1_collect
    if p not in sys.path:
        sys.path.insert(0, p)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import numpy as np
from PIL import Image

import align
import page
import scan
import onnx모델
import step1_collect
from 표시 import 줄글월, 표시문턱
import 대조

정적 = os.path.join(여기, "정적")
스레드 = int(os.environ.get("OCR_THREADS", "1"))
캐시 = os.environ.get("OCR_CACHE") or os.path.join(tempfile.gettempdir(), "oldhangul-ocr")
캐시최대 = int(os.environ.get("OCR_CACHE_FILES", "1500"))     # 스캔 그림을 이만큼 넘게 두지 않음(오래된 것부터 지움)
os.makedirs(캐시, exist_ok=True)

모델 = onnx모델.끼우기(os.path.join(여기, "모델"), 스레드)
너비 = 모델.설정.get("스캔너비", 1920)
계산 = threading.Lock()            # CPU 가 적어 모델 셈은 한 번에 하나씩

# 글자 모델 — "hangul"(근대 순한글, 기본) · "hanmun"(근대 국한문, 있을 때만 · 처음 쓸 때 불러옴 — 메모리를 아끼려고)
모델이름들 = {"hangul": "근대 순한글", "hanmun": "근대 국한문"}
국한문폴더 = os.path.join(여기, "모델", "근대 국한문")      # 모델마다 `모델/<이름>/` 폴더 하나 — 이름은 `모델이름들` 과 같게
_모델들 = {"hangul": 모델}
_모델잠금 = threading.Lock()


def 모델얻기(이름):
    이름 = (이름 or "hangul")
    if 이름 not in 모델이름들:
        raise 손님오류("모르는 모델입니다: " + str(이름))
    with _모델잠금:
        if 이름 not in _모델들:
            if not os.path.exists(os.path.join(국한문폴더, "국한문모델.onnx")):
                raise 손님오류("이 서버에는 국한문 모델이 없습니다")
            _모델들[이름] = onnx모델.혼용모델(국한문폴더, 모델.설정, 스레드)
        return _모델들[이름]


def 단바꾸기(s, 단):
    """파일을 살펴 정한 설정 `s` 에서 단만 사람이 고른 값으로(없거나 "auto" 면 그대로). 1단 = 1, N단 = 가름줄 높이 목록 [1/N …]."""
    if 단 in (None, "", "auto", "자동"):
        return s
    try:
        n = int(단)
    except (TypeError, ValueError):
        raise 손님오류("tiers(몇 단)는 숫자나 auto 여야 합니다")
    if not 1 <= n <= 6:
        raise 손님오류("tiers(몇 단)는 1~6 사이여야 합니다")
    s = dict(s)
    s["단"] = 1 if n == 1 else [k / n for k in range(1, n)]
    return s
판정보 = {}
try:
    with open(os.path.join(여기, "판.json"), encoding="utf-8") as f:
        판정보 = json.load(f)
except Exception:
    pass


# ── 스캔 받기 ────────────────────────────────────────────────────────
# ⚠ 여러 쪽 파일은 API 가 요청한 너비를 무시함 → 주소를 한 번 받아 `/page{쪽}-1920px-` 만 갈아 끼움(`step1_collect.url_pattern` 과 같음)
_파일정보 = {}
_파일잠금 = threading.Lock()


def 파일정보(파일):
    """{여러쪽, 쪽수, 틀(여러 쪽 파일) | 주소(한 장짜리)}"""
    with _파일잠금:
        if 파일 in _파일정보:
            return _파일정보[파일]
    r = step1_collect.api(action="query", prop="imageinfo", titles="File:" + 파일,
                          iiprop="url|size", iiurlwidth=500, iiurlparam="page1-500px")
    ii = (r.get("query", {}).get("pages") or [{}])[0].get("imageinfo")
    if not ii:
        raise 손님오류(f"위키미디어 공용에서 파일을 찾지 못했습니다: {파일}")
    ii = ii[0]
    u = (ii.get("thumburl") or ii.get("url") or "").split("?")[0]
    if "/page1-500px-" in u:
        v = dict(여러쪽=True, 쪽수=ii.get("pagecount") or 0, 틀=u.replace("/page1-500px-", f"/page{{N}}-{너비}px-", 1))
    else:                                       # 한 장짜리 그림 — 1920px 썸네일(원본이 작으면 원본)
        r2 = step1_collect.api(action="query", prop="imageinfo", titles="File:" + 파일, iiprop="url", iiurlwidth=너비)
        ii2 = r2["query"]["pages"][0]["imageinfo"][0]
        v = dict(여러쪽=False, 쪽수=1, 주소=(ii2.get("thumburl") or ii2["url"]).split("?")[0])
    with _파일잠금:
        _파일정보[파일] = v
    return v


def _캐시정리():
    파일들 = []
    for 뿌리, _, 이름들 in os.walk(캐시):
        for n in 이름들:
            if n.endswith((".jpg", ".png")):
                p = os.path.join(뿌리, n)
                파일들.append((os.path.getmtime(p), p))
    if len(파일들) > 캐시최대:
        파일들.sort()
        for _, p in 파일들[:len(파일들) - 캐시최대 + 100]:
            try:
                os.remove(p)
            except OSError:
                pass


def 스캔(파일, 쪽):
    """그 쪽 스캔의 로컬 경로(받아 둠). 1920px."""
    정보 = 파일정보(파일)
    d = os.path.join(캐시, hashlib.sha1(파일.encode("utf-8")).hexdigest()[:16])
    os.makedirs(d, exist_ok=True)
    if 정보["여러쪽"]:
        if 정보["쪽수"] and not (1 <= 쪽 <= 정보["쪽수"]):
            raise 손님오류(f"이 파일은 {정보['쪽수']}쪽까지입니다")
        p = os.path.join(d, f"{쪽:04d}.jpg")
        r = step1_collect.fetch_one(정보["틀"], 쪽, p)
        if r not in ("ok", "skip"):
            raise 손님오류(f"스캔을 받지 못했습니다({r}) — {파일} {쪽}쪽")
    else:
        p = os.path.join(d, "0001.png")
        if not os.path.exists(p):
            im = Image.open(__import__("io").BytesIO(step1_collect._open(정보["주소"]))).convert("L")
            if im.size[0] != 너비:               # ⚠ 브라우저(캔버스)와 늘리는 셈이 달라 결과가 조금 다를 수 있음
                im = im.resize((너비, round(im.size[1] * 너비 / im.size[0])), Image.BICUBIC)
            im.save(p)
    os.utime(p)
    if r_정리.acquire(blocking=False):
        try:
            _캐시정리()
        finally:
            r_정리.release()
    return p


def 진단정보(파일, 쪽, 경로, 결과):
    """전사대조에 사용한 스캔과 서버 판을 재현할 짧은 정보."""
    정보 = 파일정보(파일)
    주소 = 정보["틀"].replace("{N}", str(쪽)) if 정보["여러쪽"] else 정보["주소"]
    with open(경로, "rb") as f:
        그림바이트 = f.read()
    with Image.open(경로) as im:
        크기 = [int(im.width), int(im.height)]
    진단 = {
        "파일": 파일,
        "쪽": int(쪽),
        "주소": 주소,
        "캐시": hashlib.sha256(경로.encode("utf-8")).hexdigest()[:16],
        "크기": 크기,
        "그림해시": hashlib.sha256(그림바이트).hexdigest()[:16],
        "판": 판정보,
    }
    if 결과 and not 결과.get("사유"):
        글자 = 결과.get("스캔글자", [])
        원문 = "".join(글자)
        진단.update({
            "OCR글자수": len(글자),
            "OCR해시": hashlib.sha256(원문.encode("utf-8")).hexdigest()[:16],
            "OCR전체": 원문,
            "상세": 결과.get("진단", {}),
            "시도기록": 결과.get("시도기록", []),
        })
    return 진단


r_정리 = threading.Lock()
_그림들 = OrderedDict()                   # (파일, 쪽) → (PIL 회색 그림, numpy) — 영역 지정이 같은 쪽을 여러 번 물음
_그림잠금 = threading.Lock()


def 그림(파일, 쪽):
    열쇠 = (파일, 쪽)
    with _그림잠금:
        if 열쇠 in _그림들:
            _그림들.move_to_end(열쇠)
            return _그림들[열쇠]
    im = Image.open(스캔(파일, 쪽)).convert("L")
    v = (im, np.asarray(im))
    with _그림잠금:
        _그림들[열쇠] = v
        while len(_그림들) > 6:
            _그림들.popitem(last=False)
    return v


# ── 파일마다 처음 한 번 — 판형 · 자간비 · 판짜임 (`읽기.js` 의 `판형살피기` 와 같은 셈) ─────
설정파일 = os.path.join(캐시, "_파일설정.json")
판형판 = 4                               # 판정 규칙을 바꾸면 올림(기억한 값을 버림) — `읽기.js` 의 `판형판` 과 같은 뜻
_살핀 = {}
_살핌일 = {}                              # 파일 → {진행, 오류}
_살핌잠금 = threading.Lock()
try:
    with open(설정파일, encoding="utf-8") as f:
        v = json.load(f)
    if v.get("판") == 판형판:
        _살핀.update(v.get("값", {}))
except Exception:
    pass


def 고르게쪽(n, k):
    쪽들 = list(range(1, n + 1))
    if k <= 0 or n <= k:
        return 쪽들
    step = max(1, n // k)
    return [쪽들[j] for j in range(0, n, step)][:k]


def _살피기(파일):
    try:
        정보 = 파일정보(파일)
        n = 정보["쪽수"] if 정보["여러쪽"] else 0
        if not n:
            값 = {"단": 1}
        else:
            가름쪽, 단쪽 = 고르게쪽(n, 12), 고르게쪽(n, 8)
            모두 = 가름쪽 + [p for p in 단쪽 if p not in 가름쪽]
            가름, 단, 길, 짜임 = {}, {}, {}, []
            for i, p in enumerate(모두):
                _살핌일[파일]["진행"] = f"{i + 1}/{len(모두)}쪽"
                try:
                    ip = 스캔(파일, p)
                    if p in 가름쪽:
                        가름[p] = scan.가름줄측정(ip)
                    if p in 단쪽:
                        단[p] = scan.tier_measure(ip)
                        길[p] = ip
                    g = np.array(Image.open(ip).convert("L"))
                    xp, cols = scan.find_columns(g)
                    짜임.append((xp, len(cols)) if xp and cols else None)
                except 손님오류:
                    raise
                except Exception:
                    traceback.print_exc()
                    가름[p] = None
                    단[p] = None
            판형, _ = page.판형정하기([가름.get(p) for p in 가름쪽], [단.get(p) for p in 단쪽])
            _살핌일[파일]["진행"] = "자간 재는 중"
            잰 = []
            for p in 단쪽:
                try:
                    잰.append(scan.page_ratio(길[p], 단=판형) if p in 길 else None)
                except Exception:
                    잰.append(None)
            잰 = [v for v in 잰 if v]
            값 = {"단": list(판형) if isinstance(판형, (list, tuple)) else 판형}
            if 잰:
                값["자간비"] = float(np.median(잰))
            짜 = page.판짜임정하기(짜임)
            if 짜:
                값["판짜임"] = 짜
        with _살핌잠금:
            _살핀[파일] = 값
            _살핌일.pop(파일, None)
            with open(설정파일 + ".새", "w", encoding="utf-8") as f:
                json.dump({"판": 판형판, "값": _살핀}, f, ensure_ascii=False)
            os.replace(설정파일 + ".새", 설정파일)
    except Exception as e:
        traceback.print_exc()
        with _살핌잠금:
            _살핌일[파일] = {"진행": "", "오류": str(e)}


def 살핌상태(파일):
    """{상태: 끝, 값} · {상태: 진행, 진행} · {상태: 오류, 오류}. 처음 부르면 뒤에서 살피기를 시작."""
    with _살핌잠금:
        if 파일 in _살핀:
            return {"상태": "끝", "값": _살핀[파일]}
        일 = _살핌일.get(파일)
        if 일 and 일.get("오류"):
            _살핌일.pop(파일, None)             # 다음에 다시 해 봄
            return {"상태": "오류", "오류": 일["오류"]}
        if 일 is None:
            _살핌일[파일] = {"진행": "시작"}
            threading.Thread(target=_살피기, args=(파일,), daemon=True).start()
        return {"상태": "진행", "진행": _살핌일[파일]["진행"]}


def 살핀값(파일):
    s = 살핌상태(파일)
    if s["상태"] != "끝":
        raise 손님오류("이 파일의 판형을 아직 살피는 중입니다 — /api/inspect 로 끝난 뒤에 다시", 409, s)
    return s["값"]


# ── 일 ───────────────────────────────────────────────────────────────
class 손님오류(Exception):
    def __init__(self, 글, 코드=400, 덧=None):
        super().__init__(글)
        self.코드, self.덧 = 코드, 덧 or {}


def 읽기(파일, 쪽, 문턱=표시문턱, 모델이름=None, 단=None, 띄움=True):
    """OCR 한 쪽 — 브라우저판 `읽기.js` 의 `한쪽` 과 같은 셈(파이썬 정본으로)."""
    s = 단바꾸기(살핀값(파일), 단)
    모델 = 모델얻기(모델이름)
    ip = 스캔(파일, 쪽)
    t0 = time.time()
    단 = s.get("단") or 1
    단 = tuple(단) if isinstance(단, list) else 단
    r = s.get("읽기자간비") or s.get("자간비") or scan.YX_RATIO
    표준 = s["판짜임"]["자간"] if s.get("판짜임") and page.SCAN_PITCH else None
    with 계산:
        geo = scan.page_geometry(ip, r, 단, 읽기=True, 가장자리=True, 표준자간=표준)
        등급, 까닭 = page.쪽건강(None, geo, 표준=s.get("판짜임"))
        줄들 = align.read_page_lines(모델, geo, 3, 띄움=align.SPACE and 띄움) if geo is not None else []
    n = sum(len(z[0]) for z in 줄들)
    if not n:
        return dict(판정=dict(등급="못씀" if geo is None else 등급, 까닭=까닭 or ["읽어 내지 못했습니다"]),
                    글월="", 교정용="", 표시비=0, 상자수=0, 살핀=s, 초=round(time.time() - t0, 1))
    글월, 교정용, 셀 = 줄글월(줄들, 문턱)
    return dict(판정=dict(등급=등급, 까닭=까닭), 글월=글월, 교정용=교정용, 표시비=셀 / n, 상자수=n, 글자수=n,
                살핀=s, 초=round(time.time() - t0, 1))


def 맞대기(파일, 쪽, 본문, 모델이름=None, 단=None):
    """전사대조 한 쪽 (파일마다 잰 설정으로)."""
    s = 단바꾸기(살핀값(파일), 단)
    모델 = 모델얻기(모델이름)
    ip = 스캔(파일, 쪽)
    t0 = time.time()
    with 계산:
        r = 대조.한쪽(모델, None, ip, 본문, 설정=s)
    답 = dict(사유=r.get("사유"), 아는문헌=True, 초=round(time.time() - t0, 1))
    답["debug"] = 진단정보(파일, 쪽, ip, r)
    if not r.get("사유"):
        # 원문 자리를 자바스크립트 문자열 자리(UTF-16)로 — 한자 확장 B 처럼 BMP 밖 글자가 있으면 파이썬 자리와 갈림
        if any(ord(ch) > 0xFFFF for ch in 본문):
            앞 = [0]
            for ch in 본문:
                앞.append(앞[-1] + (2 if ord(ch) > 0xFFFF else 1))
            for c in r["후보"]:
                c["시작"], c["끝"] = 앞[c["시작"]], 앞[c["끝"]]
        답.update(일치=r["일치"], 흔들림=r["흔들림"], 흔들린열=r["흔들린열"], 기하=r["기하"], 제목=r["제목"],
                 글자수=r["글자수"], 시도기록=r.get("시도기록", []), 진단=r.get("진단", {}),
                 후보=[{k: v for k, v in c.items()} for c in r["후보"]])
    return 답


def 상자읽기(파일, 쪽, 상자들, 모델이름=None):
    모델 = 모델얻기(모델이름)
    im, _ = 그림(파일, 쪽)
    with 계산:
        kL, kV, kT, cf = 모델.read(im, [list(map(int, b)) for b in 상자들])
    return dict(초=[int(v) for v in kL], 중=[int(v) for v in kV], 종=[int(v) for v in kT], 확신=[float(v) for v in cf])


def 경계읽기(파일, 쪽, x0, x1):
    _, g = 그림(파일, 쪽)
    with 계산:
        p = align._검출기.경계확률(g, x0, x1)
    return dict(확률=[float(v) for v in p], 높이=int(g.shape[0]))


# ── WSGI ─────────────────────────────────────────────────────────────
def _json기본(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(type(o))


공통머리 = [("Access-Control-Allow-Origin", "*"),
           ("Access-Control-Allow-Methods", "GET, POST, OPTIONS"),
           ("Access-Control-Allow-Headers", "Content-Type")]

갈래 = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml", ".txt": "text/plain; charset=utf-8",
        ".md": "text/plain; charset=utf-8", ".onnx": "application/octet-stream"}

# 바깥 주소 → 정적 파일(앞에 서버 주소를 붙여 줄 소도구는 따로)
소도구들 = {"/ocr.js": "소도구.js", "/소도구.js": "소도구.js", "/compare.js": "전사대조.js", "/전사대조.js": "전사대조.js"}
영역길 = ("/area/", "/영역지정/")
옛영역길 = "/region"                 # 옛 주소 — /area/ 로 넘겨 줌(물음표 뒤도 그대로)


def _바탕주소(env):
    if os.environ.get("OCR_BASE"):
        return os.environ["OCR_BASE"].rstrip("/") + "/"
    host = env.get("HTTP_X_FORWARDED_HOST") or env.get("HTTP_HOST") or "localhost"
    proto = env.get("HTTP_X_FORWARDED_PROTO") or ("https" if host.endswith("toolforge.org") else env.get("wsgi.url_scheme", "http"))
    return f"{proto}://{host}/"


def _경로(env):
    p = env.get("PATH_INFO") or "/"
    try:
        p = p.encode("latin-1").decode("utf-8")      # WSGI 는 경로를 latin-1 로 넘김
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return urllib.parse.unquote(p)


def _정적(start, 이름, 앞=b""):
    p = os.path.normpath(os.path.join(정적, 이름))
    if not p.startswith(os.path.normpath(정적) + os.sep) or not os.path.isfile(p):
        return _응답(start, {"오류": "없는 주소"}, 404)
    with open(p, "rb") as f:
        b = 앞 + f.read()
    머리 = 공통머리 + [("Content-Type", 갈래.get(os.path.splitext(p)[1], "application/octet-stream")),
                    ("Content-Length", str(len(b))), ("Cache-Control", "no-cache")]
    start("200 OK", 머리)
    return [b]


def _응답(start, obj, 코드=200):
    b = json.dumps(obj, ensure_ascii=False, default=_json기본).encode("utf-8")
    글 = {200: "200 OK", 400: "400 Bad Request", 404: "404 Not Found", 409: "409 Conflict", 500: "500 Internal Server Error"}
    start(글.get(코드, f"{코드} Error"), 공통머리 + [("Content-Type", "application/json; charset=utf-8"),
                                                ("Content-Length", str(len(b))), ("Cache-Control", "no-store")])
    return [b]


def _몸(env):
    n = int(env.get("CONTENT_LENGTH") or 0)
    if n > 5_000_000:
        raise 손님오류("요청이 너무 큽니다")
    return json.loads(env["wsgi.input"].read(n).decode("utf-8") or "{}") if n else {}


def _파일쪽(q):
    파일 = (q.get("file") or q.get("파일") or "").strip()
    if not 파일:
        raise 손님오류("file(파일 이름)이 없습니다")
    파일 = 파일.replace("_", " ")
    for 머리 in ("File:", "파일:"):
        if 파일.startswith(머리):
            파일 = 파일[len(머리):]
    쪽 = q.get("page") or q.get("쪽") or 1
    try:
        쪽 = int(쪽)
    except (TypeError, ValueError):
        raise 손님오류("page(쪽 번호)가 숫자가 아닙니다")
    return 파일, 쪽


def app(env, start):
    방식 = env.get("REQUEST_METHOD", "GET")
    경로 = _경로(env)
    if 방식 == "OPTIONS":
        start("204 No Content", 공통머리 + [("Access-Control-Max-Age", "86400")])
        return [b""]
    try:
        if 경로 in ("/", "/index.html"):
            return _정적(start, "index.html")
        if 경로 in 소도구들:
            앞 = f'window.옛한글OCR서버 = window.옛한글OCR서버 || "{_바탕주소(env)}";\n'.encode("utf-8")
            return _정적(start, 소도구들[경로], 앞)
        if 경로 == 옛영역길 or 경로.startswith(옛영역길 + "/"):
            새 = "/area/" + 경로[len(옛영역길):].lstrip("/")
            qs = env.get("QUERY_STRING", "")
            start("301 Moved Permanently", [("Location", urllib.parse.quote(새) + ("?" + qs if qs else ""))])
            return [b""]
        for 길 in 영역길:
            if 경로 == 길.rstrip("/"):
                start("301 Moved Permanently", [("Location", 길)])
                return [b""]
            if 경로.startswith(길):
                이름 = 경로[len(길):] or "index.html"
                if 이름 == "서버.js":                # 영역 지정 화면을 서버 모드로(모델은 서버에서)
                    b = f'window.옛한글OCR서버 = "{_바탕주소(env)}";\n'.encode("utf-8")
                    start("200 OK", 공통머리 + [("Content-Type", "text/javascript; charset=utf-8"), ("Content-Length", str(len(b)))])
                    return [b]
                return _정적(start, os.path.join("영역지정", 이름))
        if 경로 == "/api/health":
            return _응답(start, dict(모델=판정보, 스레드=스레드, 캐시=캐시, 살핀파일=len(_살핀),
                                  모델들={k: v for k, v in 모델이름들.items()
                                          if k == "hangul" or os.path.exists(os.path.join(국한문폴더, "국한문모델.onnx"))}))
        q = {k: v[0] for k, v in urllib.parse.parse_qs(env.get("QUERY_STRING", "")).items()}
        if 경로 == "/api/inspect":
            파일, _ = _파일쪽(q)
            return _응답(start, 살핌상태(파일))
        if 경로 == "/api/tables":
            m = 모델얻기(q.get("model"))
            return _응답(start, dict(초성=m.Ls, 중성=m.Vs, 종성=m.Ts))
        if 방식 != "POST":
            return _응답(start, {"오류": "없는 주소"}, 404)
        몸 = _몸(env)
        파일, 쪽 = _파일쪽(몸)
        if 경로 == "/api/read":
            문턱 = float(몸.get("threshold") or 표시문턱)
            return _응답(start, 읽기(파일, 쪽, 문턱, 몸.get("model"), 몸.get("tiers"), 몸.get("spacing") is not False))
        if 경로 == "/api/compare":
            본문 = 몸.get("text") if 몸.get("text") is not None else 몸.get("본문")
            if not isinstance(본문, str):
                raise 손님오류("text(본문)가 없습니다")
            return _응답(start, 맞대기(파일, 쪽, 본문, 몸.get("model"), 몸.get("tiers")))
        if 경로 == "/api/boxes":
            상자 = 몸.get("boxes") or []
            if len(상자) > 20000:
                raise 손님오류("상자가 너무 많습니다")
            return _응답(start, 상자읽기(파일, 쪽, 상자, 몸.get("model")))
        if 경로 == "/api/edge":
            return _응답(start, 경계읽기(파일, 쪽, int(몸["x0"]), int(몸["x1"])))
        return _응답(start, {"오류": "없는 주소"}, 404)
    except 손님오류 as e:
        return _응답(start, dict({"오류": str(e)}, **e.덧), e.코드)
    except Exception as e:
        traceback.print_exc()
        return _응답(start, {"오류": f"서버에서 오류: {e}"}, 500)


if __name__ == "__main__":                     # 내 컴퓨터에서 시험 — python old-hangul-ocr-toolforge/app.py [포트]
    from socketserver import ThreadingMixIn
    from wsgiref.simple_server import WSGIServer, WSGIRequestHandler, make_server

    class 여럿(ThreadingMixIn, WSGIServer):
        daemon_threads = True

    class 조용히(WSGIRequestHandler):
        def log_message(self, fmt, *a):
            pass

    문 = int(sys.argv[1]) if len(sys.argv) > 1 else 8761
    with make_server("127.0.0.1", 문, app, server_class=여럿, handler_class=조용히) as s:
        print(f"옛한글 OCR 서버 — http://localhost:{문}/  (멈추려면 Ctrl+C)")
        try:
            s.serve_forever()
        except KeyboardInterrupt:
            print("멈췄습니다.")
