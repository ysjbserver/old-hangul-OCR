# -*- coding: utf-8 -*-
"""
1단계 — 이미 전사된 페이지를 모아 온다.  (v4: 해상도 검사 추가)

사용법:
    python step1_collect.py "신약젼셔 (1904년).pdf"
    python step1_collect.py "신약젼셔 (1904년).pdf" --max 20      # 우선 20쪽만 시험
    python step1_collect.py "신약젼셔 (1904년).pdf" --as 신약1904  # 폴더 이름 지정
    python step1_collect.py --adopt "신약젼셔 (1904년).pdf"        # v1 폴더 넘겨받기

결과:
    data/신약젼셔_1904년/text/0757.txt
    data/신약젼셔_1904년/img/0757.jpg
    data/신약젼셔_1904년/문헌.txt
"""
import os, re, sys, time, json, shutil, threading
import urllib.parse, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

# ─────────────────────────────────────────────────────────────────────
#  ※ 아래 CONTACT 를 본인 것으로 바꿔 주세요.
#     위키미디어 이용 규칙상 연락처가 든 User-Agent 를 요구합니다.
#     한글은 넣지 마세요 — HTTP 헤더는 영문/숫자만 허용됩니다.
CONTACT = "https://ko.wikisource.org/wiki/User:Aspere; aspere@wikimedia.kr"
UA      = f"OldHangulOCR/0.4 ({CONTACT})".encode("ascii", "ignore").decode()
WORKERS = 3        # 동시 내려받기 수. 위키미디어 권장 상한이 3입니다. 올리지 마세요.
WIDTH   = 1920     # 썸네일 폭. 1280 과 1920 만 받아집니다.
# ─────────────────────────────────────────────────────────────────────

API = "https://ko.wikisource.org/w/api.php"
_print_lock = threading.Lock()

def slugify(pdf):
    s = re.sub(r"\.(pdf|djvu)$", "", pdf, flags=re.I)
    s = re.sub(r"[()\[\]{}]", "", s)
    s = re.sub(r'[\\/:*?"<>|]', "", s)
    return re.sub(r"\s+", "_", s.strip()) or "문헌"

def _open(url, method="GET", timeout=90):
    """429/503 을 만나면 Retry-After 만큼 기다렸다 다시 시도한다."""
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method=method)
    for attempt in range(6):
        try:
            return urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                wait = int(e.headers.get("Retry-After") or 5) + attempt * 5
                with _print_lock:
                    print(f"    (서버가 잠시 쉬라고 합니다 — {wait}초 대기)")
                time.sleep(wait); continue
            raise
        except Exception:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"요청에 계속 실패했습니다: {url[:80]}…")

def api(**params):
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    return json.loads(_open(API + "?" + urllib.parse.urlencode(params)).decode("utf-8"))

def list_pages(pdf):
    """전사된 (쪽번호, 위키텍스트). 한 번에 50쪽씩 받아 온다."""
    out, cont = [], {}
    while True:
        r = api(action="query", generator="allpages", gapnamespace=250,
                gapprefix=pdf + "/", gaplimit=50,
                prop="revisions", rvprop="content", rvslots="main", **cont)
        for p in r.get("query", {}).get("pages", []):
            m = re.search(r"/(\d+)$", p["title"])
            if m and "revisions" in p:
                out.append((int(m.group(1)), p["revisions"][0]["slots"]["main"]["content"]))
        if "continue" in r:
            cont = r["continue"]
        else:
            break
    return sorted(out)

def url_pattern(pdf):
    """
    썸네일 주소를 문헌당 딱 한 번만 물어보고, 쪽번호만 갈아 끼울 틀을 만든다.
    (v2 는 쪽마다 한 번씩 물어보느라 요청이 두 배였습니다.)
    """
    r = api(action="query", prop="imageinfo", titles="File:" + pdf,
            iiprop="url", iiurlwidth=500, iiurlparam="page1-500px")
    ii = r["query"]["pages"][0].get("imageinfo")
    if not ii or not ii[0].get("thumburl"):
        raise RuntimeError(f"'{pdf}' 의 썸네일 주소를 찾지 못했습니다. 파일명을 확인해 주세요.")
    u = ii[0]["thumburl"].split("?")[0]
    return re.sub(r"/page\d+-\d+px-", f"/page{{N}}-{WIDTH}px-", u, count=1)

def _width_of(path):
    """이미 있는 파일의 가로 크기. 열 수 없으면 0."""
    try:
        with Image.open(path) as im:
            return im.size[0]
    except Exception:
        return 0

