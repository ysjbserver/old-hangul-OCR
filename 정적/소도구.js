/*
 * 옛한글 OCR — 위키문헌 소도구
 *
 * 페이지 이름공간 편집 창에 단추를 놓고, 누르면 그 쪽을 **Toolforge 서버**에서 읽어 편집 상자에 넣음.
 * 셈은 전부 서버(`근원/툴포지/app.py` · 파이썬 부품) — 이 파일은 화면만. 서버가 내주는 이 파일의 맨 앞 줄이
 * `window.옛한글OCR서버` 를 채움(서버 없이 단독으로는 안 돎).
 */
(function () {
"use strict";

// ── 어디서 가져오나 ──────────────────────────────────────────────────
// Toolforge 서버(`툴포지/app.py`) — 있으면 모델 · 판형 살피기를 서버에 맡김. 서버가 내주는 이 파일의 맨 앞 줄이 채움
var 서버 = window.옛한글OCR서버 || "";
if (서버 && 서버.charAt(서버.length - 1) !== "/") 서버 += "/";

// 영역 지정 화면 주소 — 서버 모드면 그 서버의 area/. `window.옛한글OCR영역` 으로 바꿀 수 있음. 비면 단추 없음
var 영역 = window.옛한글OCR영역 || (서버 ? 서버 + "area/" : "");

var 상태, 단추;

// ── 작은 도우미 ──────────────────────────────────────────────────────
function 알림(t) { if (상태) 상태.textContent = t; }

// ── 디버그 로그 — 잘 안 읽힌 쪽을 알릴 때 복사해 붙일 글(마지막 한 번만) ──
var 로그 = { 글: "", 칸: null };

function 시각글(d) {
  function p(n) { return String(n).padStart(2, "0"); }
  var 차 = -d.getTimezoneOffset();
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " "
       + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds())
       + " (UTC" + (차 >= 0 ? "+" : "-") + p(Math.floor(Math.abs(차) / 60)) + ":" + p(Math.abs(차) % 60) + ")";
}

/** 문서 이름 · 주소 · 실행 환경 — 쪽과 상관없이 늘 적는 것 */
function 로그머리(쪽, 언제) {
  var c = mw.config.get(["wgServer", "wgArticlePath", "wgFormattedNamespaces", "wgNamespaceNumber", "wgCurRevisionId"]);
  var 제목 = 쪽 ? ((c.wgFormattedNamespaces || {})[c.wgNamespaceNumber] || "페이지") + ":" + 쪽.파일 + "/" + 쪽.쪽 : "(못 찾음)";
  return [
    ["도구", "인식 (전사)"],
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

function 로그쓰기(줄들) {
  로그.글 = "[옛한글 OCR 디버그 로그]\n" + 줄들
    .filter(function (v) { return v[1] !== undefined && v[1] !== null && v[1] !== ""; })
    .map(function (v) { return v[0] + ": " + v[1]; }).join("\n");
  if (로그.칸) 로그.칸.글.value = 로그.글;
}

function 초글(ms) { return (ms / 1000).toFixed(1) + "초"; }

/** 단추 줄 오른쪽 끝의 작은 '인식 로그' — 누르면 줄 아래에 펼침. `공` = `공용도구()` */
function 로그단추(공) {
  var 고리 = document.createElement("a");
  고리.href = "#";
  고리.setAttribute("role", "button");
  고리.textContent = "인식 로그";
  고리.title = "마지막으로 읽은 쪽의 기록(쪽 · 시간 · 판정 …) — 잘 안 읽힌 쪽을 알릴 때 복사해 붙여 주세요";
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
    고리.textContent = 열림 ? "인식 로그 닫기" : "인식 로그";
    글.value = 로그.글 || "아직 기록이 없습니다 — '인식 (전사)' 를 한 번 누른 뒤에 보세요.";
    알림말.textContent = "";
  });
  공.로그묶음.appendChild(고리);
  공.줄.appendChild(칸);           // 줄이 flex-wrap 이라 폭 100% 로 다음 줄에 펼쳐짐
  로그.칸 = { 글: 글 };
}

// ── 공용 도구 줄 — 인식 · 교정 · 영역 지정 단추를 한 줄에 모으고, 옆의 '설정' 메뉴에 모델 · 단을 둠 ──
// ⚠ `소도구.js` 와 `전사대조.js` 에 **같은 꼴**로 들어 있음 — 한쪽을 고치면 다른 쪽도(어느 쪽이 먼저 떠도 한 줄을 같이 씀)
// 고른 값은 `window.옛한글OCR공용.모델()` · `.단()` 으로 읽음 — 모델 "hangul"(근대 순한글) | "hanmun"(근대 국한문) ·
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

/**
 * 편집 중인 쪽의 파일 이름과 쪽 번호. "페이지:셩경젼셔 신약.pdf/393" → {파일, 쪽: 393}
 * ⚠ 이름공간 이름은 언어마다 달라 `wgCanonicalNamespace` 로 확인
 * 순서대로 편집(`prp_editinsequence`)은 쪽을 옮겨도 `mw.config` 를 안 바꾸고 `location.hash` 에 "페이지:파일/쪽" 만 적음 → 그때는 hash 를 먼저 봄
 */
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
  var m = /^(.*)\/(\d+)$/.exec(순서편집제목() || cfg.wgTitle);
  if (!m) return null;
  return { 파일: m[1], 쪽: parseInt(m[2], 10) };
}

