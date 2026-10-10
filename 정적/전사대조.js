/*
 * 전사대조 — 위키문헌 '페이지:' 편집 창에서 **이미 전사된 글**을 그 쪽 스캔과 맞대어, 전사문이 틀렸을 만한 자리를 편집 상자 안에 칠하는 소도구.
 *
 * Toolforge 서버(`https://<도구 주소>/compare.js`)가 내줌:
 *   mw.loader.load("https://<도구 주소>/ocr.js");        ← 인식 (전사)
 *   mw.loader.load("https://<도구 주소>/compare.js");    ← 교정 (전사대조) — 이 줄을 더하면 켜짐
 *
 * 셈은 전부 서버(`근원/부품/대조.py`) — 이 파일은 화면(칠하기 · 후보 목록 · 바꾸기)만.
 * 서버가 내주는 이 파일의 맨 앞 줄은 `window.옛한글OCR서버` 를 채움.
 */
(function (전역) {
"use strict";

// ════════════════════════════════════════════════════════════════════
//  화면 — 위키문헌 편집 창 (칠하기 · 목록 · 바꾸기)
// ════════════════════════════════════════════════════════════════════
if (typeof document === "undefined") return;

var 상태, 단추, 판, 깔개 = null, 후보들 = [], 어긋남보기 = false, 끝난것보기 = false;
// 합의 = 다르게 한 번 더 잘라도 남은 것(`한쪽` 의 합의). 안 남은 것은 자르기 실수일 때가 많아 접어 둔다
function 확실(c) { return c.합의 !== false && c.갈래 !== "빠짐" && c.갈래 !== "더들어감"; }
function 보일것(c) { return 어긋남보기 || 확실(c); }
function 바꿀수(c) { return (c.갈래 === "바뀜" || c.갈래 === "모르는자모") && c.스캔; }

var 이름 = { "바뀜": "글자가 다름", "모르는자모": "모르는 자모", "깨진글자": "깨진 글자", "누락": "전사문에 글자 누락 의심", "빠짐": "스캔에 글자가 더 있음", "더들어감": "전사문에 글자가 더 있음" };
var 색 = { "바뀜": "rgba(255,80,80,.40)", "모르는자모": "rgba(255,160,0,.40)", "깨진글자": "rgba(170,80,255,.38)", "누락": "rgba(80,140,255,.35)", "빠짐": "rgba(80,140,255,.35)", "더들어감": "rgba(80,140,255,.35)" };

function 알림(t) { if (상태) 상태.textContent = t; }

// ⚠ 순서대로 편집(`prp_editinsequence`)은 쪽을 옮겨도 `mw.config` 를 안 바꾸고 `location.hash` 에
//   "페이지:파일/쪽" 만 적음 → 그때는 hash 를 먼저 봄 (OCR 소도구 `순서편집제목` 과 같음)
function 순서편집제목() {
  if (!/[?&]prp_editinsequence=(1|true|yes|on)(&|$)/i.test(location.search)) return null;
  var h;
  try { h = decodeURIComponent(location.hash.slice(1)); } catch (e) { return null; }
  var i = h.indexOf(":");
  if (i < 0) return null;
  var 앞 = h.slice(0, i).replace(/_/g, " ");
  var 이름공간 = (mw.config.get("wgFormattedNamespaces") || {})[mw.config.get("wgNamespaceNumber")];
  if (앞 !== "Page" && 앞 !== 이름공간) return null;
  return h.slice(i + 1).replace(/_/g, " ");
}

function 지금쪽() {
  var cfg = mw.config.get(["wgCanonicalNamespace", "wgTitle", "wgAction"]);
  if (cfg.wgCanonicalNamespace !== "Page") return null;
  if (cfg.wgAction !== "edit" && cfg.wgAction !== "submit") return null;
  var m = /^(.*)\/(\d+)$/.exec(순서편집제목() || cfg.wgTitle);
  return m ? { 파일: m[1], 쪽: parseInt(m[2], 10) } : null;
}

function 편집상자() {
  return document.querySelector("#wpTextbox1") || document.querySelector("textarea[name='wpTextbox1']");
}

function 보이나(상자) {
  return 상자.isConnected && 상자.offsetParent !== null && getComputedStyle(상자).visibility !== "hidden";
}

// ── 디버그 로그 — 잘 안 맞은 쪽을 알릴 때 복사해 붙일 글(마지막 한 번만). OCR 소도구 `로그단추` 와 같은 모양 ──
var 로그 = { 글: "", 칸: null };

function 시각글(d) {
  function p(n) { return String(n).padStart(2, "0"); }
  var 차 = -d.getTimezoneOffset();
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " "
       + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds())
       + " (UTC" + (차 >= 0 ? "+" : "-") + p(Math.floor(Math.abs(차) / 60)) + ":" + p(Math.abs(차) % 60) + ")";
}

function 로그머리(쪽, 언제) {
  var c = mw.config.get(["wgServer", "wgArticlePath", "wgFormattedNamespaces", "wgNamespaceNumber", "wgCurRevisionId"]);
  var 제목 = 쪽 ? ((c.wgFormattedNamespaces || {})[c.wgNamespaceNumber] || "페이지") + ":" + 쪽.파일 + "/" + 쪽.쪽 : "(못 찾음)";
  return [
    ["도구", "교정 (전사대조)"],
    ["모델 · 단", 선택글()],
    ["시각", 시각글(언제)],
    ["문서", 제목],
    ["주소", 쪽 ? (c.wgServer || location.origin) + (c.wgArticlePath || "/wiki/$1").replace("$1", encodeURIComponent(제목.replace(/ /g, "_")).replace(/%2F/g, "/").replace(/%3A/g, ":")) : ""],
    ["판", c.wgCurRevisionId || "(새 문서)"],
    ["실행", "서버 " + 서버],
    ["구문 강조", 편집상자() && !보이나(편집상자()) ? "켜짐" : "꺼짐"],
    ["브라우저", navigator.userAgent],
  ];
}

// ── 공용 도구 줄 — 인식 · 교정 · 영역 지정 단추를 한 줄에 모으고, 옆의 '설정' 메뉴에 모델 · 단을 둠 ──
// ⚠ `소도구.js` 와 `전사대조.js` 에 **같은 꼴**로 들어 있음 — 한쪽을 고치면 다른 쪽도(어느 쪽이 먼저 떠도 한 줄을 같이 씀)
// 고른 값은 `window.옛한글OCR공용.모델()` · `.단()` 으로 읽음 — 모델 "hangul"(근대 순한글, 기본) | "hanmun"(근대 국한문, 서버판만) ·
// 단 null(자동 — 파일을 살펴 정한 값) | 1~5
function 공용도구() {
  var 옛 = window.옛한글OCR공용;
  if (옛 && 옛.뿌리.isConnected) return 옛;
  var 서버주소 = window.옛한글OCR서버 || "";
  if (서버주소 && 서버주소.charAt(서버주소.length - 1) !== "/") 서버주소 += "/";
  var 저장 = function (이름, 값) {          // 쪽을 옮겨도 · 새로 고쳐도 고른 값을 기억(막힌 브라우저면 그냥 기억 없이)
    try {
      if (값 === undefined) return localStorage.getItem("옛한글OCR:" + 이름);
      localStorage.setItem("옛한글OCR:" + 이름, 값);
    } catch (e) {}
    return null;
  };
  var 만들기 = function (태그, 글, 꼴) {
    var e = document.createElement(태그);
    if (글) e.textContent = 글;
    if (꼴) e.style.cssText = 꼴;
    return e;
  };

  var 뿌리 = 만들기("div", "", "margin:8px 0");
  뿌리.id = "옛한글OCR-도구";
  var 줄 = 만들기("div", "", "display:flex;gap:10px;align-items:center;flex-wrap:wrap");
  var 로그묶음 = 만들기("span", "", "margin-left:auto;order:9;display:inline-flex;gap:10px");
  줄.appendChild(로그묶음);

  var 설정단추 = 만들기("button", "설정 ▾");
  설정단추.type = "button";
  설정단추.className = "cdx-button";
  설정단추.style.order = "4";
  설정단추.title = "모델 · 몇 단짜리인지 고르기";
  var 칸 = 만들기("div", "", "display:none;margin:6px 0 0;padding:8px 12px;border:1px solid #c8ccd1;"
                   + "background:#f8f9fa;border-radius:2px;font-size:13px;color:#202122");
  줄.appendChild(설정단추);

  var 항목 = function (이름, 값들, 도움말) {
    var 행 = 만들기("div", "", "display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin:4px 0");
    행.appendChild(만들기("label", 이름, "min-width:3.2em;font-weight:bold"));
    var 고름 = 만들기("select", "", "padding:2px 6px");
    값들.forEach(function (v) {
      var o = document.createElement("option");
      o.value = v[0]; o.textContent = v[1];
      고름.appendChild(o);
    });
    행.appendChild(고름);
    행.appendChild(만들기("span", 도움말, "font-size:12px;color:#72777d"));
    칸.appendChild(행);
    return 고름;
  };
  // 띄어쓰기 자동 감지 — 종이에 띄어쓰기가 없는 문헌에서 헛띄움이 생기면 끔(인식에만 해당)
  var 띄움행 = 만들기("div", "", "display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;margin:4px 0");
  var 띄움칸 = document.createElement("input");
  띄움칸.type = "checkbox";
  띄움칸.checked = true;
  var 띄움글 = 만들기("label", "", "display:inline-flex;gap:6px;align-items:center");
  띄움글.appendChild(띄움칸);
  띄움글.appendChild(document.createTextNode("띄어쓰기 자동 감지"));
  띄움행.appendChild(만들기("span", "", "min-width:3.2em"));
  띄움행.appendChild(띄움글);
  띄움행.appendChild(만들기("span", "인식 결과에 띄어쓰기를 넣습니다. 띄어쓰기 없이 찍은 문헌에서 엉뚱한 곳이 띄어지면 끄세요.", "font-size:12px;color:#72777d"));
  var 모델선택 = 항목("모델", [["hangul", "근대 순한글"], ["hanmun", "근대 국한문"]],
                    "한글로만 된 문헌일 경우 순한글을 선택하는 것이 정확도가 높습니다.");
  var 단선택 = 항목("단", [["auto", "자동"], ["1", "1단"], ["2", "2단"], ["3", "3단"], ["4", "4단"], ["5", "5단"]],
                  "자동을 선택하면 파일을 처음 열 때 쪽을 몇 장 받아 살펴 정합니다.");

  var 한문칸 = 모델선택.querySelector("option[value=hanmun]");
  var 요약 = function () {
    var 글 = [];
    if (모델선택.value !== "hangul") 글.push("국한문");
    if (단선택.value !== "auto") 글.push(단선택.value + "단");
    if (!띄움칸.checked) 글.push("띄어쓰기 끔");
    설정단추.textContent = "설정 ▾" + (글.length ? " (" + 글.join(" · ") + ")" : "");
    설정단추.setAttribute("aria-expanded", 칸.style.display !== "none" ? "true" : "false");
  };
  // 서버에 국한문 모델 파일이 없으면 못 고르게(`/api/health` 로 확인)
  var 국한문가능 = function (됨) {
    한문칸.disabled = !됨;
    한문칸.textContent = "근대 국한문" + (됨 ? "" : " — 이 서버에는 없음");
    if (!됨 && 모델선택.value === "hanmun") 모델선택.value = "hangul";
    요약();
  };
  var 옛모델 = 저장("모델"), 옛단 = 저장("단");
  if (옛모델 === "hanmun") 모델선택.value = "hanmun";
  if (옛단 && 단선택.querySelector("option[value='" + 옛단 + "']")) 단선택.value = 옛단;
  fetch(서버주소 + "api/health").then(function (r) { return r.json(); }).then(function (h) {
    if (h && h.모델들 && !h.모델들.hanmun) 국한문가능(false);
  }).catch(function () {});
  모델선택.addEventListener("change", function () { 저장("모델", 모델선택.value); 요약(); });
  단선택.addEventListener("change", function () { 저장("단", 단선택.value); 요약(); });
  칸.appendChild(띄움행);
  if (저장("띄움") === "끔") 띄움칸.checked = false;
  띄움칸.addEventListener("change", function () { 저장("띄움", 띄움칸.checked ? "켬" : "끔"); 요약(); });
  설정단추.addEventListener("click", function () {
    칸.style.display = 칸.style.display === "none" ? "block" : "none";
    요약();
  });
  요약();

  뿌리.appendChild(줄);
  뿌리.appendChild(칸);
  var 상자 = 편집상자();
  상자.parentNode.insertBefore(뿌리, 상자);
  return (window.옛한글OCR공용 = {
    뿌리: 뿌리, 줄: 줄, 로그묶음: 로그묶음,
    모델: function () { return (모델선택.value === "hanmun" && !한문칸.disabled) ? "hanmun" : "hangul"; },
    단: function () { return 단선택.value === "auto" ? null : parseInt(단선택.value, 10); },
    띄움: function () { return 띄움칸.checked; },
  });
}

/** 살핀 값(자동으로 정한 설정)의 단만 사람이 고른 값으로 — 1단 = 1, N단 = 가름줄 높이 목록(서버 `단바꾸기` · `읽기.js` 의 가름줄 판형과 같은 꼴). 자동(null)이면 그대로 */
function 단바꾸기(살핀, 단) {
  if (!단 || !살핀) return 살핀;
  var s = {};
  for (var k in 살핀) s[k] = 살핀[k];
  s.단 = 단 === 1 ? 1 : Array.apply(null, Array(단 - 1)).map(function (_, i) { return (i + 1) / 단; });
  return s;
}

function 단글(단) { return 단 ? 단 + "단(직접 고름)" : "자동"; }

function 선택글() {
  var 공 = window.옛한글OCR공용;
  return 공 ? (공.모델() === "hanmun" ? "근대 국한문" : "근대 순한글") + " · 단 " + 단글(공.단()) + " · 띄어쓰기 " + (공.띄움() ? "자동 감지" : "끔") : "";
}

function 로그쓰기(줄들) {
  로그.글 = "[옛한글 OCR 디버그 로그]\n" + 줄들
    .filter(function (v) { return v[1] !== undefined && v[1] !== null && v[1] !== ""; })
    .map(function (v) { return v[0] + ": " + v[1]; }).join("\n");
  if (로그.칸) 로그.칸.글.value = 로그.글;
}

function 초글(ms) { return (ms / 1000).toFixed(1) + "초"; }

/** 단추 줄 오른쪽 끝의 작은 '교정 로그' — 누르면 줄 아래에 펼침. `공` = `공용도구()` */
function 로그단추(공) {
  var 고리 = document.createElement("a");
  고리.href = "#";
  고리.setAttribute("role", "button");
  고리.textContent = "교정 로그";
  고리.title = "마지막으로 맞댄 쪽의 기록(쪽 · 시간 · 일치율 …) — 잘 안 맞은 쪽을 알릴 때 복사해 붙여 주세요";
  고리.style.cssText = "font-size:11px;color:#a2a9b1;text-decoration:none";
  var 칸 = document.createElement("div");
  칸.style.cssText = "flex-basis:100%;order:10;display:none;font-size:12px;color:#54595d";
  var 글 = document.createElement("textarea");
  글.readOnly = true;
  글.rows = 12;
  글.style.cssText = "width:100%;box-sizing:border-box;font-family:monospace;font-size:12px;"
                  + "white-space:pre-wrap;word-break:break-all;height:18em;resize:vertical;"
                  + "background:#f8f9fa;border:1px solid #c8ccd1;padding:4px 6px";
  var 아래 = document.createElement("div");
  아래.style.cssText = "display:flex;gap:8px;align-items:center;margin-top:4px";
  var 복사 = document.createElement("button");
  복사.type = "button";
  복사.className = "cdx-button";
  복사.style.cssText = "font-size:12px;min-height:0;padding:2px 8px";
  복사.textContent = "복사";
  var 알림말 = document.createElement("span");
  복사.addEventListener("click", function () {
    var 됨 = function () { 알림말.textContent = "복사했습니다."; };
    var 손으로 = function () {
      글.focus(); 글.select();
      try { document.execCommand("copy"); 됨(); } catch (e) { 알림말.textContent = "Ctrl+C 로 복사해 주세요(골라 두었습니다)."; }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(글.value).then(됨, 손으로);
    else 손으로();
  });
  아래.appendChild(복사);
  아래.appendChild(알림말);
  칸.appendChild(글);
  칸.appendChild(아래);
  고리.addEventListener("click", function (e) {
    e.preventDefault();
    var 열림 = 칸.style.display === "none";
    칸.style.display = 열림 ? "block" : "none";
    고리.textContent = 열림 ? "교정 로그 닫기" : "교정 로그";
    글.value = 로그.글 || "아직 기록이 없습니다 — '교정 (전사대조)' 를 한 번 누른 뒤에 보세요.";
    알림말.textContent = "";
  });
  공.로그묶음.appendChild(고리);
  공.줄.appendChild(칸);           // 줄이 flex-wrap 이라 폭 100% 로 다음 줄에 펼쳐짐
  로그.칸 = { 글: 글 };
}

/** 맞댄 결과 · 걸린 시간 */
function 로그본문(살핀, 답, 때, 처음) {
  var 줄 = [];
  if (살핀) 줄.push(["판형 살핀 값", (Array.isArray(살핀.단) ? (살핀.단.length + 1) + "단(가로줄)" : (살핀.단 || 1) + "단")
                       + (살핀.자간비 ? " · 자간비 " + 살핀.자간비.toFixed(3) : " · 자간비 없음(기본값)")
                       + (살핀.판짜임 ? " · 판짜임 " + JSON.stringify(살핀.판짜임) : "")]);
  if (답 && !답.사유) {
    var 셈 = {};
    (답.후보 || []).forEach(function (c) {
      var k = (이름[c.갈래] || c.갈래) + (c.합의 === false ? "(접힘)" : "");
      셈[k] = (셈[k] || 0) + 1;
    });
    줄.push(["일치율", (답.일치 * 100).toFixed(1) + "%" + (답.흔들림 ? " — 흔들림(맞대기가 잘 안 됨)" : "")]);
    줄.push(["맞대기", "고른 기하 " + (답.기하 || "?") + " · 편 제목 " + (답.제목 ? "본문에 찍힘" : "안 찍힘")
             + (답.큰빼기 ? " · 큰 활자 뺌" : "") + (답.합의본 && 답.합의본.length ? " · 다시 자른 판 " + 답.합의본.join(",") : "")]);
    줄.push(["글자 · 열", (답.글자수 || "?") + "자 · 열 " + (답.열수 || "?") + "개 · 흔들린 열 " + (답.흔들린열 || 0)]);
    줄.push(["후보", Object.keys(셈).length ? Object.keys(셈).map(function (k) { return k + " " + 셈[k]; }).join(" · ") : "없음"]);
    줄.push(["문헌 설정", 답.아는문헌 === false ? "없음 — 이 쪽 그림으로 자간을 잼" : "파일마다 잰 값"]);
    if (답.debug) {
      줄.push(["서버 진단", "그림 " + (답.debug.그림해시 || "?") + " · " +
        (답.debug.크기 ? 답.debug.크기.join("×") : "?") + " · 캐시 " + (답.debug.캐시 || "?")]);
      줄.push(["서버 판", (답.debug.주소 || "주소 없음") + " · " + JSON.stringify(답.debug.판 || {})]);
      줄.push(["서버 OCR", (답.debug.OCR글자수 == null ? "개수 없음" : 답.debug.OCR글자수 + "자") +
        " · 해시 " + (답.debug.OCR해시 || "?") +
        (답.debug.OCR미리보기 ? " · 앞 80자 " + 답.debug.OCR미리보기 : "")]);
      if (답.debug.OCR전체 != null) 줄.push(["서버 OCR 전체", 답.debug.OCR전체]);
      if (답.debug.시도기록) 줄.push(["맞대기 시도 기록", JSON.stringify(답.debug.시도기록)]);
      var 상 = 답.debug.상세 || {};
      if (상.전사글자) 줄.push(["서버 전사 글자", 상.전사글자.join("")]);
      if (상.불일치구간) 줄.push(["불일치 구간", JSON.stringify(상.불일치구간)]);
      if (상.열) 줄.push(["열별 진단", JSON.stringify(상.열)]);
      if (상.기하) 줄.push(["선택 기하 상세", JSON.stringify(상.기하)]);
      if (상.상자) 줄.push(["상자별 OCR 진단", JSON.stringify(상.상자)]);
    } else {
      줄.push(["서버 진단", "없음 — 구형 서버 응답"]);
    }
  }
  var 시간 = Object.keys(때).map(function (k) { return k + " " + 초글(때[k]); });
  시간.push("전체 " + 초글(performance.now() - 처음));
  줄.push(["걸린 시간", 시간.join(" · ")]);
  return 줄;
}

// ── 편집 상자에 칠하기 (브라우저판 `표시깔기` 와 같은 방법 — 상자 뒤에 같은 글꼴의 판을 깔고 바탕만 칠함) ──
var 베낄모양 = ["paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
  "fontFamily", "fontSize", "fontWeight", "fontStyle", "fontVariant", "fontStretch",
  "fontKerning", "fontFeatureSettings", "lineHeight", "letterSpacing", "wordSpacing",
  "textIndent", "textTransform", "tabSize", "whiteSpace", "overflowWrap", "wordBreak",
  "direction", "textAlign"];

function 모양베끼기(상자, 판) {
  var cs = getComputedStyle(상자), st = 판.style;
  베낄모양.forEach(function (k) { st[k] = cs[k]; });
  st.position = "absolute";
  st.top = (상자.offsetTop + 상자.clientTop) + "px";
  st.left = (상자.offsetLeft + 상자.clientLeft) + "px";
  st.width = 상자.clientWidth + "px";
  st.height = 상자.clientHeight + "px";
  st.boxSizing = "border-box";
  st.margin = "0"; st.border = "0"; st.overflow = "hidden";
  st.color = "transparent"; st.pointerEvents = "none";
}

function 깔기(상자) {
  걷기();
  if (!보이나(상자)) return false;
  var 바닥 = document.createElement("div");
  바닥.id = "전사대조-깔개";
  바닥.setAttribute("aria-hidden", "true");
  상자.parentNode.insertBefore(바닥, 상자);
  var 바탕 = getComputedStyle(상자).backgroundColor;
  var 옛모양 = { position: 상자.style.position, backgroundColor: 상자.style.backgroundColor };
  if (getComputedStyle(상자).position === "static") 상자.style.position = "relative";
  상자.style.backgroundColor = "transparent";
  깔개 = { 상자: 상자, 판: 바닥, 기준: 상자.value, 옛모양: 옛모양 };

  function 맞추기() {
    if (!보이나(상자)) { 바닥.style.display = "none"; return; }
    바닥.style.display = "block";
    모양베끼기(상자, 바닥);
    바닥.style.background = 바탕;
    바닥.scrollTop = 상자.scrollTop; 바닥.scrollLeft = 상자.scrollLeft;
  }
  깔개.그리기 = function () {
    var t = 깔개.기준, p = 0;
    바닥.textContent = "";
    후보들.filter(function (c) { return !c.끝남 && 보일것(c); })
      .sort(function (a, b) { return a.시작 - b.시작; })
      .forEach(function (c) {
        if (c.시작 < p) return;                     // 겹치면 앞의 것만
        if (c.시작 > p) 바닥.appendChild(document.createTextNode(t.slice(p, c.시작)));
        var m = document.createElement("mark");
        var 끝 = Math.max(c.끝, c.시작 + 1);
        m.style.cssText = "color:transparent;padding:0;margin:0;border-radius:2px;background:" + 색[c.갈래]
          + (c === 고른것 ? ";outline:2px solid #d33" : "");
        m.textContent = t.slice(c.시작, 끝);
        바닥.appendChild(m);
        p = 끝;
      });
    바닥.appendChild(document.createTextNode(t.slice(p) + "\n​"));
    바닥.scrollTop = 상자.scrollTop; 바닥.scrollLeft = 상자.scrollLeft;
  };
  function 스크롤() { 바닥.scrollTop = 상자.scrollTop; 바닥.scrollLeft = 상자.scrollLeft; }
  상자.addEventListener("input", 따라가기);
  상자.addEventListener("scroll", 스크롤);
  var 시계 = setInterval(function () {
    if (!상자.isConnected) { 걷기(); return; }
    따라가기(); 맞추기();
  }, 500);
  window.addEventListener("resize", 맞추기);
  깔개.끝내기 = function () {
    상자.removeEventListener("input", 따라가기);
    상자.removeEventListener("scroll", 스크롤);
    clearInterval(시계);
    window.removeEventListener("resize", 맞추기);
  };
  맞추기();
  깔개.그리기();
  return true;
}

function 걷기() {
  if (!깔개) return;
  깔개.끝내기();
  깔개.판.remove();
  깔개.상자.style.position = 깔개.옛모양.position;
  깔개.상자.style.backgroundColor = 깔개.옛모양.backgroundColor;
  깔개 = null;
}

// 사람이 고친 만큼 자리를 옮긴다 — 고친 구간에 걸린 후보는 '손댐', 뒤의 것은 민다
var 기준글 = null;
function 따라가기() {
  var 상자 = 편집상자();
  if (!상자 || 기준글 === null) return;
  var 새 = 상자.value, 옛 = 기준글;
  if (새 === 옛) return;
  var n = Math.min(옛.length, 새.length), a = 0, b = 0;
  while (a < n && 옛.charCodeAt(a) === 새.charCodeAt(a)) a++;
  while (b < n - a && 옛.charCodeAt(옛.length - 1 - b) === 새.charCodeAt(새.length - 1 - b)) b++;
  var 옛끝 = 옛.length - b, 차 = 새.length - 옛.length;
  후보들.forEach(function (c) {
    if (c.끝남) return;
    if (c.갈래 === "누락" && a <= c.시작 && c.시작 <= 옛끝) { c.끝남 = "손댐"; return; }
    if (c.끝 <= a) return;
    if (c.시작 >= 옛끝) { c.시작 += 차; c.끝 += 차; return; }
    c.끝남 = "손댐";
  });
  기준글 = 새;
  if (깔개) { 깔개.기준 = 새; 깔개.그리기(); }
  목록그리기();
}

// ── 편집 상자에서 자리 보기 ──
function 위치재기(상자, i) {                      // 글자 i 의 세로 자리(px) — 같은 모양의 판을 하나 더 만들어 잰다
  var 잴 = document.createElement("div");
  모양베끼기(상자, 잴);
  잴.style.visibility = "hidden"; 잴.style.height = "auto"; 잴.style.overflow = "visible";
  잴.textContent = 상자.value.slice(0, i);
  var 표 = document.createElement("span"); 표.textContent = "​";
  잴.appendChild(표);
  상자.parentNode.appendChild(잴);
  var y = 표.offsetTop;
  잴.remove();
  return y;
}

var 고른것 = null;
function 자리보기(c) {
  var 상자 = 편집상자();
  고른것 = c;
  if (보이나(상자)) {
    var y = 위치재기(상자, c.시작);
    상자.scrollTop = Math.max(0, y - 상자.clientHeight / 3);
    상자.focus({ preventScroll: true });
    상자.setSelectionRange(c.시작, c.갈래 === "누락" ? c.시작 : Math.max(c.끝, c.시작 + 1));
    상자.scrollTop = Math.max(0, y - 상자.clientHeight / 3);
  }
  if (깔개) 깔개.그리기();
  목록그리기();
}

function 바꾸기(c) {
  var 상자 = 편집상자();
  if (상자.value.slice(c.시작, c.끝) !== c.원문) {
    알림("그 자리 글이 그사이 바뀌어 바꾸지 않았습니다 — 직접 고쳐 주세요.");
    return;
  }
  // 원문 구간 안에서 전사 글자만 바꾼다(구간에 틀이 끼어 있으면 손대지 않음)
  var 자리 = c.원문.indexOf(c.전사);
  if (자리 < 0 || c.원문.length !== c.전사.length) {
    알림("이 자리는 틀과 섞여 있어 자동으로 바꾸지 않습니다 — 직접 고쳐 주세요.");
    return;
  }
  상자.focus({ preventScroll: true });
  상자.setSelectionRange(c.시작, c.끝);
  // execCommand 로 넣어야 되돌리기(Ctrl+Z)가 된다. 안 되면 setRangeText.
  var 됨 = false;
  try { 됨 = document.execCommand("insertText", false, c.스캔); } catch (e) { 됨 = false; }
  if (!됨) {
    상자.setRangeText(c.스캔, c.시작, c.끝, "end");
    상자.dispatchEvent(new Event("input", { bubbles: true }));
  }
  따라가기();
  c.끝남 = "바꿈";
  if (깔개) 깔개.그리기();
  목록그리기();
}

// ── 목록 ──
function 목록그리기() {
  if (!판) return;
  var 몸 = 판.querySelector(".전사대조-목록");
  if (!몸) return;
  몸.textContent = "";
  // 넘기거나 바꾼 곳은 목록에서 빼고 맨 아래 한 줄로 접는다
  var 남은것 = [], 끝난것 = [];
  후보들.forEach(function (c, k) {
    if (보일것(c)) (c.끝남 ? 끝난것 : 남은것).push([c, k]);
  });
  남은것.forEach(function (ck) { 줄그리기(몸, ck[0], ck[1]); });
  if (!남은것.length) {
    var 없음 = document.createElement("div");
    없음.style.cssText = "padding:6px 4px";
    없음.textContent = 끝난것.length ? "남은 볼 곳이 없습니다." : "볼 곳이 없습니다.";
    몸.appendChild(없음);
  }
  if (끝난것.length) {
    var 셈 = {};
    끝난것.forEach(function (ck) { 셈[ck[0].끝남] = (셈[ck[0].끝남] || 0) + 1; });
    var 말 = { "넘김": "넘긴 곳", "바꿈": "바꾼 곳", "손댐": "손댄 곳" };
    var 접 = document.createElement("div");
    접.style.cssText = "padding:6px 4px;border-top:1px solid #eaecf0;font-size:13px;color:#36c;cursor:pointer";
    접.textContent = (끝난것보기 ? "▾ " : "▸ ")
      + Object.keys(셈).map(function (k) { return (말[k] || k) + " " + 셈[k] + "개"; }).join(" · ")
      + (끝난것보기 ? " — 접기" : " — 누르면 다시 보기");
    접.addEventListener("click", function () { 끝난것보기 = !끝난것보기; 목록그리기(); });
    몸.appendChild(접);
    if (끝난것보기) 끝난것.forEach(function (ck) { 줄그리기(몸, ck[0], ck[1]); });
  }
}

function 줄그리기(몸, c, k) {
  {
    var 줄 = document.createElement("div");
    줄.style.cssText = "display:flex;gap:10px;align-items:center;padding:6px 4px;border-top:1px solid #eaecf0;"
      + (c.끝남 ? "opacity:.45;" : "") + (c === 고른것 ? "background:#fef6e7;" : "");
    if (c.그림) {
      var im = document.createElement("img");
      im.src = c.그림;
      im.style.cssText = "height:96px;border:1px solid #c8ccd1;flex:none;cursor:zoom-in";
      im.title = "누르면 크게";
      im.addEventListener("click", function () { im.style.height = im.style.height === "96px" ? "220px" : "96px"; });
      줄.appendChild(im);
    }
    var 글 = document.createElement("div");
    글.style.cssText = "flex:1;min-width:0";
    var 머리 = document.createElement("div");
    머리.style.cssText = "font-size:12px;color:#54595d";
    머리.textContent = (k + 1) + ". " + 이름[c.갈래]
      + (c.갈래 === "바뀜" || c.갈래 === "모르는자모"
          ? " · 모델 확신 " + Math.round(c.확신 * 100) + "% · 전사 글자일 확률 " + (c.전사확률 * 100).toFixed(1) + "%" : "")
      + (c.갈래 === "깨진글자" ? " — " + c.까닭 + " (스캔과 상관없이 전사문만 보고)" : "")
      + (c.합의 === false ? " · 다르게 자르면 사라짐(자르기 실수일 수 있음)" : "")
      + (c.끝남 ? " — " + c.끝남 : "");
    var 본 = document.createElement("div");
    본.style.cssText = "font-size:20px;line-height:1.6";
    본.appendChild(document.createTextNode(c.앞));
    var b = document.createElement("b");
    b.style.cssText = "background:" + 색[c.갈래];
    b.textContent = c.갈래 === "누락" ? "〔" + c.스캔 + " 누락?〕" : c.전사;
    본.appendChild(b);
    본.appendChild(document.createTextNode(c.뒤));
    if (c.갈래 === "바뀜" || c.갈래 === "모르는자모") {
      var 스 = document.createElement("span");
      스.style.cssText = "margin-left:14px;color:#54595d;font-size:15px";
      스.textContent = "스캔: ";
      var sb = document.createElement("b"); sb.style.fontSize = "20px"; sb.textContent = c.스캔;
      스.appendChild(sb);
      본.appendChild(스);
    } else if (c.갈래 !== "깨진글자") {
      var 설 = document.createElement("span");
      설.style.cssText = "margin-left:14px;color:#54595d;font-size:13px";
      설.textContent = c.갈래 === "빠짐" ? "이 근처에서 전사문에 글자가 " + c.칸 + "자 빠졌을 수 있습니다"
                                       : "이 근처에서 전사문에 글자가 " + c.칸 + "자 더 들어갔을 수 있습니다";
      if (c.갈래 === "누락") 설.textContent = "이 사이에 " + c.칸 + "글자 누락 의심 · 스캔: " + c.스캔 + " · 다음 글자 앞을 표시했습니다";
      본.appendChild(설);
    }
    글.appendChild(머리); 글.appendChild(본);
    줄.appendChild(글);
    var 단 = document.createElement("div");
    단.style.cssText = "display:flex;flex-direction:column;gap:4px;flex:none";
    function 단추하나(이름, 할일) {
      var x = document.createElement("button");
      x.type = "button"; x.className = "cdx-button"; x.textContent = 이름;
      x.addEventListener("click", 할일);
      단.appendChild(x);
      return x;
    }
    단추하나("자리 보기", function () { 자리보기(c); });
    if (!c.끝남 && 바꿀수(c)) {
      단추하나("바꾸기 → " + c.스캔, function () { 바꾸기(c); });
    }
    if (!c.끝남) 단추하나("넘기기", function () { c.끝남 = "넘김"; if (깔개) 깔개.그리기(); 목록그리기(); });
    줄.appendChild(단);
    몸.appendChild(줄);
  }
}

function 판세우기(답) {
  if (판) 판.remove();
  끝난것보기 = false;
  판 = document.createElement("div");
  판.id = "전사대조-판";
  판.style.cssText = "margin:8px 0;padding:8px 12px;border:1px solid #c8ccd1;background:#fff;"
    + "border-radius:2px;max-height:26em;overflow:auto";
  var 요약 = document.createElement("div");
  요약.style.cssText = "font-size:13px;color:#202122;margin-bottom:4px";
  var 바뀜수 = 후보들.filter(확실).length;
  요약.textContent = "스캔과 " + Math.round(답.일치 * 100) + "% 맞음 · 볼 곳 " + 바뀜수 + " (" + 답.초 + "초)"
    + (답.흔들린열 ? " · 맞대기가 흔들린 열 " + 답.흔들린열 + "개는 뺐습니다" : "")
    + (답.아는문헌 ? "" : " · 자간은 이 쪽 그림으로 잼(OCR 소도구로 이 파일을 한 번 읽으면 파일 전체로 잰 값을 씀)");
  판.appendChild(요약);
  var 어긋남수 = 후보들.length - 바뀜수;
  if (어긋남수) {
    // 다르게 잘라 보면 사라지는 후보는 대개 자르기 실수라 접어 둔다
    var 펼 = document.createElement("button");
    펼.type = "button"; 펼.className = "cdx-button";
    펼.style.cssText = "font-size:12px;margin-bottom:4px";
    function 글() { 펼.textContent = (어긋남보기 ? "자르기에 따라 달라진 곳 " + 어긋남수 + "곳 접기"
                                              : "자르기에 따라 달라진 곳 " + 어긋남수 + "곳도 보기 (자르기 실수가 많음)"); }
    글();
    펼.addEventListener("click", function () { 어긋남보기 = !어긋남보기; 글(); if (깔개) 깔개.그리기(); 목록그리기(); });
    판.appendChild(펼);
  }
  if (답.흔들림) {
    var 경 = document.createElement("div");
    경.style.cssText = "font-size:13px;color:#b32424;margin-bottom:4px";
    경.textContent = "⚠ 이 쪽은 스캔과 전사문이 잘 맞춰지지 않았습니다 — 아래 목록에 헛경보가 많을 수 있습니다.";
    판.appendChild(경);
  }
  var 안내 = document.createElement("div");
  안내.style.cssText = "font-size:12px;color:#72777d;margin-bottom:4px";
  안내.textContent = "모델이 틀렸을 수도 있습니다 — 스캔 조각을 보고 정하세요. 원문 오식은 {{SIC}} 로 표시해 주세요.";
  판.appendChild(안내);
  var 몸 = document.createElement("div");
  몸.className = "전사대조-목록";
  판.appendChild(몸);
  var 줄 = document.getElementById("전사대조-줄");
  줄.parentNode.insertBefore(판, 줄.nextSibling);
  목록그리기();
}

// ── 서버 ────────────────────────────────────────────────────────────
// Toolforge 서버(`툴포지/app.py`) — 있으면 맞대기를 서버에 맡김(파이썬 `대조.한쪽` — 답의 꼴이 `셈.한쪽` 과 같음).
// 서버가 내주는 이 파일의 맨 앞 줄이 채움. OCR 소도구와 같은 서버 · 같은 판형 살피기
var 서버 = window.옛한글OCR서버 || "";
if (서버 && 서버.charAt(서버.length - 1) !== "/") 서버 += "/";

async function 서버살피기(파일) {
  for (;;) {
    var 답 = await (await fetch(서버 + "api/inspect?file=" + encodeURIComponent(파일))).json();
    if (답.상태 === "끝") return 답.값;
    if (답.상태 === "오류" || 답.오류) throw new Error(답.오류 || "서버가 판형을 못 살폈습니다");
    알림("이 파일의 판형·자간을 서버에서 살피는 중… (" + 답.진행 + ", 이 파일은 처음 한 번만)");
    await new Promise(function (ok) { setTimeout(ok, 2000); });
  }
}

async function 서버로(경로, 몸) {
  var res = await fetch(서버 + 경로, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(몸),
  });
  var 답 = await res.json();
  if (!res.ok || 답.오류) throw new Error(답.오류 || ("서버 오류 " + res.status));
  return 답;
}

async function 시작() {
  var 쪽 = 지금쪽(), 상자 = 편집상자();
  if (!쪽 || !상자) return;
  if (!서버) { 알림("서버 주소가 없습니다 — Toolforge 도구가 내주는 주소(…/ocr.js · …/compare.js)로 불러와 주세요."); return; }
  단추.disabled = true;
  걷기();
  var 공 = 공용도구(), 고른모델 = 공.모델(), 고른단 = 공.단();
  var t0 = performance.now();
  var 언제 = new Date(), 때 = {}, 결과 = [], 살핀 = null, 답 = null, t;
  var 재기 = function (이름, t) { 때[이름] = performance.now() - t; };
  try {
    var 본문 = 상자.value;
    결과.push(["편집 상자", 본문.length + "글자(UTF-16)"]);
    t = performance.now();
    살핀 = await 서버살피기(쪽.파일);
    재기("판형 살피기", t);
    알림("서버에서 문자를 대조하는 중…");
    t = performance.now();
    살핀 = 단바꾸기(살핀, 고른단);
    답 = await 서버로("api/compare", { file: 쪽.파일, page: 쪽.쪽, text: 본문, model: 고른모델, tiers: 고른단 || "auto" });
    재기("대조(서버 왕복)", t);       // 후보 그림(data: 주소)까지 서버가 붙여 줌
    if (답.초 !== undefined) 때["└ 서버 셈"] = 답.초 * 1000;
    if (답.사유) throw new Error(답.사유);
    var 뒤쪽 = 지금쪽();
    if (!뒤쪽 || 뒤쪽.파일 !== 쪽.파일 || 뒤쪽.쪽 !== 쪽.쪽) throw new Error("맞대는 사이에 쪽이 바뀌었습니다 — 다시 눌러 주세요.");
    if (상자.value !== 본문) throw new Error("맞대는 사이에 편집 상자가 바뀌었습니다 — 다시 눌러 주세요.");
    답.초 = ((performance.now() - t0) / 1000).toFixed(1);
    후보들 = 답.후보.map(function (c) {
      c.원문 = 본문.slice(c.시작, c.끝);
      return c;
    });
    기준글 = 본문;
    고른것 = null;
    판세우기(답);
    var 칠함 = 깔기(상자);
    알림("볼 곳 " + 후보들.filter(확실).length + "곳" + (칠함 ? "" : " — 구문 강조가 켜져 있어 편집 상자에는 칠하지 못했습니다(끄면 칠합니다)"));
  } catch (e) {
    console.error(e);
    var 메시지 = e && e.message ? e.message : e;
    알림("✗ " + 메시지);
    결과.push(["오류", String(메시지)]);
    if (e && e.stack) 결과.push(["오류 자리", "\n  " + String(e.stack).split("\n").slice(0, 6).join("\n  ")]);
  } finally {
    단추.disabled = false;
    try { 로그쓰기(로그머리(쪽, 언제).concat(결과, 로그본문(살핀, 답, 때, t0))); }
    catch (e2) { console.error(e2); }
  }
}

function 세우기() {
  if (!지금쪽() || !편집상자()) return;
  if (document.getElementById("전사대조-줄")) return;
  var 공 = 공용도구();                     // 인식 · 교정 · 영역 지정 단추가 한 줄 — 차례는 style.order(인식 1 · 교정 2 · 영역 3 · 설정 4)
  단추 = document.createElement("button");
  단추.type = "button";
  단추.className = "cdx-button";
  단추.style.order = "2";
  단추.textContent = "교정 (전사대조)";
  단추.title = "지금 편집 상자의 전사문을 이 쪽 스캔과 맞대어 틀렸을 만한 글자를 짚습니다";
  단추.addEventListener("click", 시작);
  공.줄.appendChild(단추);
  // 알림 글은 단추 줄 아래 한 줄(⚠ 후보 목록 판이 이 줄 다음에 놓임)
  var 줄 = document.createElement("div");
  줄.id = "전사대조-줄";
  줄.style.cssText = "margin:4px 0 0";
  상태 = document.createElement("span");
  상태.style.cssText = "font-size:13px;color:#54595d";
  줄.appendChild(상태);
  공.뿌리.appendChild(줄);
  로그단추(공);
  // 순서대로 편집으로 쪽을 옮기면 앞 쪽의 칠 · 후보 목록을 걷음
  if (/[?&]prp_editinsequence=/i.test(location.search)) {
    window.addEventListener("hashchange", function () {
      걷기();
      if (판) { 판.remove(); 판 = null; }
      후보들 = []; 기준글 = null; 고른것 = null;
      if (!단추.disabled) 알림("");
    });
  }
}

window.전사대조 = { 시작: 시작, 후보: function () { return 후보들; } };   // 시험용

if (window.mw && mw.loader) {
  mw.loader.using(["mediawiki.api", "mediawiki.util"]).then(function () {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", 세우기);
    else 세우기();
  });
}
})(typeof self !== "undefined" ? self : this);
