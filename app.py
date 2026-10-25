# -*- coding: utf-8 -*-
"""
옛한글 OCR — Toolforge 웹 도구

위키문헌 소도구(OCR · 전사대조)와 영역 지정 화면이 묻는 서버. 셈은 `부품/` 그대로, 모델은 `onnx모델.py`(ONNX · CPU).
⚠ 만들어진 사본 — 손으로 고치지 말 것(원본 `근원/툴포지/app.py`).

돌리기
  · Toolforge — `Procfile` 의 gunicorn 이 `app:app` 을 띄움(포트 8000)
  · 내 컴퓨터 — `python old-hangul-ocr-toolforge/app.py` → http://localhost:8761/

주소
  /                       첫 화면(쓰는 법)
  /ocr.js  /소도구.js       OCR 소도구(서버 주소를 스스로 채움)
  /compare.js /전사대조.js  전사대조 소도구
  /area/ /영역지정/          영역 지정 화면 (/region/ → /area/)
  GET  /api/inspect?file=     파일의 판형 · 자간비 · 판짜임 (처음 한 번 뒤에서 잼 — 끝날 때까지 되물음)
  POST /api/read            {file, page}            → OCR 결과
  POST /api/compare         {file, page, text}      → 전사대조 결과
  POST /api/boxes           {file, page, boxes}     → 상자마다 글자(영역 지정 화면)
  POST /api/edge            {file, page, x0, x1}    → 열의 글자 경계 확률(영역 지정 화면)
  POST /api/area-read       {file, page, ratio, width, height, model} → 쪽 전체의 글자·확신·상자(영역 지정 화면)
  GET  /api/tables?model=   그 모델의 글자표(번호 → 글자)
  GET  /api/health          모델 · 판 정보
  선택 값 — model("hangul" 근대 순한글 · 기본 / "hanmun" 근대 국한문) · tiers(몇 단, 없으면 자동) ·
    spacing(/api/read 만 — false 면 띄어쓰기 감지 끔)
"""
import hashlib
import json
import os
import re
import sys

# 서버가 불러오는 부품의 바이트코드 캐시를 만들지 않음.
sys.dont_write_bytecode = True

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

# 글자 모델 — "hangul"(기본) · "hanmun"(있을 때만 · 처음 쓸 때 불러옴)
모델이름들 = {"hangul": "근대 순한글", "hanmun": "근대 국한문"}
국한문폴더 = os.path.join(여기, "모델", "근대 국한문")      # `모델/<모델이름들 값>/`
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
    """설정 `s` 의 단만 고른 값으로(없거나 "auto" 면 그대로). 1단 = 1, N단 = 가름줄 높이 [1/N …]."""
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
# ⚠ 여러 쪽 파일은 API 가 요청한 너비를 무시함 → 주소를 한 번 받아 `/page{쪽}-1920px-` 만 갈아 끼움
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


def 쪽검사(정보, 쪽):
    """쪽 번호가 그 파일에 있는지 — 없으면 400. 한 장짜리는 1쪽뿐, 여러 쪽은 1~쪽수."""
    if isinstance(쪽, bool) or not isinstance(쪽, int) or 쪽 < 1:
        raise 손님오류("page(쪽 번호)는 1 이상의 정수여야 합니다")
    if not 정보["여러쪽"]:
        if 쪽 != 1:
            raise 손님오류(f"이 파일은 한 장짜리 그림이라 1쪽만 있습니다(요청 {쪽}쪽)")
    elif 정보["쪽수"] and 쪽 > 정보["쪽수"]:
        raise 손님오류(f"이 파일은 {정보['쪽수']}쪽까지입니다")