def fetch_one(pat, n, path):
    # 이미 있어도 해상도가 다르면 다시 받는다.
    # (v2 는 위키미디어 API 가 요청을 무시하고 500px 을 돌려주는 바람에
    #  작은 이미지를 받아 두는 문제가 있었습니다.)
    if os.path.exists(path):
        if _width_of(path) == WIDTH:
            return "skip"
        os.remove(path)
    data = _open(pat.replace("{N}", str(n)))
    if not data.startswith(b"\xff\xd8"):          # JPEG인지 확인
        return "fail"
    with open(path, "wb") as f:
        f.write(data)
    if _width_of(path) != WIDTH:                  # 엉뚱한 크기를 받았으면 실패 처리
        return "small"
    return "ok"

def collect(pdf, slug, limit=None):
    root = os.path.join("data", slug)
    tdir, idir = os.path.join(root, "text"), os.path.join(root, "img")
    os.makedirs(tdir, exist_ok=True); os.makedirs(idir, exist_ok=True)
    with open(os.path.join(root, "문헌.txt"), "w", encoding="utf-8") as f:
        f.write(pdf + "\n")

    print(f"[1/3] '{pdf}' 의 전사된 페이지를 찾는 중…")
    pages = list_pages(pdf)
    if limit: pages = pages[:limit]
    print(f"      {len(pages)}쪽 발견  →  data/{slug}/")

    print("[2/3] 위키텍스트 저장 중…")
    for n, body in pages:
        with open(os.path.join(tdir, f"{n:04d}.txt"), "w", encoding="utf-8") as f:
            f.write(body)

    print(f"[3/3] 스캔 이미지 내려받는 중 (동시 {WORKERS}개)…")
    pat = url_pattern(pdf)
    done = {"ok": 0, "skip": 0, "fail": 0, "small": 0}
    t0 = time.time()

    def work(item):
        n = item[0]
        try:
            res = fetch_one(pat, n, os.path.join(idir, f"{n:04d}.jpg"))
        except Exception as e:
            res = "fail"
            with _print_lock: print(f"      {n}쪽 실패 — {e}")
        with _print_lock:
            done[res] += 1
            c = done["ok"] + done["skip"] + done["fail"]
            if c % 10 == 0 or c == len(pages):
                el = time.time() - t0
                rate = c / el if el else 0
                left = (len(pages) - c) / rate if rate else 0
                print(f"      {c}/{len(pages)}쪽  ({rate:.1f}쪽/초, 남은 시간 약 {left/60:.1f}분)")

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(work, pages))

    print(f"\n완료 — 새로 받음 {done['ok']}쪽 / 이미 있음 {done['skip']}쪽 "
          f"/ 실패 {done['fail']}쪽 / 크기이상 {done['small']}쪽")
    print(f"       걸린 시간 {(time.time()-t0)/60:.1f}분  →  data/{slug}/")
    if done["small"]:
        print(f"\n※ {done['small']}쪽이 요청한 {WIDTH}px 이 아닌 크기로 왔습니다.")
        print("  WIDTH 를 1280 으로 바꿔 다시 실행해 보세요. 둘 중 하나는 반드시 받아집니다.")

def adopt(pdf):
    slug = slugify(pdf); dst = os.path.join("data", slug)
    if not (os.path.isdir("data/text") or os.path.isdir("data/img")):
        print("옮길 data/text, data/img 폴더가 없습니다."); return
    os.makedirs(dst, exist_ok=True)
    for sub in ("text", "img"):
        src = os.path.join("data", sub)
        if not os.path.isdir(src): continue
        os.makedirs(os.path.join(dst, sub), exist_ok=True)
        n = 0
        for name in os.listdir(src):
            shutil.move(os.path.join(src, name), os.path.join(dst, sub, name)); n += 1
        os.rmdir(src)
        print(f"  data/{sub}/ 의 {n}개 파일 → data/{slug}/{sub}/")
    with open(os.path.join(dst, "문헌.txt"), "w", encoding="utf-8") as f:
        f.write(pdf + "\n")
    print(f"\n완료 — '{pdf}' 로 정리했습니다.")

def main():
    args = sys.argv[1:]
    if not args: print(__doc__); sys.exit(1)
    if args[0] == "--adopt":
        if len(args) < 2: print('사용법: python step1_collect.py --adopt "<파일명>.pdf"'); sys.exit(1)
        adopt(args[1]); return

    pdf = args[0]
    slug = args[args.index("--as") + 1] if "--as" in args else slugify(pdf)
    limit = int(args[args.index("--max") + 1]) if "--max" in args else None

    if os.path.isdir("data/text") or os.path.isdir("data/img"):
        print("잠깐 — 이전 버전이 만든 data/text 또는 data/img 폴더가 남아 있습니다.")
        print("어느 문헌 것인지 알 수 없어 그대로 두면 섞입니다. 먼저 아래를 실행해 주세요:\n")
        print('    python step1_collect.py --adopt "<그 문헌의 파일명>.pdf"\n')
        sys.exit(1)

    collect(pdf, slug, limit)

if __name__ == "__main__":
    main()
