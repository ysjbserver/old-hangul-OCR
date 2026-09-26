/*
 * 옛한글 OCR — 위키문헌 소도구
 *
 * 페이지 이름공간 편집 창에 단추를 놓고, 누르면 그 쪽 스캔을 브라우저 안에서 읽어 편집 상자에 넣음.
 * 읽는 셈은 `읽기.js`, 이 파일은 화면과 그림 가져오기만.
 * ⚠ 저장은 하지 않음 — 사람이 확인하고 누름
 */
(function () {
"use strict";

// ── 어디서 가져오나 ──────────────────────────────────────────────────
// ⚠ 위키문헌 CSP 가 허용하는 곳만 됨(jsdelivr · cdnjs · unpkg · toolforge 등). 다른 곳은 조용히 막힘
var ORT = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/";

// 실행기 — 기본 WASM. `window.옛한글OCR실행기 = "webgpu"` 로 WebGPU (파이썬과 대조 안 됨)
var 실행기 = (window.옛한글OCR실행기 === "webgpu") ? ["webgpu", "wasm"] : ["wasm"];
// 모델·설정·읽기.js 가 있는 곳 (`window.옛한글OCR자료`)
// ⚠ 빈 값이면 빈 채로 — "/" 를 붙이면 사이트 루트가 됨
var 자료 = window.옛한글OCR자료 || "";
if (자료 && 자료.charAt(자료.length - 1) !== "/") 자료 += "/";

var 상태, 단추, 모델 = null, 설정 = null;

// ── 작은 도우미 ──────────────────────────────────────────────────────
function 알림(t) { if (상태) 상태.textContent = t; }

function 스크립트(url) {
  return new Promise(function (ok, no) {
    var s = document.createElement("script");
    s.src = url;
    s.onload = ok;
    s.onerror = function () { no(new Error(url + " 를 못 불러왔습니다")); };
    document.head.appendChild(s);
  });
}

/**
 * 편집 중인 쪽의 파일 이름과 쪽 번호. "페이지:셩경젼셔 신약.pdf/393" → {파일, 쪽: 393}
 * ⚠ 이름공간 이름은 언어마다 달라 `wgCanonicalNamespace` 로 확인
 */
function 지금쪽() {
  var cfg = mw.config.get(["wgCanonicalNamespace", "wgTitle", "wgAction"]);
  if (cfg.wgCanonicalNamespace !== "Page") return null;
  var m = /^(.*)\/(\d+)$/.exec(cfg.wgTitle);
  if (!m) return null;
  return { 파일: m[1], 쪽: parseInt(m[2], 10) };
}

/**
 * 그 쪽 스캔을 학습 때와 같은 너비(`설정.스캔너비`, 1920px)로 받기.
 * ⚠ 너비가 다르면 쪽 판정이 전부 '못씀' — 받은 뒤 실제 너비를 확인
 * ⚠ 여러 쪽 파일은 API 가 요청한 너비를 무시하고 500px 을 줌
 *   → 주소를 한 번 받아 `/page{쪽}-{너비}px-` 만 갈아 끼움
 * ⚠ 주소를 통째로 짐작하면 404 (해시가 들어 있음)
 * ⚠ `crossOrigin="anonymous"` 가 있어야 캔버스에서 픽셀을 꺼낼 수 있음
 */
var 주소틀 = {};                 // 파일 이름 → 주소 틀 (파일당 한 번 물음)
var 쪽수 = {};                   // 파일 이름 → 전체 쪽 수

function 주소틀얻기(파일) {
  var 너비 = (설정 && 설정.스캔너비) || 1920;
  return 주소틀[파일]
    ? Promise.resolve(주소틀[파일])
    : new mw.Api().get({
        action: "query", format: "json", formatversion: 2,
        prop: "imageinfo", titles: "File:" + 파일,
        iiprop: "url|size", iiurlwidth: 500, iiurlparam: "page1-500px",
      }).then(function (r) {
        var p = r.query && r.query.pages && r.query.pages[0];
        var ii = p && p.imageinfo && p.imageinfo[0];
        if (!ii || !ii.thumburl) {
          throw new Error("스캔 주소를 못 받았습니다. 파일 이름이 맞는지 보세요: " + 파일);
        }
        // 받은 주소에서 쪽 번호와 너비만 갈아 끼우기
        var u = ii.thumburl.split("?")[0];
        if (!/\/page\d+-\d+px-/.test(u)) {
          throw new Error("이 파일은 여러 쪽짜리(PDF·DjVu)가 아닌 것 같습니다: " + 파일);
        }
        주소틀[파일] = u.replace(/\/page\d+-\d+px-/, "/page{N}-" + 너비 + "px-");
        쪽수[파일] = ii.pagecount || 0;       // 판형 살필 쪽 고르기에 씀
        return 주소틀[파일];
      });
}

function 스캔가져오기(파일, 쪽) {
  var 너비 = (설정 && 설정.스캔너비) || 1920;
  return 주소틀얻기(파일).then(function (pat) {
    var url = pat.replace("{N}", String(쪽));
    return new Promise(function (ok, no) {
      var im = new Image();
      im.crossOrigin = "anonymous";
      im.onload = function () {
        if (im.naturalWidth !== 너비) {
          no(new Error("스캔을 " + 너비 + "px 로 달라고 했는데 "
                       + im.naturalWidth + "px 이 왔습니다. 이 크기로는 쪽 판정이"
                       + " 맞지 않습니다."));
          return;
        }
        ok(im);
      };
      im.onerror = function () {
        no(new Error("스캔 그림을 못 읽었습니다. 그 쪽이 정말 있는 쪽인가요? " + url));
      };
      im.src = url;
    });
  });
}

/** 편집 상자 (2017 편집기·CodeMirror 아래에서도 원본은 이것) */
function 편집상자() {
  return document.querySelector("#wpTextbox1")
      || document.querySelector("textarea[name='wpTextbox1']");
}

// ── 모델 한 번만 불러오기 ────────────────────────────────────────────
var 준비중 = null;
function 준비() {
  if (준비중) return 준비중;
  준비중 = (async function () {
    알림("도구를 불러오는 중…");
    if (!window.옛한글읽기) await 스크립트(자료 + "읽기.js");
    // ⚠ `ort.min.js` 말고 `ort.webgpu.min.js` — WASM 도 들어 있고, `ort.min.js` 에는 WebGPU 가 없음
    if (!window.ort) await 스크립트(ORT + "ort.webgpu.min.js");
    설정 = window.옛한글읽기.설정넣기(
      await (await fetch(자료 + "설정.json")).json());
    알림("모델을 불러오는 중… (2.4MB, 처음 한 번만)");
    ort.env.wasm.wasmPaths = ORT;
    // ⚠ 위키문헌에는 SharedArrayBuffer 가 없어 WASM 은 1스레드
    ort.env.wasm.numThreads = 1;
    var 세션 = await ort.InferenceSession.create(자료 + "옛한글모델.onnx",
                    { executionProviders: 실행기 });
    모델 = window.옛한글읽기.모델만들기(설정, 세션, ort);
  })();
  return 준비중;
}

/** 파일 이름으로 문헌 설정 찾기. 모르는 문헌이면 빈 것 */
function 문헌설정(파일) {
  var 표 = (설정 && 설정.문헌) || {};
  for (var k in 표) if (표[k].파일 === 파일) return { 슬러그: k, 값: 표[k] };
  return { 슬러그: null, 값: {} };
}

/**
 * 처음 보는 파일의 판형(1 · 2 · 가름줄 높이 목록)을 쪽 몇 장으로 정하기 — `읽기.js` 의 `판형정하기`.
 * 고르게 12쪽(가름줄)·8쪽(가운데 줄)을 받고, 정한 것은 브라우저에 기억.
 * ⚠ 판정 규칙을 바꾸면 `판형판` 을 올릴 것 — 안 올리면 기억한 옛 판정을 씀
 * ⚠ 자간비는 재지 않음(기본값)
 */
var 판형판 = 1;
var 판형기억 = {};

function 고르게(n, k) {             // 1…n 쪽에서 고르게 k 개
  var 쪽들 = [];
  for (var i = 1; i <= n; i++) 쪽들.push(i);
  if (k <= 0 || n <= k) return 쪽들;
  var step = Math.max(1, Math.floor(n / k)), out = [];
  for (var j = 0; j < n && out.length < k; j += step) out.push(쪽들[j]);
  return out;
}

async function 판형살피기(파일) {
  if (판형기억[파일] !== undefined) return 판형기억[파일];
  var 키 = "옛한글OCR:판형:" + 파일;
  try {
    var 적힌 = JSON.parse(localStorage.getItem(키));
    if (적힌 && 적힌.판 === 판형판) return (판형기억[파일] = 적힌.값);
  } catch (e) { /* 저장소를 못 쓰면 매번 살핌 */ }
  await 주소틀얻기(파일);
  var n = 쪽수[파일] || 0;
  if (!n) return (판형기억[파일] = 1);          // 쪽 수를 모르면 한 단
  var 가름쪽 = 고르게(n, 12), 단쪽 = 고르게(n, 8);
  var 모두 = 가름쪽.concat(단쪽.filter(function (p) { return 가름쪽.indexOf(p) < 0; }));
  var A = window.옛한글읽기, 가름 = {}, 단 = {};
  for (var i = 0; i < 모두.length; i++) {
    알림("처음 보는 문헌이라 판형을 살피는 중… (" + (i + 1) + "/" + 모두.length
         + "쪽, 이 파일은 처음 한 번만)");
    var p = 모두[i];
    try {
      var g = A.그림읽기(await 스캔가져오기(파일, p));
      if (가름쪽.indexOf(p) >= 0) 가름[p] = A.가름줄측정(g);
      if (단쪽.indexOf(p) >= 0) 단[p] = A.단측정(g);
    } catch (e) {
      console.warn("판형 살피기 — " + p + "쪽을 못 받았습니다", e);
      가름[p] = null; 단[p] = null;           // 못 잰 쪽
    }
  }
  var 값 = A.판형정하기(가름쪽.map(function (p) { return 가름[p] || null; }),
                       단쪽.map(function (p) { return 단[p] || null; }));
  판형기억[파일] = 값;
  try { localStorage.setItem(키, JSON.stringify({ 판: 판형판, 값: 값 })); } catch (e) { }
  return 값;
}

function 판형글(값) {
  return Array.isArray(값) ? (값.length + 1) + "단(가로줄로 가름)" : 값 + "단";
}

// ── 단추를 눌렀을 때 ─────────────────────────────────────────────────
async function 읽기시작() {
  var 상자 = 편집상자();
  var 쪽 = 지금쪽();
  if (!상자 || !쪽) { 알림("편집 창을 못 찾았습니다."); return; }
  단추.disabled = true;
  try {
    await 준비();
    var 문 = 문헌설정(쪽.파일);
    var 살핀판형 = 문.슬러그 ? null : await 판형살피기(쪽.파일);
    알림("스캔을 받는 중…");
    var im = await 스캔가져오기(쪽.파일, 쪽.쪽);
    var g = window.옛한글읽기.그림읽기(im);

    알림("읽는 중… 20~30초 걸립니다 (화면이 잠깐 멎을 수 있습니다)");
    var t0 = performance.now();
    var r = await window.옛한글읽기.한쪽(모델, g, 문.슬러그,
      살핀판형 === null ? {} : { 문헌설정: { 단: 살핀판형 } });
    var 초 = ((performance.now() - t0) / 1000).toFixed(1);

    if (!r.글월) {
      알림("판정: " + r.판정.등급 + " — " + (r.판정.까닭.join(" · ") || "열을 못 찾았습니다")
           + ". 넣지 않았습니다.");
      return;
    }
    // ⚠ '못씀' 이면 넣지 않음 — 지우고 다시 치게 되므로. 아래에 보여 주고 넣을지는 사람이
    var 칠함 = false;
    if (r.판정.등급 !== "못씀") {
      // 편집 상자에는 표시 없는 글월(`⟪⟫` 가 저장되면 안 됨). 표시는 상자 뒤에 칠함
      넣기(상자, r.글월);
      칠함 = 표시깔기(상자, r.교정용);
    }
    // 칠했으면 위쪽 칸은 치움. 못 칠했을 때만(못씀 · 구문 강조) 띄움
    if (칠함) 교정칸치우기();
    else 보이기(r, r.판정.등급 === "못씀" ? 상자 : null);
    알림((r.판정.등급 === "못씀" ? "판정: 못씀 — 넣지 않았습니다. 처음부터 치는 편이 빠릅니다"
                              : "판정: " + r.판정.등급)
         + (칠함 ? " · 노란 자리가 확신 낮은 글자입니다(고치면 칠이 사라지고, 칠은 저장되지 않습니다)" : "")
         + (문.슬러그 ? "" : " · 처음 보는 문헌 — 판형은 쪽을 살펴 " + 판형글(살핀판형)
                           + "으로 정했고 자간은 기본값입니다")
         + " · 확신 낮은 글자 " + (r.표시비 * 100).toFixed(0) + "%"
         + " · " + r.상자수 + "상자 " + 초 + "초(" + 실행기[0] + ")"
         + (r.판정.까닭.length ? " · " + r.판정.까닭.join(" · ") : ""));
  } catch (e) {
    알림("멈췄습니다: " + e.message);
    console.error(e);
  } finally {
    단추.disabled = false;
  }
}

function 넣기(상자, 글) {
  상자.value = 글;
  // CodeMirror·2017 편집기가 바뀐 것을 알아채게
  상자.dispatchEvent(new Event("input", { bubbles: true }));
  상자.dispatchEvent(new Event("change", { bubbles: true }));
}

// ── 편집 상자 안에 표시 깔기 ─────────────────────────────────────────
// 편집 상자 뒤에 같은 모양의 판을 깔고 확신 낮은 자리의 바탕만 칠함. 글자는 상자 것이라 칠은 저장되지 않음
// 칠한 자리를 고치면 그 칠은 사라지고, 나머지는 따라 밀림(`따라가기`)
// ⚠ CodeMirror(구문 강조) 위에는 칠하지 않음 — 위쪽 칸으로(`보이기`)
var 깔개 = null;

/** `⟪…⟫` 가 든 교정용 글월 → 표시를 뺀 글월에서의 [시작, 끝) 목록 */
function 표시자리(교정용) {
  var 자리 = [], n = 0, s = -1;
  for (var i = 0; i < 교정용.length; i++) {
    var c = 교정용.charAt(i);
    if (c === "⟪") s = n;
    else if (c === "⟫") { if (s >= 0 && n > s) 자리.push([s, n]); s = -1; }
    else n++;
  }
  return 자리;
}

function 보이나(상자) {
  return 상자.isConnected && 상자.offsetParent !== null
      && getComputedStyle(상자).visibility !== "hidden";
}

// 판이 편집 상자와 같은 자리에서 줄을 바꾸게 베낄 모양들
var 베낄모양 = ["paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
  "fontFamily", "fontSize", "fontWeight", "fontStyle", "fontVariant", "fontStretch",
  "fontKerning", "fontFeatureSettings", "lineHeight", "letterSpacing", "wordSpacing",
  "textIndent", "textTransform", "tabSize", "whiteSpace", "overflowWrap", "wordBreak",
  "direction", "textAlign"];

/** 편집 상자에 표시 깔기. 깔았으면 true (못 깔면 위쪽 칸으로) */
function 표시깔기(상자, 교정용) {
  표시걷기();
  if (!보이나(상자)) return false;                 // 구문 강조가 켜져 편집 상자가 숨음
  var 자리 = 표시자리(교정용);
  if (상자.value !== 교정용.replace(/[⟪⟫]/g, "")) return false;   // 넣은 글과 안 맞으면 칠하지 않음

  var 판 = document.createElement("div");
  판.id = "옛한글OCR-깔개";
  판.setAttribute("aria-hidden", "true");
  상자.parentNode.insertBefore(판, 상자);
  var 바탕 = getComputedStyle(상자).backgroundColor;
  var 옛모양 = { position: 상자.style.position, backgroundColor: 상자.style.backgroundColor };
  // 판보다 위에 그려지게 (relative 는 제자리 그대로)
  if (getComputedStyle(상자).position === "static") 상자.style.position = "relative";
  상자.style.backgroundColor = "transparent";

  깔개 = { 상자: 상자, 판: 판, 자리: 자리, 기준: 상자.value, 옛모양: 옛모양, 바탕: 바탕 };

  function 모양맞추기() {
    if (!보이나(상자)) { 판.style.display = "none"; return; }
    var cs = getComputedStyle(상자), st = 판.style;
    st.display = "block";
    베낄모양.forEach(function (k) { st[k] = cs[k]; });
    st.position = "absolute";
    st.top = (상자.offsetTop + 상자.clientTop) + "px";
    st.left = (상자.offsetLeft + 상자.clientLeft) + "px";
    st.width = 상자.clientWidth + "px";           // 스크롤 막대를 뺀 폭
    st.height = 상자.clientHeight + "px";
    st.boxSizing = "border-box";
    st.margin = "0"; st.border = "0";
    st.overflow = "hidden";
    st.color = "transparent";
    st.pointerEvents = "none";
    st.background = 바탕;
    스크롤맞추기();
  }
  function 스크롤맞추기() {
    판.scrollTop = 상자.scrollTop;
    판.scrollLeft = 상자.scrollLeft;
  }
  function 그리기() {
    var t = 깔개.기준, p = 0;
    판.textContent = "";
    깔개.자리.forEach(function (z) {
      if (z[0] > p) 판.appendChild(document.createTextNode(t.slice(p, z[0])));
      var m = document.createElement("mark");
      m.style.cssText = "background:rgba(255,190,0,.45);color:transparent;"
                      + "padding:0;margin:0;border-radius:2px";
      m.textContent = t.slice(z[0], z[1]);
      판.appendChild(m);
      p = z[1];
    });
    // 끝의 줄바꿈도 높이를 갖게 (div 는 마지막 줄바꿈을 무시)
    판.appendChild(document.createTextNode(t.slice(p) + "\n​"));
    스크롤맞추기();
  }
  // 고친 만큼 칠 옮기기 — 고친 구간과 겹친 칠은 지우고, 뒤의 칠은 밈
  function 따라가기() {
    var 새 = 상자.value, 옛 = 깔개.기준;
    if (새 === 옛) return;
    var n = Math.min(옛.length, 새.length), a = 0, b = 0;
    while (a < n && 옛.charCodeAt(a) === 새.charCodeAt(a)) a++;
    while (b < n - a && 옛.charCodeAt(옛.length - 1 - b) === 새.charCodeAt(새.length - 1 - b)) b++;
    var 옛끝 = 옛.length - b, 차 = 새.length - 옛.length;
    깔개.자리 = 깔개.자리
      .filter(function (z) { return z[1] <= a || z[0] >= 옛끝; })
      .map(function (z) { return z[0] >= 옛끝 ? [z[0] + 차, z[1] + 차] : z; });
    깔개.기준 = 새;
    그리기();
  }

  상자.addEventListener("input", 따라가기);
  상자.addEventListener("scroll", 스크롤맞추기);
  // ⚠ 도구 모음은 input 없이 글을 바꾸고, 구문 강조를 켜고 끄면 상자가 숨었다 나타남 — 그래서 0.5초마다 대 봄
  var 시계 = setInterval(function () {
    if (!상자.isConnected) { 표시걷기(); return; }
    따라가기(); 모양맞추기();
  }, 500);
  var 관찰 = window.ResizeObserver ? new ResizeObserver(모양맞추기) : null;
  if (관찰) 관찰.observe(상자);
  window.addEventListener("resize", 모양맞추기);

  깔개.끝내기 = function () {
    상자.removeEventListener("input", 따라가기);
    상자.removeEventListener("scroll", 스크롤맞추기);
    clearInterval(시계);
    if (관찰) 관찰.disconnect();
    window.removeEventListener("resize", 모양맞추기);
  };
  모양맞추기();
  그리기();
  return true;
}

function 표시걷기() {
  if (!깔개) return;
  깔개.끝내기();
  깔개.판.remove();
  깔개.상자.style.position = 깔개.옛모양.position;
  깔개.상자.style.backgroundColor = 깔개.옛모양.backgroundColor;
  깔개 = null;
}

function 교정칸치우기() {
  var 칸 = document.getElementById("옛한글OCR-교정");
  if (칸) 칸.remove();
}

/** 편집 상자에 칠하지 못할 때('못씀' · 구문 강조) 위쪽 칸에 보이기 */
function 보이기(r, 넣을상자) {
  var 칸 = document.getElementById("옛한글OCR-교정");
  if (!칸) {
    칸 = document.createElement("div");
    칸.id = "옛한글OCR-교정";
    칸.style.cssText = "margin:8px 0;padding:10px 12px;border:1px solid #c8ccd1;"
      + "background:#fff;border-radius:2px;line-height:2;font-size:15px;"
      + "max-height:16em;overflow:auto;white-space:pre-wrap";   // 열마다 한 줄
    // ⚠ 단추 줄은 flex 라 그 안이 아니라 다음에 놓음
    var 줄 = document.getElementById("옛한글OCR-줄");
    줄.parentNode.insertBefore(칸, 줄.nextSibling);
  }
  칸.textContent = "";
  var 머리 = document.createElement("div");
  머리.style.cssText = "font-size:12px;color:#54595d;margin-bottom:6px";
  머리.textContent = 넣을상자
    ? "이 쪽은 '못씀' 이라 편집 상자에 넣지 않았습니다. 아래가 읽은 것입니다 —"
      + " 처음부터 치는 편이 대개 빠릅니다."
    : "구문 강조가 켜져 있어 편집 상자 안에는 칠하지 못했습니다. 끄고 다시 읽으면"
      + " 편집 상자에 바로 표시됩니다. 확신이 낮아 먼저 볼 자리 —";
  칸.appendChild(머리);
  if (넣을상자) {                    // 그래도 넣을지는 사람이
    var 그래도 = document.createElement("button");
    그래도.type = "button";
    그래도.className = "cdx-button";
    그래도.style.cssText = "margin:0 0 8px";
    그래도.textContent = "그래도 편집 상자에 넣기";
    그래도.addEventListener("click", function () {
      넣기(넣을상자, r.글월);
      if (표시깔기(넣을상자, r.교정용)) { 교정칸치우기(); return; }
      그래도.disabled = true;
      그래도.textContent = "넣었습니다";
    });
    칸.appendChild(그래도);
  }
  // ⟪…⟫ 로 갈라 칠하기
  var 조각 = r.교정용.split(/(⟪[^⟫]*⟫)/);
  for (var i = 0; i < 조각.length; i++) {
    var s = 조각[i];
    if (!s) continue;
    if (s.charAt(0) === "⟪") {
      var b = document.createElement("mark");
      b.style.cssText = "background:#fee7a0;padding:0 1px";
      b.textContent = s.slice(1, -1);
      칸.appendChild(b);
    } else {
      칸.appendChild(document.createTextNode(s));
    }
  }
}

// ── 화면에 붙이기 ────────────────────────────────────────────────────
function 세우기() {
  if (!지금쪽() || !편집상자()) return;
  if (document.getElementById("옛한글OCR-줄")) return;
  var 줄 = document.createElement("div");
  줄.id = "옛한글OCR-줄";
  줄.style.cssText = "margin:8px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap";
  단추 = document.createElement("button");
  단추.type = "button";
  단추.className = "cdx-button";
  단추.textContent = "옛한글 OCR 로 읽기";
  단추.addEventListener("click", 읽기시작);
  상태 = document.createElement("span");
  상태.style.cssText = "font-size:13px;color:#54595d";
  상태.textContent = "";
  줄.appendChild(단추);
  줄.appendChild(상태);
  var 상자 = 편집상자();
  상자.parentNode.insertBefore(줄, 상자);

  var 안내 = document.createElement("div");
  안내.style.cssText = "font-size:12px;color:#72777d;flex-basis:100%";
  안내.textContent = "결과를 편집 상자에 넣기만 합니다. 저장은 반드시 눈으로 보고 직접 누르세요.";
  줄.appendChild(안내);
}

if (window.mw && mw.loader) {
  mw.loader.using(["mediawiki.api"]).then(function () {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", 세우기);
    } else {
      세우기();
    }
  });
}
})();