def 스캔(파일, 쪽):
    """그 쪽 스캔의 로컬 경로(받아 둠). 1920px."""
    정보 = 파일정보(파일)
    쪽검사(정보, 쪽)                       # 캐시 폴더를 만들기 전에
    d = os.path.join(캐시, hashlib.sha1(파일.encode("utf-8")).hexdigest()[:16])
    os.makedirs(d, exist_ok=True)
    if 정보["여러쪽"]:
        p = os.path.join(d, f"{쪽:04d}.jpg")
        r = step1_collect.fetch_one(정보["틀"], 쪽, p)
        if r not in ("ok", "skip"):
            raise 손님오류(f"스캔을 받지 못했습니다({r}) — {파일} {쪽}쪽")
    else:
        p = os.path.join(d, "0001.png")
        with _한장잠금:                    # 같은 그림을 동시에 받지 않게 · 다 쓴 뒤 옮김(반쯤 쓴 그림을 읽지 않게)
            if not os.path.exists(p):
                im = Image.open(__import__("io").BytesIO(step1_collect._open(정보["주소"]))).convert("L")
                if im.size[0] != 너비:
                    im = im.resize((너비, round(im.size[1] * 너비 / im.size[0])), Image.BICUBIC)
                im.save(p + ".part", "PNG")
                os.replace(p + ".part", p)
    os.utime(p)
    if r_정리.acquire(blocking=False):
        try:
            _캐시정리()
        finally:
            r_정리.release()
    return p


def 진단정보(파일, 쪽, 경로, 결과):
    """전사대조에 쓴 스캔 · 서버 판을 재현할 짧은 정보."""
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
_한장잠금 = threading.Lock()
_그림들 = OrderedDict()                   # (파일, 쪽) → (PIL 회색 그림, numpy) — 최근 6쪽
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