/** 편집 상자 (2017 편집기·CodeMirror 아래에서도 원본은 이것) */
function 편집상자() {
  return document.querySelector("#wpTextbox1")
      || document.querySelector("textarea[name='wpTextbox1']");
}

// ── 서버 ────────────────────────────────────────────────────────
/** 서버에 판형 살피기를 맡기고 끝날 때까지 되물음(처음 보는 파일은 1~3분) */
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

function 판형글(값) {
  return Array.isArray(값) ? (값.length + 1) + "단(가로줄로 가름)" : 값 + "단";
}

function 살핀글(살핀) {
  return (window.옛한글OCR공용 && window.옛한글OCR공용.단() ? "단은 직접 골라 " : "쪽을 살펴 ") + 판형글(살핀.단)
       + (살핀.자간비 ? " · 자간비 " + 살핀.자간비.toFixed(3) : " · 자간은 기본값")
       + "으로 정했습니다";
}

// ── 단추를 눌렀을 때 ─────────────────────────────────────────────────
async function 읽기시작() {
  var 상자 = 편집상자();
  var 쪽 = 지금쪽();
  if (!상자 || !쪽) { 알림("편집 창을 못 찾았습니다."); return; }
  if (!서버) { 알림("서버 주소가 없습니다 — Toolforge 도구가 내주는 주소(…/ocr.js · …/compare.js)로 불러와 주세요."); return; }
  단추.disabled = true;
  var 공 = 공용도구(), 고른모델 = 공.모델(), 고른단 = 공.단();
  var 언제 = new Date(), 처음 = performance.now(), 때 = {}, 결과 = [], 살핀, r;
  var 재기 = function (이름, t) { 때[이름] = performance.now() - t; };
  try {
    var 초, 실행, t;
    t = performance.now();
    살핀 = await 서버살피기(쪽.파일);
    재기("판형 살피기", t);
    알림("서버에서 문자를 인식하는 중…");
    var t1 = performance.now();
    r = await 서버로("api/read", { file: 쪽.파일, page: 쪽.쪽, model: 고른모델, tiers: 고른단 || "auto", spacing: 공.띄움() });
    살핀 = r.살핀 || 단바꾸기(살핀, 고른단);
    재기("인식(서버 왕복)", t1);
    if (r.초 !== undefined) 때["└ 서버 셈"] = r.초 * 1000;
    초 = ((performance.now() - t1) / 1000).toFixed(1);
    실행 = "서버";
    결과.push(["판정", r.판정.등급 + (r.판정.까닭.length ? " — " + r.판정.까닭.join(" · ") : "")]);

    // 순서대로 편집에서 읽는 사이 쪽을 옮겼으면 넣지 않음 — 다른 쪽 글을 덮게 됨
    var 뒤쪽 = 지금쪽();
    if (!뒤쪽 || 뒤쪽.파일 !== 쪽.파일 || 뒤쪽.쪽 !== 쪽.쪽) {
      알림("읽는 사이에 쪽이 바뀌어(" + 쪽.쪽 + "쪽 → " + (뒤쪽 ? 뒤쪽.쪽 + "쪽" : "?")
           + ") 넣지 않았습니다. 다시 눌러 주세요.");
      결과.push(["넣음", "아니오 — 읽는 사이에 쪽이 바뀜"]);
      return;
    }
    if (!r.글월) {
      알림(쪽.쪽 + "쪽 판정: " + r.판정.등급 + " — " + (r.판정.까닭.join(" · ") || "열을 못 찾았습니다")
           + ". 넣지 않았습니다.");
      결과.push(["넣음", "아니오 — 읽은 글이 없음"]);
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
    결과.push(["넣음", r.판정.등급 === "못씀" ? "아니오 — 못씀" : "예" + (칠함 ? " · 칠함" : " · 칠 못함(위쪽 칸)")]);
    알림(쪽.쪽 + "쪽 " + (r.판정.등급 === "못씀" ? "판정: 못씀 — 넣지 않았습니다. 처음부터 치는 편이 빠릅니다"
                              : "판정: " + r.판정.등급)
         + (칠함 ? " · 노란 자리가 확신 낮은 글자입니다(고치면 칠이 사라지고, 칠은 저장되지 않습니다)" : "")
         + " · " + 살핀글(살핀)
         + (고른모델 === "hanmun" ? " · 국한문 모델" : "")
         + " · 확신 낮은 글자 " + (r.표시비 * 100).toFixed(0) + "%"
         + " · " + r.상자수 + (서버 ? "자 " : "상자 ") + 초 + "초(" + 실행 + ")"
         + (r.판정.까닭.length ? " · " + r.판정.까닭.join(" · ") : ""));
  } catch (e) {
    알림("멈췄습니다: " + e.message);
    console.error(e);
    결과.push(["오류", (e && e.message) || String(e)]);
    if (e && e.stack) 결과.push(["오류 자리", "\n  " + String(e.stack).split("\n").slice(0, 6).join("\n  ")]);
  } finally {
    단추.disabled = false;
    try { 로그쓰기(로그머리(쪽, 언제).concat(결과, 로그본문(살핀, r, 때, 처음))); }
    catch (e2) { console.error(e2); }
  }
}

/** 판형 · 읽은 결과 · 걸린 시간 */
function 로그본문(살핀, r, 때, 처음) {
  var 줄 = [];
  if (살핀) 줄.push(["판형 살핀 값", 판형글(살핀.단) + (살핀.자간비 ? " · 자간비 " + 살핀.자간비.toFixed(3) : " · 자간비 없음(기본값)")
                       + (살핀.판짜임 ? " · 판짜임 " + JSON.stringify(살핀.판짜임) : "")]);
  if (r) {
    if (살핀 && 살핀.빈단) 줄.push(["선 없는 단", "경계 " + 살핀.빈단.join("~") + "px · 단별 자간비 "
        + 살핀.단별자간비.map(function (v) { return v.toFixed(3); }).join(" · ")]);
    줄.push(["읽은 것", r.상자수 + (서버 ? "자" : "상자") + " · 표시 " + (r.표시비 * 100).toFixed(1) + "%"
             + (r.글월 ? " · 줄 " + r.글월.split("\n").length : "")]);
    if (r.글월) 줄.push(["줄마다 글자 수", r.글월.split("\n").map(function (l) { return l.replace(/\s/g, "").length; }).join(" ")]);
    var g = r.기하;
    if (g && g.cols) 줄.push(["기하", "열 " + g.cols.length + "개(가장자리 후보 포함) · 열 간격 " + (+g.xpitch).toFixed(1)
                             + "px · 글자 높이 " + (+g.pitch).toFixed(1) + "px" + (g.맞춤 ? " · 상자 맞춤" : "")]);
  }
  var 시간 = Object.keys(때).map(function (k) { return k + " " + 초글(때[k]); });
  시간.push("전체 " + 초글(performance.now() - 처음));
  줄.push(["걸린 시간", 시간.join(" · ")]);
  return 줄;
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
  var 공 = 공용도구();                     // 인식 · 교정 · 영역 지정 단추가 한 줄 — 차례는 style.order(인식 1 · 교정 2 · 영역 3 · 설정 4)
  단추 = document.createElement("button");
  단추.type = "button";
  단추.className = "cdx-button";
  단추.style.order = "1";
  단추.textContent = "인식 (전사)";
  단추.addEventListener("click", 읽기시작);
  공.줄.appendChild(단추);
  // 영역 지정 화면을 새 창으로 — 지금 쪽(파일 · 쪽 번호)과 고른 모델을 물음표 뒤에 실어 저절로 불러오게
  if (영역) {
    var 영역단추 = document.createElement("a");
    영역단추.className = "cdx-button";
    영역단추.style.order = "3";
    영역단추.target = "_blank";
    영역단추.rel = "noopener";
    영역단추.textContent = "영역 지정";
    영역단추.title = "이 쪽 스캔을 영역 지정 도구에서 엽니다(상자를 쳐서 그 자리만 읽기)";
    var 영역주소 = function () {
      var 쪽 = 지금쪽();                       // 순서대로 편집으로 쪽을 옮겼을 수 있어 누를 때마다 새로
      var 값 = { host: location.host };
      if (쪽) { 값.file = 쪽.파일; 값.page = String(쪽.쪽); }
      if (공.모델() !== "hangul") 값.model = 공.모델();
      영역단추.href = 영역 + "?" + new URLSearchParams(값);
    };
    영역주소();
    영역단추.addEventListener("mousedown", 영역주소);   // 가운데 단추로 새 탭에 열 때도
    영역단추.addEventListener("click", 영역주소);
    공.줄.appendChild(영역단추);
  }
  // 알림 글은 단추 줄 아래 한 줄(⚠ `보이기` 가 이 줄 다음에 교정 칸을 놓음)
  var 줄 = document.createElement("div");
  줄.id = "옛한글OCR-줄";
  줄.style.cssText = "margin:4px 0 0";
  상태 = document.createElement("span");
  상태.style.cssText = "font-size:13px;color:#54595d";
  상태.textContent = "";
  줄.appendChild(상태);
  공.뿌리.appendChild(줄);
  로그단추(공);
  // 순서대로 편집으로 쪽을 옮기면 앞 쪽의 칠 · 교정 칸 · 알림을 걷음
  if (/[?&]prp_editinsequence=/i.test(location.search)) {
    window.addEventListener("hashchange", function () {
      표시걷기();
      교정칸치우기();
      if (!단추.disabled) 알림("");
    });
  }
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
