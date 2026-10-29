/*
 * 옛한글 OCR — 소도구 공용 부분: 편집 도구모음 단추 · 펼침 메뉴 · 상태 띠 · 로그 · 서버
 *
 * 서버가 `/ocr.js` 로 공용.js · 소도구.js(인식) · 전사대조.js(교정)를 이어 붙여 내줌 — 맨 앞 줄이 `window.옛한글OCR서버` 를 채움.
 * 인식 · 교정은 `window.옛한글OCR` 을 씀.
 */
(function () {
"use strict";
if (typeof document === "undefined" || window.옛한글OCR) return;      // 두 번 실려도 한 번만

// ── 어디서 가져오나 ──────────────────────────────────────────────────
var 서버 = window.옛한글OCR서버 || "";
if (서버 && 서버.charAt(서버.length - 1) !== "/") 서버 += "/";
// 영역 지정 화면 주소 — 기본은 서버의 area/ · `window.옛한글OCR영역` 으로 바꿈
var 영역 = window.옛한글OCR영역 || (서버 ? 서버 + "area/" : "");

// ── 작은 도우미 ──────────────────────────────────────────────────────
function 만들기(태그, 이름, 글) {
  var e = document.createElement(태그);
  if (이름) e.className = 이름;
  if (글) e.textContent = 글;
  return e;
}

function 저장(이름, 값) {          // 고른 값을 기억(막힌 브라우저면 기억 없이)
  try {
    if (값 === undefined) return localStorage.getItem("옛한글OCR:" + 이름);
    localStorage.setItem("옛한글OCR:" + 이름, 값);
  } catch (e) {}
  return null;
}

/**
 * 편집 중인 쪽의 파일 이름과 쪽 번호. "페이지:셩경젼셔 신약.pdf/393" → {파일, 쪽: 393}
 * ⚠ 순서대로 편집은 쪽을 옮겨도 `mw.config` 를 안 바꾸고 `location.hash` 만 바꿈 → hash 를 먼저 봄
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
  if (cfg.wgAction !== "edit" && cfg.wgAction !== "submit") return null;
  var m = /^(.*)\/(\d+)$/.exec(순서편집제목() || cfg.wgTitle);
  return m ? { 파일: m[1], 쪽: parseInt(m[2], 10) } : null;
}

/** 편집 상자 (2017 편집기·CodeMirror 아래에서도 원본은 이것) */
function 편집상자() {
  return document.querySelector("#wpTextbox1") || document.querySelector("textarea[name='wpTextbox1']");
}

function 보이나(상자) {
  return 상자.isConnected && 상자.offsetParent !== null && getComputedStyle(상자).visibility !== "hidden";
}

/** CodeMirror 글이 숨은 textarea 에 아직 안 옮겨졌어도 읽음 */
function 편집글(상자) {
  if (window.jQuery && window.jQuery.fn && typeof window.jQuery.fn.textSelection === "function") {
    return window.jQuery(상자).textSelection("getContents");
  }
  return 상자.value;
}

function 초글(ms) { return (ms / 1000).toFixed(1) + "초"; }

function 판형글(값) {
  return Array.isArray(값) ? (값.length + 1) + "단(가로줄로 가름)" : (값 || 1) + "단";
}

function 확인(글) {
  if (window.OO && OO.ui && OO.ui.confirm) return OO.ui.confirm(글);
  return Promise.resolve(window.confirm(글));
}

// ── 고른 값 ──────────────────────────────────────────────────────────
var 고름 = {
  모델: 저장("모델") === "hanmun" ? "hanmun" : "hangul",
  단: /^[1-5]$/.test(저장("단") || "") ? parseInt(저장("단"), 10) : null,
  띄움: 저장("띄움") !== "끔",
  국한문있음: true,
};

function 단글(단) { return 단 ? 단 + "단(직접 고름)" : "자동"; }

function 선택글() {
  return (공.모델() === "hanmun" ? "근대 국한문" : "근대 순한글") + " · 단 " + 단글(고름.단)
       + " · 띄어쓰기 " + (고름.띄움 ? "자동 감지" : "끔");
}

/** 살핀 설정의 단만 고른 값으로 — 1단 = 1, N단 = 가름줄 높이 목록. 자동(null)이면 그대로 */
function 단바꾸기(살핀, 단) {
  if (!단 || !살핀) return 살핀;
  var s = {};
  for (var k in 살핀) s[k] = 살핀[k];
  s.단 = 단 === 1 ? 1 : Array.apply(null, Array(단 - 1)).map(function (_, i) { return (i + 1) / 단; });
  return s;
}

// ── 꼴 ───────────────────────────────────────────────────────────────
// 아이콘: 텍스트 변환(OCR) 아이콘의 네 귀 + ᄒᆞ. currentColor 로 칠함(어두운 화면 · 꺼진 단추도 따라감)
var 아이콘 = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">'
  + '<path d="M3 17h5v2H1v-7h2zm16 2h-7v-2h5v-5h2zM8 3H3v5H1V1h7zm11 5h-2V3h-5V1h7z"/>'
  + '<rect x="9.1" y="3.6" width="1.8" height="2.2"/><rect x="5.2" y="5.8" width="9.6" height="1.7"/>'
  + '<ellipse cx="10" cy="10.4" rx="3.2" ry="2.15" fill="none" stroke="#000" stroke-width="1.6"/>'
  + '<circle cx="10" cy="15" r="1.25"/></svg>';
// 전사대조: 같은 틀 · ᄒᆞ 에 오른쪽 아래 귀만 체크로
var 교정아이콘 = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">'
  + '<path d="M3 17h5v2H1v-7h2zM8 3H3v5H1V1h7zm11 5h-2V3h-5V1h7z"/>'
  + '<rect x="9.1" y="3.6" width="1.8" height="2.2"/><rect x="5.2" y="5.8" width="9.6" height="1.7"/>'
  + '<ellipse cx="10" cy="10.4" rx="3.2" ry="2.15" fill="none" stroke="#000" stroke-width="1.6"/>'
  + '<circle cx="10" cy="15" r="1.25"/>'
  + '<path d="M12.6 16.3l1.9 1.9 4.2-4.6" fill="none" stroke="#000" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
function 그림주소(svg) { return "url(\"data:image/svg+xml," + encodeURIComponent(svg) + "\")"; }
var 아이콘주소 = 그림주소(아이콘), 교정아이콘주소 = 그림주소(교정아이콘);

function 꼴넣기() {
  if (document.getElementById("옛한글OCR-꼴")) return;
  var s = 만들기("style");
  s.id = "옛한글OCR-꼴";
  s.textContent = [
    ".group-old-hangul-ocr{float:left;display:flex;align-items:center;box-sizing:border-box;height:32px;padding:0 4px}",
    // OOUI 가 아이콘 칸을 단추 높이만큼 늘이므로 그림은 가운데 20px 로
    ".옛한글OCR-아이콘{min-width:20px;min-height:20px;background:currentColor;"
      + "-webkit-mask:" + 아이콘주소 + " center/20px 20px no-repeat;mask:" + 아이콘주소 + " center/20px 20px no-repeat}",
    ".옛한글OCR-아이콘.교정{-webkit-mask-image:" + 교정아이콘주소 + ";mask-image:" + 교정아이콘주소 + "}",
    "#옛한글OCR-도구{margin:8px 0}",
    ".옛한글OCR-펼침{position:absolute;z-index:1001;box-sizing:border-box;width:260px;max-width:calc(100vw - 16px);"
      + "padding:12px 14px;background:var(--background-color-base,#fff);color:var(--color-base,#202122);"
      + "border:1px solid var(--border-color-base,#a2a9b1);border-radius:2px;box-shadow:0 2px 2px 0 rgba(0,0,0,.25);font-size:14px;line-height:1.5}",
    ".옛한글OCR-펼침 .제목{font-weight:bold;margin:0 0 4px}",
    ".옛한글OCR-펼침 .줄{display:flex;gap:8px;align-items:center;margin:4px 0}",
    ".옛한글OCR-펼침 .줄>.제목{min-width:2.5em;margin:0}",
    ".옛한글OCR-펼침 select{flex:1;min-width:0}",
    ".옛한글OCR-펼침 .가운데{display:block;text-align:center}",
    ".옛한글OCR-펼침 .칸{margin:0 0 10px}",
    ".옛한글OCR-펼침 hr{border:0;border-top:1px solid var(--border-color-subtle,#c8ccd1);margin:10px -14px}",
    ".옛한글OCR-펼침 input{accent-color:var(--color-progressive,#36c);margin:0}",
    ".옛한글OCR-펼침 .고리{color:var(--color-progressive,#36c);text-decoration:none;cursor:pointer}",
    ".옛한글OCR-펼침 .고리:hover{text-decoration:underline}",
    ".옛한글OCR-펼침 .로그들{display:flex;gap:16px;font-size:12px}",
    ".옛한글OCR-펼침 .로그들 .고리{color:var(--color-subtle,#72777d)}",
    ".옛한글OCR-띠{background:var(--background-color-interactive,#eaecf0);border:solid var(--border-color-subtle,#c8ccd1);"
      + "border-width:1px 0;color:var(--color-base,#202122)}",
    ".옛한글OCR-띠 .첫줄{display:flex;align-items:center;gap:8px;min-height:32px;padding:0 0 0 8px;font-weight:bold}",
    ".옛한글OCR-띠 .첫줄 .말{flex:1;min-width:0}",
    ".옛한글OCR-띠 .첫줄 .말 small{font-weight:normal;color:var(--color-subtle,#54595d)}",
    ".옛한글OCR-띠 .둘째줄{padding:0 12px 6px;font-size:12px;color:var(--color-subtle,#54595d)}",
    ".옛한글OCR-띠 .둘째줄>div{margin-top:2px}",
    ".옛한글OCR-띠 .둘째줄 .경고{color:var(--color-warning,#886425)}",
    ".옛한글OCR-띠 .빛{display:inline-block;width:.9em;height:.9em;border-radius:2px;vertical-align:-.1em;margin:0 3px 0 8px}",
    ".옛한글OCR-띠 .빛:first-child{margin-left:0}",
    ".옛한글OCR-띠 .글단추{background:none;border:0;padding:4px 6px;font:inherit;font-weight:bold;cursor:pointer;"
      + "color:var(--color-progressive,#36c)}",
    ".옛한글OCR-띠 .글단추:disabled{color:var(--color-disabled,#a2a9b1);cursor:default}",
    ".옛한글OCR-빙글{display:inline-block;box-sizing:border-box;width:16px;height:16px;margin:0 4px;flex:none;border-radius:50%;"
      + "border:2px solid var(--border-color-subtle,#c8ccd1);border-top-color:var(--color-progressive,#36c);animation:옛한글OCR-돎 .8s linear infinite}",
    "@keyframes 옛한글OCR-돎{to{transform:rotate(360deg)}}",
    ".옛한글OCR-가림{position:fixed;inset:0;z-index:1002;background:rgba(255,255,255,.5);display:flex;align-items:center;justify-content:center}",
    ".옛한글OCR-창{box-sizing:border-box;width:min(760px,94vw);padding:16px;background:var(--background-color-base,#fff);"
      + "color:var(--color-base,#202122);border:1px solid var(--border-color-base,#a2a9b1);border-radius:2px;box-shadow:0 2px 2px 0 rgba(0,0,0,.25)}",
    ".옛한글OCR-창 textarea{width:100%;box-sizing:border-box;height:20em;resize:vertical;font-family:monospace;font-size:12px;"
      + "white-space:pre-wrap;word-break:break-all;background:var(--background-color-neutral-subtle,#f8f9fa);border:1px solid var(--border-color-subtle,#c8ccd1);padding:4px 6px}",
    ".옛한글OCR-창 .아래{display:flex;gap:8px;align-items:center;margin-top:8px}",
    ".옛한글OCR-숨김{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}",
  ].join("\n");
  document.head.appendChild(s);
  // OOUI 단추 · 아이콘 꼴(편집 창에는 대개 이미 있음)
  if (window.mw && mw.loader && mw.loader.load) {
    try {
      mw.loader.load(["oojs-ui-core.styles", "oojs-ui.styles.indicators",
                      "oojs-ui.styles.icons-editing-core", "oojs-ui.styles.icons-interactions"]);
    } catch (e) {}
  }
}

// ── OOUI 모양 단추(OOUI 스크립트 없이 꼴만 빌림) ──────────────────────
function 단추(글, 갈래) {
  갈래 = 갈래 || {};
  var 겉 = 만들기("span", "oo-ui-widget oo-ui-widget-enabled oo-ui-buttonElement oo-ui-buttonWidget "
    + (갈래.테없음 ? "oo-ui-buttonElement-frameless" : "oo-ui-buttonElement-framed")
    + (갈래.아이콘 ? " oo-ui-iconElement" : "") + (글 ? " oo-ui-labelElement" : "")
    + (갈래.표 ? " oo-ui-indicatorElement" : "") + (갈래.진하게 ? " oo-ui-flaggedElement-progressive" : ""));
  var a = 만들기("a", "oo-ui-buttonElement-button");
  a.setAttribute("role", "button");
  a.tabIndex = 0;
  if (갈래.설명) a.title = 갈래.설명;
  var 그림 = 만들기("span", "oo-ui-iconElement-icon " + (갈래.아이콘 ? 갈래.아이콘 : "oo-ui-iconElement-noIcon"));
  var 이름 = 만들기("span", "oo-ui-labelElement-label" + (갈래.이름숨김 ? " oo-ui-labelElement-invisible" : ""), 글 || 갈래.이름숨김);
  var 표 = 만들기("span", "oo-ui-indicatorElement-indicator " + (갈래.표 ? "oo-ui-indicator-" + 갈래.표 : "oo-ui-indicatorElement-noIndicator"));
  a.appendChild(그림); a.appendChild(이름); a.appendChild(표);
  겉.appendChild(a);
  var 하나 = { 겉: 겉, a: a, 이름: 이름, 켬: true, 할일: null };
  하나.켜기 = function (켬) {
    하나.켬 = 켬;
    겉.classList.toggle("oo-ui-widget-enabled", 켬);
    겉.classList.toggle("oo-ui-widget-disabled", !켬);
    a.setAttribute("aria-disabled", 켬 ? "false" : "true");
    a.tabIndex = 켬 ? 0 : -1;
  };
  하나.바쁨 = function (켬) { a.classList.toggle("oo-ui-pendingElement-pending", 켬); };
  function 누름(e) {
    e.preventDefault();
    if (!하나.켬 || !하나.할일) return;
    하나.할일(e);
  }
  a.addEventListener("click", 누름);
  a.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") 누름(e); });
  return 하나;
}

// ── 공용 ─────────────────────────────────────────────────────────────
var 공 = {
  서버: 서버, 영역: 영역,
  만들기: 만들기, 저장: 저장, 지금쪽: 지금쪽, 편집상자: 편집상자, 보이나: 보이나, 편집글: 편집글,
  초글: 초글, 판형글: 판형글, 단바꾸기: 단바꾸기, 선택글: 선택글, 확인: 확인, 단추: 단추,
  모델: function () { return 고름.모델 === "hanmun" && 고름.국한문있음 ? "hanmun" : "hangul"; },
  단: function () { return 고름.단; },
  띄움: function () { return 고름.띄움; },
  도구: {},                          // 이름 → {단추, 시작}  (인식 · 교정이 채움)
};

/** 인식 · 교정 파일이 자기를 알림 — 두 번 실리면 false */
공.들임 = function (이름, 글, 설명, 시작, 갈래) {
  if (공.도구[이름]) return false;
  공.도구[이름] = { 글: 글, 설명: 설명, 시작: 시작, 갈래: 갈래 || {} };
  if (묶음) 묶음채우기();            // 묶음을 세운 뒤에 실린 파일(시험 화면처럼 따로 불러올 때)
  return true;
};

// ── 알림(위키 알림 · 화면 읽기용 한 칸) ──────────────────────────────
공.알림 = function (글, 종류) {
  var 칸 = document.getElementById("옛한글OCR-알림");
  if (!칸) {
    칸 = 만들기("div", "옛한글OCR-숨김");
    칸.id = "옛한글OCR-알림";
    칸.setAttribute("role", "status");
    document.body.appendChild(칸);
  }
  칸.textContent = 글 || "";
  if (글 && window.mw && typeof mw.notify === "function") {
    mw.notify(글, { tag: "old-hangul-ocr", type: 종류 || "info", autoHide: 종류 !== "error", title: "옛한글 OCR" });
  }
};

// ── 로그 — 잘 안 읽힌 쪽을 알릴 때 복사해 붙일 글(도구마다 마지막 한 번만) ──
var 로그 = { 인식: "", 교정: "" };
var 로그이름 = { 인식: "인식 로그", 교정: "교정 로그" };

function 시각글(d) {
  function p(n) { return String(n).padStart(2, "0"); }
  var 차 = -d.getTimezoneOffset();
  return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " "
       + p(d.getHours()) + ":" + p(d.getMinutes()) + ":" + p(d.getSeconds())
       + " (UTC" + (차 >= 0 ? "+" : "-") + p(Math.floor(Math.abs(차) / 60)) + ":" + p(Math.abs(차) % 60) + ")";
}

/** 문서 이름 · 주소 · 실행 환경 — 쪽과 상관없이 늘 적는 것 */
공.로그머리 = function (도구, 쪽, 언제) {
  var c = mw.config.get(["wgServer", "wgArticlePath", "wgFormattedNamespaces", "wgNamespaceNumber", "wgCurRevisionId"]);
  var 제목 = 쪽 ? ((c.wgFormattedNamespaces || {})[c.wgNamespaceNumber] || "페이지") + ":" + 쪽.파일 + "/" + 쪽.쪽 : "(못 찾음)";
  var 상자 = 편집상자();
  return [
    ["도구", 도구],
    ["모델 · 단", 선택글()],
    ["시각", 시각글(언제)],
    ["문서", 제목],
    ["주소", 쪽 ? (c.wgServer || location.origin) + (c.wgArticlePath || "/wiki/$1").replace("$1", encodeURIComponent(제목.replace(/ /g, "_")).replace(/%2F/g, "/").replace(/%3A/g, ":")) : ""],
    ["판", c.wgCurRevisionId || "(새 문서)"],
    ["실행", "서버 " + 서버],
    ["구문 강조", 상자 && !보이나(상자) ? "켜짐" : "꺼짐"],
    ["브라우저", navigator.userAgent],
  ];
};

공.로그쓰기 = function (종류, 줄들) {
  로그[종류] = "[옛한글 OCR 디버그 로그]\n" + 줄들
    .filter(function (v) { return v[1] !== undefined && v[1] !== null && v[1] !== ""; })
    .map(function (v) { return v[0] + ": " + v[1]; }).join("\n");
};

공.로그글 = function (종류) { return 로그[종류]; };

/** 로그 창 — 읽기만 하는 글 칸 + 복사 · 닫기 */
공.로그창 = function (종류) {
  창닫기();
  var 가림 = 만들기("div", "옛한글OCR-가림");
  가림.id = "옛한글OCR-로그창";
  var 창 = 만들기("div", "옛한글OCR-창");
  창.setAttribute("role", "dialog");
  창.setAttribute("aria-label", 로그이름[종류]);
  var 머리 = 만들기("div", "", 로그이름[종류]);
  머리.style.cssText = "font-weight:bold;font-size:1.1em;margin:0 0 4px";
  var 도움 = 만들기("div", "", "잘 안 읽힌 쪽을 알릴 때 이 글을 복사해 붙여 주세요.");
  도움.style.cssText = "font-size:12px;color:var(--color-subtle,#54595d);margin:0 0 8px";
  var 글 = 만들기("textarea");
  글.readOnly = true;
  글.value = 로그[종류] || "아직 기록이 없습니다 — '" + (종류 === "인식" ? "옛한글 OCR" : "전사대조") + "' 를 한 번 누른 뒤에 보세요.";
  var 아래 = 만들기("div", "아래");
  var 복사 = 단추("복사", { 아이콘: "oo-ui-icon-copy" });
  var 닫기 = 단추("닫기");
  var 알림말 = 만들기("span");
  알림말.style.fontSize = "13px";
  복사.할일 = function () {
    var 됨 = function () { 알림말.textContent = "복사했습니다."; };
    var 손으로 = function () {
      글.focus(); 글.select();
      try { document.execCommand("copy"); 됨(); } catch (e) { 알림말.textContent = "Ctrl+C 로 복사해 주세요(골라 두었습니다)."; }
    };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(글.value).then(됨, 손으로);
    else 손으로();
  };
  닫기.할일 = 창닫기;
  아래.appendChild(복사.겉); 아래.appendChild(닫기.겉); 아래.appendChild(알림말);
  창.appendChild(머리); 창.appendChild(도움); 창.appendChild(글); 창.appendChild(아래);
  가림.appendChild(창);
  가림.addEventListener("mousedown", function (e) { if (e.target === 가림) 창닫기(); });
  document.body.appendChild(가림);
  닫기.a.focus();
};

function 창닫기() {
  var 옛 = document.getElementById("옛한글OCR-로그창");
  if (옛) 옛.remove();
}

document.addEventListener("keydown", function (e) {
  if (e.key !== "Escape") return;
  if (document.getElementById("옛한글OCR-로그창")) { 창닫기(); return; }
  if (펼침 && 펼침.보임()) { 펼침.닫기(); 묶음단추.펼.a.focus(); }
});

// ── 서버 ─────────────────────────────────────────────────────────────
/** 서버에 판형 살피기를 맡기고 끝날 때까지 되물음(처음 보는 파일은 1~3분) */
공.서버살피기 = async function (파일, 일) {
  for (;;) {
    var 답 = await 일.기다림(fetch(서버 + "api/inspect?file=" + encodeURIComponent(파일)).then(function (r) { return r.json(); }));
    if (답.상태 === "끝") return 답.값;
    if (답.상태 === "오류" || 답.오류) throw new Error(답.오류 || "서버가 판형을 못 살폈습니다");
    일.진행("이 파일의 판형을 서버에서 살피는 중…", "(" + 답.진행 + " · 이 파일은 처음 한 번만)");
    await 일.쉼(2000);
  }
};

공.서버로 = async function (경로, 몸, 일) {
  var res = await 일.기다림(fetch(서버 + 경로, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(몸),
    signal: 일.신호,
  }));
  var 답 = await 일.기다림(res.json());
  if (!res.ok || 답.오류) throw new Error(답.오류 || ("서버 오류 " + res.status));
  return 답;
};

// ── 상태 띠 — 편집 상자 바로 위(텍스트 변환의 진행 · 되돌리기 띠와 같은 자리) ──
var 띠 = null;
var 자리듣기 = [];
공.자리듣기 = function (f) { 자리듣기.push(f); };
function 자리바뀜() { 자리듣기.forEach(function (f) { try { f(); } catch (e) {} }); }

/** 띠를 꽂을 자리 — 편집 상자 앞(구문 강조가 켜져 상자가 숨었으면 CodeMirror 앞) */
function 띠자리() {
  var 상자 = 편집상자();
  if (!상자) return null;
  if (!보이나(상자) && 상자.parentNode) {
    var cm = 상자.parentNode.querySelector(":scope > .cm-editor, :scope > .CodeMirror");
    if (cm && (cm.compareDocumentPosition(상자) & Node.DOCUMENT_POSITION_FOLLOWING)) return cm;
  }
  return 상자;
}

function 띠세우기() {
  var 자리 = 띠자리();
  if (!자리) return null;
  if (!띠) {
    띠 = 만들기("div", "옛한글OCR-띠");
    띠.id = "옛한글OCR-띠";
    띠.setAttribute("role", "status");
  }
  if (!띠.isConnected || 띠.parentNode !== 자리.parentNode) 자리.parentNode.insertBefore(띠, 자리);
  띠.textContent = "";
  return 띠;
}

/** 진행 중 — 빙글이 · 말 · [취소] */
function 띠진행(말, 작은말, 취소) {
  var b = 띠세우기();
  if (!b) return;
  var 첫 = 만들기("div", "첫줄");
  첫.appendChild(만들기("span", "옛한글OCR-빙글"));
  var 글 = 만들기("span", "말", 말);
  if (작은말) { 글.appendChild(document.createTextNode(" ")); 글.appendChild(만들기("small", "", 작은말)); }
  첫.appendChild(글);
  var 그만 = 단추("취소", { 테없음: true, 진하게: true });
  그만.할일 = 취소;
  첫.appendChild(그만.겉);
  b.appendChild(첫);
  b.dataset.때 = "진행";
  자리바뀜();
}

/**
 * 결과 — 첫 줄 [되돌리기] 말 … [×] · 둘째 줄 작은 글(여럿이면 줄마다)
 * 갈래: {되돌리기: {글, 할일, 켬} | null, 말: 노드|글, 덧: [노드…], 둘째: [노드|글…], 닫기: 함수}
 */
공.띠결과 = function (갈래) {
  var b = 띠세우기();
  if (!b) return null;
  var 첫 = 만들기("div", "첫줄");
  var 되 = null;
  if (갈래.되돌리기) {
    되 = 단추(갈래.되돌리기.글, { 테없음: true, 진하게: true, 아이콘: "oo-ui-icon-undo oo-ui-image-progressive" });
    되.a.dataset.ohocr = "되돌리기";
    되.할일 = 갈래.되돌리기.할일;
    되.켜기(갈래.되돌리기.켬 !== false);
    첫.appendChild(되.겉);
  }
  var 말 = 만들기("span", "말");
  if (갈래.말) 말.appendChild(typeof 갈래.말 === "string" ? document.createTextNode(갈래.말) : 갈래.말);
  첫.appendChild(말);
  (갈래.덧 || []).forEach(function (x) { 첫.appendChild(x); });
  var 닫 = 단추("", { 테없음: true, 아이콘: "oo-ui-icon-close", 이름숨김: "닫기", 설명: 갈래.닫기설명 || "닫기" });
  닫.a.dataset.ohocr = "닫기";
  닫.할일 = 갈래.닫기;
  첫.appendChild(닫.겉);
  b.appendChild(첫);
  var 둘 = (갈래.둘째 || []).filter(Boolean);
  if (둘.length) {
    var 칸 = 만들기("div", "둘째줄");
    둘.forEach(function (x) {
      var 줄 = typeof x === "string" ? 만들기("div", "", x) : x;
      칸.appendChild(줄);
    });
    b.appendChild(칸);
  }
  b.dataset.때 = "결과";
  자리바뀜();
  return { 되돌리기: 되 };
};

공.띠걷기 = function () {
  if (띠) { 띠.remove(); 띠 = null; 자리바뀜(); }
  document.querySelectorAll(".옛한글OCR-띠아래").forEach(function (e) { e.remove(); });
};

/** 띠 바로 아래에 칸 하나(전사대조 목록 · '못씀' 칸) */
공.띠아래 = function (칸) {
  칸.classList.add("옛한글OCR-띠아래");
  if (띠 && 띠.parentNode) 띠.parentNode.insertBefore(칸, 띠.nextSibling);
  else { var 자리 = 띠자리(); if (자리) 자리.parentNode.insertBefore(칸, 자리); }
  자리바뀜();
};
공.자리바뀜 = 자리바뀜;

// ── 결과 하나만 — 새 일을 시작하거나 쪽을 옮기면 앞 결과(칠 · 띠 · 목록)를 걷음 ──
var 결과 = null;
공.결과놓기 = function (걷기) {          // 띠는 그대로 — 부른 쪽이 곧 새 결과를 그림
  var 옛 = 결과;
  결과 = 걷기;
  if (옛 && 옛 !== 걷기) { try { 옛(); } catch (e) { console.error(e); } }
};
공.결과걷기 = function () {
  var 옛 = 결과;
  결과 = null;
  if (옛) { try { 옛(); } catch (e) { console.error(e); } }
  if (!바쁨) 공.띠걷기();
};

// ── 일 — 한 번에 하나. 도는 동안 두 단추를 막고 편집 상자를 읽기만으로 ──
var 바쁨 = null;
function 취소오류() { var e = new Error("취소했습니다"); e.취소 = true; return e; }

공.일 = function (이름) {
  if (바쁨) return null;
  공.결과걷기();
  var 멈춤들 = [];
  var 끊개 = window.AbortController ? new AbortController() : null;
  var 일 = { 이름: 이름, 취소됨: false, 신호: 끊개 ? 끊개.signal : undefined };
  일.취소 = function () {
    if (일.취소됨) return;
    일.취소됨 = true;
    if (끊개) 끊개.abort();
    멈춤들.splice(0).forEach(function (f) { f(); });
  };
  일.기다림 = function (p) {
    return new Promise(function (ok, no) {
      if (일.취소됨) { no(취소오류()); return; }
      var 끝남 = false;
      var 멈춤 = function () { if (!끝남) { 끝남 = true; no(취소오류()); } };
      멈춤들.push(멈춤);
      Promise.resolve(p).then(function (v) {
        if (끝남) return;
        끝남 = true; 멈춤들.splice(멈춤들.indexOf(멈춤) >>> 0, 1); ok(v);
      }, function (e) {
        if (끝남) return;
        끝남 = true; 멈춤들.splice(멈춤들.indexOf(멈춤) >>> 0, 1); no(일.취소됨 ? 취소오류() : e);
      });
    });
  };
  일.쉼 = function (ms) { return 일.기다림(new Promise(function (ok) { setTimeout(ok, ms); })); };
  일.진행 = function (말, 작은말) { if (바쁨 === 일) 띠진행(말, 작은말, 일.취소); };
  일.끝 = function () {
    if (바쁨 !== 일) return;
    바쁨 = null;
    document.querySelectorAll("textarea[data-ohocr-lock]").forEach(function (t) {
      t.readOnly = false;
      t.removeAttribute("data-ohocr-lock");
    });
    if (띠 && 띠.dataset.때 === "진행") 공.띠걷기();
    단추맞추기();
  };
  var 상자 = 편집상자();
  if (상자 && !상자.readOnly) { 상자.readOnly = true; 상자.setAttribute("data-ohocr-lock", "1"); }
  바쁨 = 일;
  단추맞추기();
  return 일;
};
공.바쁨 = function () { return 바쁨; };

// ── 도구모음 묶음 [옛한글 OCR | 전사대조 | ▾] ──────────────────────────
var 묶음 = null, 묶음단추 = {}, 펼침 = null;

function 단추맞추기() {
  Object.keys(공.도구).forEach(function (이름) {
    var b = 묶음단추[이름];
    if (!b) return;
    b.켜기(!바쁨);
    b.바쁨(!!바쁨 && 바쁨.이름 === 이름);
  });
  if (묶음단추.펼) 묶음단추.펼.a.title = "옛한글 OCR 설정 — " + 선택글();
}

function 묶음만들기() {
  묶음 = 만들기("span", "oo-ui-widget oo-ui-widget-enabled oo-ui-buttonGroupWidget");
  묶음.id = "옛한글OCR-묶음";
  묶음채우기();
}

function 묶음채우기() {
  var 겉 = 묶음;
  겉.textContent = "";
  묶음단추 = {};
  if (펼침) 펼침.판.remove();
  ["인식", "교정"].forEach(function (이름) {
    var 도 = 공.도구[이름];
    if (!도) return;
    var b = 단추(도.글, { 아이콘: 도.갈래.아이콘 ? "옛한글OCR-아이콘" + (이름 === "교정" ? " 교정" : "") : "", 설명: 도.설명 });
    b.a.dataset.ohocr = 이름;
    b.할일 = function () { if (펼침) 펼침.닫기(); 도.시작(); };
    묶음단추[이름] = b;
    겉.appendChild(b.겉);
  });
  var 펼 = 단추("", { 표: "down", 이름숨김: "옛한글 OCR 설정" });
  펼.a.dataset.ohocr = "설정";
  펼.a.setAttribute("aria-haspopup", "dialog");
  펼.a.setAttribute("aria-expanded", "false");
  펼.할일 = function () { 펼침.보임() ? 펼침.닫기() : 펼침.열기(); };
  묶음단추.펼 = 펼;
  겉.appendChild(펼.겉);
  펼침 = 펼침만들기(펼);
  단추맞추기();
}

/** ▾ 아래 펼침 메뉴 — 설정 · 영역 지정 · 로그 */
function 펼침만들기(펼) {
  var 판 = 만들기("div", "옛한글OCR-펼침");
  판.id = "옛한글OCR-펼침";
  판.setAttribute("role", "dialog");
  판.setAttribute("aria-label", "옛한글 OCR 설정");
  판.hidden = true;

  var 칸 = function (제목) {
    var c = 만들기("div", "칸");
    if (제목) c.appendChild(만들기("div", "제목", 제목));
    판.appendChild(c);
    return c;
  };
  var 고름줄 = function (부모, 형, 이름, 값, 글, 켬) {
    var 줄 = 만들기("label", "줄");
    var i = 만들기("input");
    i.type = 형; if (이름) i.name = 이름; if (값) i.value = 값;
    i.checked = !!켬;
    줄.appendChild(i);
    줄.appendChild(document.createTextNode(글));
    부모.appendChild(줄);
    return i;
  };

  // 모델 · 단 — 이름 옆 내림 목록
  var 고르기 = function (부모, 제목, 값들, 지금) {
    var 줄 = 만들기("label", "줄");
    줄.appendChild(만들기("span", "제목", 제목));
    var 고름칸 = 만들기("select");
    값들.forEach(function (v) {
      var o = 만들기("option", "", v[1]);
      o.value = v[0];
      고름칸.appendChild(o);
    });
    고름칸.value = 지금;
    줄.appendChild(고름칸);
    부모.appendChild(줄);
    return 고름칸;
  };
  var 고름칸 = 칸("");
  var 모델고름 = 고르기(고름칸, "모델", [["hangul", "근대 순한글"], ["hanmun", "근대 국한문"]], 고름.모델);
  모델고름.addEventListener("change", function () {
    고름.모델 = 모델고름.value; 저장("모델", 모델고름.value); 단추맞추기();
  });
  // 서버에 국한문 모델이 없으면 못 고르게(`/api/health`)
  if (서버) {
    fetch(서버 + "api/health").then(function (r) { return r.json(); }).then(function (h) {
      if (h && h.모델들 && !h.모델들.hanmun) {
        고름.국한문있음 = false;
        var 국 = 모델고름.querySelector("option[value=hanmun]");
        국.disabled = true;
        국.textContent = "근대 국한문 — 이 서버에는 없음";
        if (모델고름.value === "hanmun") 모델고름.value = "hangul";
        단추맞추기();
      }
    }).catch(function () {});
  }
  var 단고름 = 고르기(고름칸, "단", [["auto", "자동"], ["1", "1단"], ["2", "2단"], ["3", "3단"], ["4", "4단"], ["5", "5단"]],
                    고름.단 ? String(고름.단) : "auto");
  단고름.addEventListener("change", function () {
    고름.단 = 단고름.value === "auto" ? null : parseInt(단고름.value, 10);
    저장("단", 단고름.value); 단추맞추기();
  });

  var 덧칸 = 칸("");
  var 띄 = 고름줄(덧칸, "checkbox", "", "", "띄어쓰기 자동 감지", 고름.띄움);
  띄.addEventListener("change", function () { 고름.띄움 = 띄.checked; 저장("띄움", 띄.checked ? "켬" : "끔"); 단추맞추기(); });

  var 영역고리 = null;
  if (영역) {
    판.appendChild(만들기("hr"));
    영역고리 = 만들기("a", "고리 가운데", "영역 지정 ↗");
    영역고리.target = "_blank";
    영역고리.rel = "noopener";
    영역고리.title = "이 쪽 스캔을 영역 지정 도구에서 엽니다(상자를 쳐서 그 자리만 읽기)";
    var 영역주소 = function () {
      var 쪽 = 지금쪽();                     // 순서대로 편집으로 쪽을 옮겼을 수 있어 누를 때마다 새로
      var 값 = { host: location.host };
      if (쪽) { 값.file = 쪽.파일; 값.page = String(쪽.쪽); }
      if (공.모델() !== "hangul") 값.model = 공.모델();
      영역고리.href = 영역 + "?" + new URLSearchParams(값);
    };
    영역고리.addEventListener("mousedown", 영역주소);       // 가운데 단추로 새 탭에 열 때도
    영역고리.addEventListener("click", function () { 영역주소(); setTimeout(닫기, 0); });
    영역주소();
    판.appendChild(영역고리);
  }

  판.appendChild(만들기("hr"));
  var 로그들 = 만들기("div", "로그들");
  ["인식", "교정"].forEach(function (종류) {
    if (!공.도구[종류]) return;
    var g = 만들기("a", "고리", 로그이름[종류]);
    g.href = "#";
    g.setAttribute("role", "button");
    g.dataset.ohocr = 종류 + "로그";
    g.title = 종류 === "인식" ? "마지막으로 읽은 쪽의 기록(쪽 · 시간 · 판정 …)" : "마지막으로 맞댄 쪽의 기록(쪽 · 시간 · 일치율 …)";
    g.addEventListener("click", function (e) { e.preventDefault(); 닫기(); 공.로그창(종류); });
    로그들.appendChild(g);
  });
  판.appendChild(로그들);

  function 자리잡기() {
    var r = 묶음.getBoundingClientRect();
    var 폭 = 판.offsetWidth || 260;
    var 왼 = Math.max(8, Math.min(r.left, document.documentElement.clientWidth - 폭 - 8));
    판.style.left = (왼 + window.scrollX) + "px";
    판.style.top = (r.bottom + window.scrollY + 2) + "px";
  }
  function 열기() {
    if (!판.isConnected) document.body.appendChild(판);
    판.hidden = false;
    자리잡기();
    펼.a.setAttribute("aria-expanded", "true");
    var 첫 = 판.querySelector("input:checked") || 판.querySelector("input");
    if (첫) 첫.focus();
  }
  function 닫기() {
    판.hidden = true;
    펼.a.setAttribute("aria-expanded", "false");
  }
  document.addEventListener("mousedown", function (e) {
    if (!판.hidden && !판.contains(e.target) && !펼.겉.contains(e.target)) 닫기();
  });
  window.addEventListener("resize", function () { if (!판.hidden) 자리잡기(); });
  document.body.appendChild(판);
  return { 열기: 열기, 닫기: 닫기, 보임: function () { return !판.hidden; }, 판: 판 };
}

/**
 * 도구모음 안 자리 — 기본 묶음(서식 · 넣기) 바로 뒤, 곧 덧붙은 도구들 가운데 맨 왼쪽.
 * ⚠ 다른 소도구가 늦게 떠서 넣기 뒤에 끼어들 수 있어 묶음이 바뀔 때마다 다시 맞춤
 */
function 무리자리(칸, 무리) {
  var 기본 = 칸.querySelectorAll(":scope > .group-format, :scope > .group-insert");
  var 앞 = 기본.length ? 기본[기본.length - 1] : null;
  var 뒤 = 앞 ? 앞.nextElementSibling : 칸.firstElementChild;
  if (뒤 !== 무리) 칸.insertBefore(무리, 뒤);
}

/** 묶음을 도구모음에 — 없으면 편집 상자 위 한 줄에 */
function 도구모음에() {
  var 칸 = document.getElementById("wikiEditor-section-main");
  if (!칸 || !묶음) return false;
  var 무리 = document.getElementById("옛한글OCR-무리");
  if (!무리) {
    무리 = 만들기("div", "group group-old-hangul-ocr");
    무리.id = "옛한글OCR-무리";
    무리.setAttribute("rel", "old-hangul-ocr");
  }
  무리자리(칸, 무리);
  if (묶음.parentNode !== 무리) 무리.appendChild(묶음);
  if (!칸.dataset.ohocrWatch && window.MutationObserver) {
    칸.dataset.ohocrWatch = "1";
    var 남은번 = 20;                     // 같은 자리를 다투는 다른 소도구와 끝없이 밀지 않게
    var 지켜봄 = new MutationObserver(function () {
      if (무리.parentNode !== 칸) return;
      if (--남은번 < 0) { 지켜봄.disconnect(); return; }
      무리자리(칸, 무리);
    });
    지켜봄.observe(칸, { childList: true });
  }
  var 옛줄 = document.getElementById("옛한글OCR-도구");
  if (옛줄) 옛줄.remove();
  return true;
}

function 상자위에() {
  if (!묶음 || 묶음.isConnected) return;
  var 자리 = 띠자리();
  if (!자리) return;
  var 줄 = 만들기("div");
  줄.id = "옛한글OCR-도구";
  줄.appendChild(묶음);
  자리.parentNode.insertBefore(줄, 자리);
}

function 세우기() {
  if (묶음 || !지금쪽() || !편집상자() || !Object.keys(공.도구).length) return;
  꼴넣기();
  묶음만들기();
  var 판 = window.mw && mw.loader && mw.loader.getState ? mw.loader.getState("ext.wikiEditor") : null;
  if (window.mw && mw.hook && 판 && ["registered", "error", "missing"].indexOf(판) < 0) {
    mw.hook("wikiEditor.toolbarReady").add(function () { 도구모음에(); });
    setTimeout(function () { if (!묶음.isConnected) 상자위에(); }, 8000);   // 도구모음이 끝내 안 뜨면
  } else {
    상자위에();
  }
  // 순서대로 편집으로 쪽을 옮기면 앞 쪽의 결과(칠 · 띠 · 목록)를 걷음
  if (/[?&]prp_editinsequence=/i.test(location.search)) {
    window.addEventListener("hashchange", function () { 공.결과걷기(); });
  }
}

/** 인식 · 교정 파일이 다 실린 뒤 부름(같은 묶음 안에서 둘째 파일 끝) */
공.세우기 = function () {
  if (!window.mw || !mw.loader) return;
  mw.loader.using(["mediawiki.util"]).then(function () {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", 세우기);
    else 세우기();
  }, function () {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", 세우기);
    else 세우기();
  });
};

window.옛한글OCR = 공;
})();