# ── 파일마다 처음 한 번 — 판형 · 자간비 · 판짜임 (`읽기.js` `판형살피기` 와 같은 셈) ─────
설정파일 = os.path.join(캐시, "_파일설정.json")
판형판 = 5                               # 판정 규칙을 바꾸면 올림(기억한 값을 버림) — `읽기.js` `판형판` 과 같은 뜻
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
    쪽들 = range(1, n + 1)
    if k <= 0 or n <= k:
        return list(쪽들)
    return list(쪽들[::max(1, n // k)][:k])


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
            잰 = scan.estimate_ratio([길[p] for p in 단쪽 if p in 길], 판형)   # 너무 크면 다시 잼(scan.RATIO_RECHECK)
            값 = {"단": list(판형) if isinstance(판형, (list, tuple)) else 판형}
            if 잰:
                값["자간비"] = float(잰)
            짜 = page.판짜임정하기(짜임)
            if 짜:
                값["판짜임"] = 짜
            if 잰:                         # 읽기 자간 — 순한글 모델 확신으로 고름(`page.읽기자간고르기`)
                _살핌일[파일]["진행"] = "읽기 자간 고르는 중"
                단쪽그림 = [길[p] for p in 단쪽 if p in 길]
                표준 = 짜["자간"] if 짜 and page.SCAN_PITCH else None
                고를쪽 = page.읽기자간쪽(단쪽그림, float(잰), 판형, 짜) or 단쪽그림[:page.READ_PICK_PAGES]
                고른, _ = page.읽기자간고르기(고를쪽, float(잰), 판형, 모델, 표준)
                if 고른 != float(잰):
                    값["읽기자간비"] = float(고른)
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


_완료들 = OrderedDict()  # 완성 결과 캐시 — 계산 잠금 안에서만 접근
결과수명 = 120
결과최대바이트 = 4 * 1024 * 1024
결과최대개수 = 16


def _작업실행(이름, ip, 조건, 작업, 단계, 시작):
    """같은 스캔 · 입력의 완성 결과는 재사용(잠금 안에서 확인)."""
    t = time.perf_counter()
    with open(ip, "rb") as f:
        그림해시 = hashlib.sha256(f.read()).hexdigest()
    열쇠 = (이름, 그림해시, hashlib.sha256(json.dumps(
        조건, ensure_ascii=False, sort_keys=True, default=_json기본).encode("utf-8")).hexdigest())
    단계["입력확인"] = time.perf_counter() - t
    대기 = time.perf_counter()
    with 계산:
        t = time.perf_counter()
        단계["대기"] = t - 대기
        for k in list(_완료들):
            if _완료들[k][0] <= t:
                del _완료들[k]
        사용 = os.environ.get("OCR_RESULT_CACHE", "1") != "0"
        저장 = _완료들.get(열쇠) if 사용 else None
        재사용 = 저장 is not None
        if 재사용:
            _완료들.move_to_end(열쇠)
            답 = json.loads(저장[1])  # 매번 새 객체
        else:
            답 = 작업()
            if 사용 and not 답.get("사유"):
                b = json.dumps(답, ensure_ascii=False, default=_json기본).encode("utf-8")
                if len(b) <= 결과최대바이트:
                    _완료들[열쇠] = (time.perf_counter() + 결과수명, b)
                    while (len(_완료들) > 결과최대개수 or
                           sum(len(v[1]) for v in _완료들.values()) > 결과최대바이트):
                        _완료들.popitem(last=False)
        단계["계산"] = time.perf_counter() - t
    답["초"] = round(단계["대기"] + 단계["계산"], 3)
    단계["전체"] = time.perf_counter() - 시작
    답["단계초"] = {k: round(v, 6) for k, v in 단계.items()}
    답["결과재사용"] = 재사용
    return 답


def 읽기(파일, 쪽, 문턱=표시문턱, 모델이름=None, 단=None, 띄움=True):
    """OCR 한 쪽."""
    시작 = time.perf_counter()
    자동단 = 단 in (None, "", "auto", "자동")
    s = 단바꾸기(살핀값(파일), 단)
    모델 = 모델얻기(모델이름)
    단계 = {"준비": time.perf_counter() - 시작}
    t = time.perf_counter()
    ip = 스캔(파일, 쪽)
    단계["스캔"] = time.perf_counter() - t
    단 = s.get("단") or 1
    단 = tuple(단) if isinstance(단, list) else 단
    r = s.get("읽기자간비") or s.get("자간비") or scan.YX_RATIO
    표준 = s["판짜임"]["자간"] if s.get("판짜임") and page.SCAN_PITCH else None
    def 작업():
        t = time.perf_counter()
        geo = scan.page_geometry(ip, r, 단, 읽기=True, 가장자리=True, 표준자간=표준, 빈단=자동단)
        단계["기하"] = time.perf_counter() - t
        t = time.perf_counter()
        geo, 줄들 = align.잉크골라(geo, lambda g: align.read_page_lines(모델, g, 3, 띄움=align.SPACE and 띄움))
        줄들 = 줄들 or []
        등급, 까닭 = page.쪽건강(None, geo, 표준=s.get("판짜임"))
        단계["인식"] = time.perf_counter() - t
        살핀 = s
        if geo is not None and geo.get("빈단"):
            살핀 = dict(s, 단=geo["단"], 자간비=geo["pitch"] / geo["xpitch"],
                        빈단=geo["빈단"], 단별자간비=geo["단별자간비"])
        n = sum(len(z[0]) for z in 줄들)
        if not n:
            return dict(판정=dict(등급="못씀" if geo is None else 등급, 까닭=까닭 or ["읽어 내지 못했습니다"]),
                        글월="", 교정용="", 표시비=0, 상자수=0, 살핀=살핀)
        글월, 교정용, 셀 = 줄글월(줄들, 문턱)
        return dict(판정=dict(등급=등급, 까닭=까닭), 글월=글월, 교정용=교정용, 표시비=셀 / n, 상자수=n, 글자수=n,
                    살핀=살핀)
    return _작업실행("read", ip, [파일, 쪽, s, 모델이름 or "hangul", 문턱, 자동단, 띄움], 작업, 단계, 시작)


def 맞대기(파일, 쪽, 본문, 모델이름=None, 단=None):
    """전사대조 한 쪽."""
    시작 = time.perf_counter()
    s = 단바꾸기(살핀값(파일), 단)
    모델 = 모델얻기(모델이름)
    단계 = {"준비": time.perf_counter() - 시작}
    t = time.perf_counter()
    ip = 스캔(파일, 쪽)
    단계["스캔"] = time.perf_counter() - t
    def 작업():
        r = 대조.한쪽(모델, None, ip, 본문, 설정=s)
        return _대조응답(파일, 쪽, ip, 본문, r)
    return _작업실행("compare", ip, [파일, 쪽, s, 모델이름 or "hangul", 본문], 작업, 단계, 시작)


def _대조응답(파일, 쪽, ip, 본문, r):
    답 = dict(사유=r.get("사유"), 아는문헌=True)
    답["debug"] = 진단정보(파일, 쪽, ip, r)
    if not r.get("사유"):
        # 원문 자리를 JS 문자열 자리(UTF-16)로 — BMP 밖 글자가 있으면 파이썬 자리와 갈림
        if any(ord(ch) > 0xFFFF for ch in 본문):
            앞 = [0]
            for ch in 본문:
                앞.append(앞[-1] + (2 if ord(ch) > 0xFFFF else 1))
            for c in r["후보"]:
                c["시작"], c["끝"] = 앞[c["시작"]], 앞[c["끝"]]
        답.update(일치=r["일치"], 흔들림=r["흔들림"], 흔들린열=r["흔들린열"], 기하=r["기하"], 제목=r["제목"],
                 글자수=r["글자수"], 시도기록=r.get("시도기록", []), 진단=r.get("진단", {}),
                 후보=[c.copy() for c in r["후보"]])
    return 답


def 영역자동읽기(파일, 쪽, 자간비=None, 모델이름=None, 너비확인=None, 높이확인=None):
    """영역 화면의 한 단 자동 읽기 — 자간비는 화면이 준 값(파일 판형은 안 잼)."""
    시작 = time.perf_counter()
    모델 = 모델얻기(모델이름)
    try:
        r = float(자간비) if 자간비 is not None else scan.YX_RATIO
    except (TypeError, ValueError):
        raise 손님오류("ratio(자간비)는 양수여야 합니다")
    if not np.isfinite(r) or r <= 0:
        raise 손님오류("ratio(자간비)는 양수여야 합니다")
    단계 = {"준비": time.perf_counter() - 시작}
    t = time.perf_counter()
    ip = 스캔(파일, 쪽)
    with Image.open(ip) as im:
        너비, 높이 = im.size
    단계["스캔"] = time.perf_counter() - t
    if ((너비확인 is not None and 너비확인 != 너비) or
            (높이확인 is not None and 높이확인 != 높이)):
        raise 손님오류("서버와 화면의 스캔 크기가 다릅니다 — 쪽을 다시 불러오세요")
    def 작업():
        t = time.perf_counter()
        geo = scan.page_geometry(ip, r, 1, 읽기=True, 가장자리=True)
        단계["기하"] = time.perf_counter() - t
        t = time.perf_counter()
        def 읽기(geo):
            줄들 = []
            열들 = align.열마다읽기(모델, geo, 3)
            남 = align.가장자리다듬기(geo, 열들) if geo.get("가장자리") else range(len(열들))
            for i in 남:
                if 열들[i] is None:
                    continue
                _, 글자, 확신, 상자, _ = 열들[i]
                남길 = [j for j, c in enumerate(글자) if c not in align.PUNCT_DROP]
                줄들.append(dict(글자=[글자[j] for j in 남길],
                                  확신=[float(확신[j]) for j in 남길],
                                  상자=[[int(v) for v in 상자[j]] for j in 남길]))
            return 줄들
        _, 줄들 = align.잉크골라(geo, 읽기, lambda z: [c for 줄 in z for c in 줄["확신"]])
        줄들 = 줄들 or []
        단계["인식"] = time.perf_counter() - t
        return dict(줄들=줄들, 너비=너비, 높이=높이)
    return _작업실행("area-read", ip, [파일, 쪽, r, 모델이름 or "hangul"], 작업, 단계, 시작)


# 영역 지정 요청의 크기 한도
상자최대화소 = 1_048_576
상자합계최대화소 = 16_777_216
경계최대확대 = 4
경계최대높이 = 8192


def _좌표(v, 이름):
    if type(v) is int or (type(v) is float and v.is_integer()):
        return int(v)
    raise 손님오류(이름 + "는 유한한 정수 좌표여야 합니다")


def _상자목록(상자들):
    if not isinstance(상자들, list):
        raise 손님오류("boxes는 상자 목록이어야 합니다")
    if len(상자들) > 20000:
        raise 손님오류("상자가 너무 많습니다")
    결과, 합계 = [], 0
    for i, b in enumerate(상자들):
        이름 = f"boxes[{i}]"
        if not isinstance(b, list) or len(b) != 4:
            raise 손님오류(이름 + "는 [x0, y0, x1, y1]이어야 합니다")
        x0, y0, x1, y1 = [_좌표(v, 이름) for v in b]
        if not (0 <= x0 < x1 and 0 <= y0 < y1):
            raise 손님오류(이름 + "의 좌표 순서나 크기가 올바르지 않습니다")
        화소 = (x1 - x0 + 8) * (y1 - y0 + 8)  # 모델.crops의 사방 4px 여백 포함
        합계 += 화소
        if 화소 > 상자최대화소 or 합계 > 상자합계최대화소:
            raise 손님오류("상자 크기 또는 합계가 처리 한도를 넘습니다")
        결과.append([x0, y0, x1, y1])
    return 결과


def 글자표지문(m):
    """글자표(초 · 중 · 종)의 짧은 지문 — 영역 지정 화면이 가진 표가 서버 모델과 같은지 확인."""
    try:
        표 = [list(m.Ls), list(m.Vs), list(m.Ts)]
    except TypeError:                     # 글자표가 없는 모의 모델(시험)
        return None
    return hashlib.sha256(json.dumps(표, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def 상자읽기(파일, 쪽, 상자들, 모델이름=None):
    상자들 = _상자목록(상자들)
    im, _ = 그림(파일, 쪽)
    for i, b in enumerate(상자들):
        if b[2] > im.width or b[3] > im.height:
            raise 손님오류(f"boxes[{i}]가 이미지 경계를 벗어납니다")
    모델 = 모델얻기(모델이름)
    with 계산:
        kL, kV, kT, cf = 모델.read(im, 상자들)
    답 = dict(초=[int(v) for v in kL], 중=[int(v) for v in kV], 종=[int(v) for v in kT], 확신=[float(v) for v in cf])
    표 = 글자표지문(모델)
    if 표:
        답["표"] = 표
    return 답


def 경계읽기(파일, 쪽, x0, x1):
    x0, x1 = _좌표(x0, "x0"), _좌표(x1, "x1")
    if not 0 <= x0 < x1:
        raise 손님오류("열 좌표는 0 <= x0 < x1이어야 합니다")
    배율 = onnx모델.경계폭 / (x1 - x0)
    if 배율 > 경계최대확대:
        raise 손님오류("열이 너무 좁습니다: 경계 검출 확대는 최대 4배입니다")
    _, g = 그림(파일, 쪽)
    if x1 > g.shape[1]:
        raise 손님오류("열 좌표가 이미지 경계를 벗어납니다")
    if max(8, int(round(g.shape[0] * 배율))) > 경계최대높이:
        raise 손님오류("경계 검출 이미지 높이가 처리 한도를 넘습니다")
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
옛영역길 = "/region"                 # → /area/ 로 넘김


공개호스트 = "old-hangul-ocr.toolforge.org"
로컬호스트 = {"localhost", "127.0.0.1", "::1"}


def _주소검증(주소):
    """주소 검사 — HTTP(S) · 호스트 · 선택 경로만(제어문자는 먼저 거름)."""
    if not isinstance(주소, str) or not re.fullmatch(r"[A-Za-z0-9._~:/%\[\]-]+", 주소):
        raise ValueError("주소 문자")
    u = urllib.parse.urlsplit(주소)
    host = u.hostname
    if u.scheme not in ("http", "https") or not host or u.username or u.password or u.query or u.fragment:
        raise ValueError("주소 형식")
    if host != "::1" and not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*", host):
        raise ValueError("호스트 형식")
    if u.netloc.endswith(":") or (u.port is not None and not 1 <= u.port <= 65535):
        raise ValueError("포트")
    return u


def _바탕주소(env):
    # OCR_BASE 가 있으면 그 주소만 씀(요청 헤더 무시)
    base = os.environ.get("OCR_BASE")
    if base:
        try:
            _주소검증(base)
        except ValueError:
            raise 손님오류("OCR_BASE 주소 설정이 올바르지 않습니다", 500)
        return base.rstrip("/") + "/"
    # 전달 헤더도 허용 호스트만
    host = env.get("HTTP_X_FORWARDED_HOST") or env.get("HTTP_HOST") or "localhost"
    proto = env.get("HTTP_X_FORWARDED_PROTO") or env.get("wsgi.url_scheme", "http")
    try:
        u = _주소검증(f"{proto}://{host}")
        if proto not in ("http", "https") or u.path or u.hostname not in 로컬호스트 | {공개호스트}:
            raise ValueError("허용되지 않은 주소")
        if u.hostname == 공개호스트:
            if u.port not in (None, 443):
                raise ValueError("공개 포트")
            proto = "https"            # 공개 주소는 늘 HTTPS
    except ValueError:
        raise 손님오류("서버 주소 헤더가 올바르지 않습니다")
    return f"{proto}://{u.netloc.lower()}/"


def _서버문장(env, 유지=False):
    # JSON 문자열로 넣어 JS 에 안전하게
    주소 = json.dumps(_바탕주소(env), ensure_ascii=True)
    앞 = "window.옛한글OCR서버 || " if 유지 else ""
    return f"window.옛한글OCR서버 = {앞}{주소};\n".encode("utf-8")


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
    try:
        n = int(env.get("CONTENT_LENGTH") or 0)
    except (TypeError, ValueError):
        raise 손님오류("요청 길이가 올바르지 않습니다")
    if n < 0:
        raise 손님오류("요청 길이가 올바르지 않습니다")
    if n > 5_000_000:
        raise 손님오류("요청이 너무 큽니다")
    try:
        몸 = json.loads(env["wsgi.input"].read(n).decode("utf-8") or "{}") if n else {}
    except (UnicodeDecodeError, ValueError):
        raise 손님오류("요청 본문은 올바른 UTF-8 JSON이어야 합니다")
    if not isinstance(몸, dict):
        raise 손님오류("요청 본문은 JSON 객체여야 합니다")
    return 몸


def _파일쪽(q):
    파일 = q.get("file") or q.get("파일") or ""
    if not isinstance(파일, str):
        raise 손님오류("file(파일 이름)은 문자열이어야 합니다")
    파일 = 파일.strip().replace("_", " ")
    for 머리 in ("File:", "파일:"):
        if 파일.startswith(머리):
            파일 = 파일[len(머리):]
    파일 = 파일.strip()
    if not 파일:
        raise 손님오류("file(파일 이름)이 없습니다")
    쪽 = q.get("page", q.get("쪽", 1))
    try:
        if isinstance(쪽, bool) or not isinstance(쪽, (str, int, float)) or (isinstance(쪽, float) and not 쪽.is_integer()):
            raise ValueError
        쪽 = int(쪽)
        if 쪽 < 1:
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise 손님오류("page(쪽 번호)는 1 이상의 정수여야 합니다")
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
            앞 = _서버문장(env, 유지=True)
            return _정적(start, 소도구들[경로], 앞)
        if 경로 == 옛영역길 or 경로.startswith(옛영역길 + "/"):
            새 = "/area/" + 경로[len(옛영역길):].lstrip("/")
            qs = env.get("QUERY_STRING", "")
            start("301 Moved Permanently", [("Location", urllib.parse.quote(새) + ("?" + qs if qs else ""))])
            return [b""]
        for 길 in 영역길:
            if 경로 == 길.rstrip("/"):
                qs = env.get("QUERY_STRING", "")
                start("301 Moved Permanently", [("Location", urllib.parse.quote(길) + ("?" + qs if qs else ""))])
                return [b""]
            if 경로.startswith(길):
                이름 = 경로[len(길):] or "index.html"
                if 이름 == "서버.js":                # 영역 지정 화면을 서버 모드로(모델은 서버에서)
                    b = _서버문장(env)
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
            return _응답(start, dict(초성=m.Ls, 중성=m.Vs, 종성=m.Ts, 표=글자표지문(m)))
        if 방식 != "POST":
            return _응답(start, {"오류": "없는 주소"}, 404)
        몸 = _몸(env)
        파일, 쪽 = _파일쪽(몸)
        if 경로 == "/api/read":
            문턱 = 몸.get("threshold", 표시문턱)
            try:
                if isinstance(문턱, bool):
                    raise ValueError
                문턱 = float(문턱)
                if not 0 <= 문턱 <= 1:
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
                raise 손님오류("threshold(확신 문턱)는 0~1 사이의 숫자여야 합니다")
            return _응답(start, 읽기(파일, 쪽, 문턱, 몸.get("model"), 몸.get("tiers"), 몸.get("spacing") is not False))
        if 경로 == "/api/compare":
            본문 = 몸.get("text") if 몸.get("text") is not None else 몸.get("본문")
            if not isinstance(본문, str):
                raise 손님오류("text(본문)가 없습니다")
            return _응답(start, 맞대기(파일, 쪽, 본문, 몸.get("model"), 몸.get("tiers")))
        if 경로 == "/api/boxes":
            상자 = 몸.get("boxes", [])
            return _응답(start, 상자읽기(파일, 쪽, 상자, 몸.get("model")))
        if 경로 == "/api/area-read":
            return _응답(start, 영역자동읽기(파일, 쪽, 몸.get("ratio"), 몸.get("model"), 몸.get("width"), 몸.get("height")))
        if 경로 == "/api/edge":
            return _응답(start, 경계읽기(파일, 쪽, 몸.get("x0"), 몸.get("x1")))
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
