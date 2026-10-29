/*
 * 전사대조 — '페이지:' 편집 창에서 전사된 글을 스캔과 맞대어 틀렸을 만한 자리를 편집 상자 안에 칠함.
 *
 * 편집 도구모음의 '전사대조' 단추. 셈은 서버, 이 파일은 화면(칠하기 · 후보 목록 · 바꾸기 · 되돌리기)만.
 * 단추 · 띠 · 로그는 `공용.js`(`window.옛한글OCR`).
 */
(function (전역) {
"use strict";
if (typeof document === "undefined") return;
var 공 = 전역.옛한글OCR;
if (!공 || !공.들임("교정", "전사대조", "지금 편집 상자의 전사문을 이 쪽 스캔과 맞대어 틀렸을 만한 글자를 짚습니다", 시작, { 아이콘: true })) return;

var 편집상자 = 공.편집상자, 지금쪽 = 공.지금쪽, 보이나 = 공.보이나;

var 판, 깔개 = null, 후보들 = [], 어긋남보기 = false, 끝난것보기 = false, 목록보임 = true, 띠쪽 = null;
var 고친차례 = [];                   // 바꾸기 · 넣기 한 차례(마지막 것부터 되돌림)
// 합의 = 다르게 한 번 더 잘라도 남은 것. 안 남은 것은 대개 자르기 실수라 접어 둠
function 확실(c) { return c.합의 !== false && c.갈래 !== "빠짐" && c.갈래 !== "더들어감"; }
function 보일것(c) { return 어긋남보기 || 확실(c); }
function 바꿀수(c) { return (c.갈래 === "바뀜" || c.갈래 === "모르는자모") && c.스캔; }
function 넣을수(c) { return c.갈래 === "누락" && c.스캔; }
function 되돌릴수(c) { return (c.끝남 === "바꿈" || c.끝남 === "넣음") && !!c.고친; }

var 이름 = { "바뀜": "글자가 다름", "모르는자모": "모르는 자모", "깨진글자": "깨진 글자", "누락": "전사문에 글자 누락 의심", "빠짐": "스캔에 글자가 더 있음", "더들어감": "전사문에 글자가 더 있음" };
var 짧은이름 = { "바뀜": "글자 다름", "모르는자모": "모르는 자모", "깨진글자": "깨진 글자", "누락": "누락 · 글자 수 어긋남" };
var 색 = { "바뀜": "rgba(255,80,80,.40)", "모르는자모": "rgba(255,160,0,.40)", "깨진글자": "rgba(170,80,255,.38)", "누락": "rgba(80,140,255,.35)", "빠짐": "rgba(80,140,255,.35)", "더들어감": "rgba(80,140,255,.35)" };

/** 맞댄 결과 · 걸린 시간 */
function 로그본문(살핀, 답, 때, 처음) {
  var 줄 = [];
  if (살핀) 줄.push(["판형 살핀 값", 공.판형글(살핀.단)
                       + (살핀.자간비 ? " · 자간비 " + 살핀.자간비.toFixed(3) : " · 자간비 없음(기본값)")
                       + (살핀.읽기자간비 ? " · 읽기 자간비 " + 살핀.읽기자간비.toFixed(3) : "")
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
        " · 해시 " + (답.debug.OCR해시 || "?")]);
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
  var 시간 = Object.keys(때).map(function (k) { return k + " " + 공.초글(때[k]); });
  시간.push("전체 " + 공.초글(performance.now() - 처음));
  줄.push(["걸린 시간", 시간.join(" · ")]);
  return 줄;
}

// ── 편집 상자에 칠하기 — 상자 뒤에 같은 글꼴의 판을 깔고 바탕만 칠함 ──
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
  깔개.맞추기 = 맞추기;
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

공.자리듣기(function () { if (깔개) 깔개.맞추기(); });   // 띠 · 목록이 생기거나 걷히면 상자가 밀림

function 걷기() {
  if (!깔개) return;
  깔개.끝내기();
  깔개.판.remove();
  깔개.상자.style.position = 깔개.옛모양.position;
  깔개.상자.style.backgroundColor = 깔개.옛모양.backgroundColor;
  깔개 = null;
}

/** 이전 검사 결과는 표시와 조작 상태를 함께 버림. 편집 글은 건드리지 않음. */
function 결과걷기() {
  후보들 = [];
  고친차례 = [];
  기준글 = null;
  고른것 = null;
  끝난것보기 = false;
  목록보임 = true;
  띠쪽 = null;
  걷기();
  if (판) {
    판.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
    판.remove();
    판 = null;
  }
}

// 사람이 고친 만큼 자리를 옮긴다 — 고친 구간에 걸린 후보는 '손댐', 뒤의 것은 민다
var 기준글 = null;
// 소도구가 직접 하는 고침 {시작, 끝, 글} — 넣은 글자가 앞뒤와 같으면 앞뒤 비교로는 자리를 잘못 짚으므로 따로 알림
var 아는고침 = null;
function 따라가기() {
  var 상자 = 편집상자();
  if (!상자 || 기준글 === null) return;
  var 새 = 상자.value, 옛 = 기준글;
  if (새 === 옛) return;
  var a, 옛끝, 차 = 새.length - 옛.length, k = 아는고침;
  var 앎 = !!k && 새 === 옛.slice(0, k.시작) + k.글 + 옛.slice(k.끝);
  if (앎) { a = k.시작; 옛끝 = k.끝; }
  else {
    var n = Math.min(옛.length, 새.length), b = 0;
    a = 0;
    while (a < n && 옛.charCodeAt(a) === 새.charCodeAt(a)) a++;
    while (b < n - a && 옛.charCodeAt(옛.length - 1 - b) === 새.charCodeAt(새.length - 1 - b)) b++;
    옛끝 = 옛.length - b;
  }
  후보들.forEach(function (c) {
    if (c.끝남) {
      // 바꾼 · 넣은 글자 자리도 따라감(되돌리기용) — 그 자리를 사람이 고치면 되돌리기를 접음
      var g = c.고친;
      if (!g || c.되돌리는중) return;
      if (옛끝 <= g.시작) g.시작 += 차;
      else if (a < g.시작 + g.길이) c.고친 = null;
      return;
    }
    // 누락의 앞뒤 원문은 소도구의 고침만 반영해 다시 적음(다른 고침이면 넣기를 막음)
    var 맞던 = 앎 && c.갈래 === "누락" && c.시작 >= c.앞원문.length
      && 옛.slice(c.시작 - c.앞원문.length, c.시작) === c.앞원문 && 옛.slice(c.시작, c.시작 + c.뒤원문.length) === c.뒤원문;
    if (c.갈래 === "누락" && a <= c.시작 && c.시작 <= 옛끝) { c.끝남 = "손댐"; return; }
    if (c.끝 <= a) { /* 앞쪽 — 그대로 */ }
    else if (c.시작 >= 옛끝) { c.시작 += 차; c.끝 += 차; }
    else { c.끝남 = "손댐"; return; }
    if (맞던) {
      c.앞원문 = 새.slice(Math.max(0, c.시작 - 6), c.시작);
      c.뒤원문 = 새.slice(c.시작, c.시작 + 6);
    }
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
    var 끝 = c.고친 ? c.고친.시작 + c.고친.길이 : c.갈래 === "누락" ? c.시작 : Math.max(c.끝, c.시작 + 1);
    상자.setSelectionRange(c.고친 ? c.고친.시작 : c.시작, 끝);
    상자.scrollTop = Math.max(0, y - 상자.clientHeight / 3);
  }
  if (깔개) 깔개.그리기();
  목록그리기();
}

function 바꾸기(c) {
  var 상자 = 편집상자();
  if (상자.value.slice(c.시작, c.끝) !== c.원문) {
    공.알림("그 자리 글이 그사이 바뀌어 바꾸지 않았습니다 — 직접 고쳐 주세요.", "warn");
    return;
  }
  // 원문 구간 안에서 전사 글자만 바꾼다(구간에 틀이 끼어 있으면 손대지 않음)
  var 자리 = c.원문.indexOf(c.전사);
  if (자리 < 0 || c.원문.length !== c.전사.length) {
    공.알림("이 자리는 틀과 섞여 있어 자동으로 바꾸지 않습니다 — 직접 고쳐 주세요.", "warn");
    return;
  }
  글넣기(상자, c.시작, c.끝, c.스캔);
  고침끝(c, "바꿈");
}

// 누락 의심 자리(다음 글자 앞)에 스캔 글자를 끼워 넣는다 — 앞뒤 원문이 맞댈 때와 같을 때만
function 넣기(c) {
  var 상자 = 편집상자();
  if (상자.value.slice(c.시작 - c.앞원문.length, c.시작) !== c.앞원문
      || 상자.value.slice(c.시작, c.시작 + c.뒤원문.length) !== c.뒤원문) {
    공.알림("그 자리 글이 그사이 바뀌어 넣지 않았습니다 — 직접 고쳐 주세요.", "warn");
    return;
  }
  글넣기(상자, c.시작, c.끝, c.스캔);
  고침끝(c, "넣음");
}

function 고침끝(c, 끝남) {
  c.끝남 = 끝남;
  c.고친 = { 시작: c.시작, 길이: c.스캔.length };
  고친차례.push(c);
  if (깔개) 깔개.그리기();
  목록그리기();
}

/** 바꾸기 · 넣기 되돌리기 — 넣은 글자가 그 자리에 그대로 있을 때만 원래 글로 */
function 되돌리기(c) {
  var 상자 = 편집상자(), g = c.고친;
  if (!상자 || !g || 상자.value.slice(g.시작, g.시작 + g.길이) !== c.스캔) {
    c.고친 = null;
    공.알림("그 자리 글이 그사이 바뀌어 되돌리지 않았습니다 — 직접 고쳐 주세요.", "warn");
    목록그리기();
    return;
  }
  c.되돌리는중 = true;
  try { 글넣기(상자, g.시작, g.시작 + g.길이, c.원문); }
  finally { c.되돌리는중 = false; }
  c.시작 = g.시작;
  c.끝 = g.시작 + c.원문.length;
  c.끝남 = null;
  c.고친 = null;
  if (c.갈래 === "누락") {
    c.앞원문 = 상자.value.slice(Math.max(0, c.시작 - 6), c.시작);
    c.뒤원문 = 상자.value.slice(c.시작, c.시작 + 6);
  }
  var i = 고친차례.indexOf(c);
  if (i >= 0) 고친차례.splice(i, 1);
  if (깔개) 깔개.그리기();
  목록그리기();
}

function 마지막되돌리기() {
  for (var i = 고친차례.length - 1; i >= 0; i--) {
    if (되돌릴수(고친차례[i])) { 되돌리기(고친차례[i]); return; }
  }
}

/** [시작, 끝) 을 글로 — execCommand 로 넣어야 Ctrl+Z 가 됨(안 되면 setRangeText) · 고친 자리는 `따라가기` 에 알려 둠 */
function 글넣기(상자, 시작, 끝, 글) {
  상자.focus({ preventScroll: true });
  상자.setSelectionRange(시작, 끝);
  아는고침 = { 시작: 시작, 끝: 끝, 글: 글 };
  try {
    var 됨 = false;
    try { 됨 = 글 ? document.execCommand("insertText", false, 글) : document.execCommand("delete", false); } catch (e) { 됨 = false; }
    if (!됨) {
      상자.setRangeText(글, 시작, 끝, "end");
      상자.dispatchEvent(new Event("input", { bubbles: true }));
    }
    따라가기();
  } finally {
    아는고침 = null;
  }
}

// ── 목록 ──
function 목록그리기() {
  띠맞추기();
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
    var 말 = { "넘김": "넘긴 곳", "바꿈": "바꾼 곳", "넣음": "넣은 곳", "손댐": "손댄 곳" };
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
      + (c === 고른것 ? "background:#fef6e7;" : "");
    var 흐림 = c.끝남 ? "opacity:.45;" : "";
    if (c.그림) {
      var im = document.createElement("img");
      im.src = c.그림;
      im.style.cssText = "height:96px;border:1px solid #c8ccd1;flex:none;cursor:zoom-in;" + 흐림;
      im.title = "누르면 크게";
      im.addEventListener("click", function () { im.style.height = im.style.height === "96px" ? "220px" : "96px"; });
      줄.appendChild(im);
    }
    var 글 = document.createElement("div");
    글.style.cssText = "flex:1;min-width:0;" + 흐림;
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
      x.addEventListener("click", function () {
        if (후보들.indexOf(c) < 0) return;   // 제거된 검사 결과의 단추/클로저도 실행하지 않음
        할일();
      });
      단.appendChild(x);
      return x;
    }
    단추하나("자리 보기", function () { 자리보기(c); });
    if (!c.끝남 && 바꿀수(c)) {
      단추하나("바꾸기 → " + c.스캔, function () { 바꾸기(c); });
    }
    if (!c.끝남 && 넣을수(c)) {
      단추하나("넣기 → " + c.스캔, function () { 넣기(c); });
    }
    if (되돌릴수(c)) 단추하나("되돌리기", function () { 되돌리기(c); });
    if (!c.끝남) 단추하나("넘기기", function () { c.끝남 = "넘김"; if (깔개) 깔개.그리기(); 목록그리기(); });
    줄.appendChild(단);
    몸.appendChild(줄);
  }
}

// ── 결과 띠 — [↶ 되돌리기] 볼 곳 N곳 [목록 접기] [×] · 아래 줄에 색 안내 ──
function 띠세우기(답, 칠함) {
  var 말 = 공.만들기("span");
  var 접기 = 공.단추("목록 접기", { 테없음: true, 진하게: true });
  접기.a.dataset.ohocr = "목록";
  접기.할일 = function () {
    목록보임 = !목록보임;
    if (판) 판.style.display = 목록보임 ? "" : "none";
    띠맞추기();
    공.자리바뀜();
  };
  // 색 안내 — 이 쪽 후보에 나온 갈래만
  var 나온 = {};
  후보들.forEach(function (c) { 나온[c.갈래 === "빠짐" || c.갈래 === "더들어감" ? "누락" : c.갈래] = true; });
  var 색줄 = 공.만들기("div");
  Object.keys(짧은이름).forEach(function (k) {
    if (!나온[k]) return;
    var 빛 = 공.만들기("span", "빛");
    빛.style.background = 색[k].replace(/[\d.]+\)$/, ".7)");
    색줄.appendChild(빛);
    색줄.appendChild(document.createTextNode(짧은이름[k]));
  });
  if (색줄.childNodes.length) 색줄.appendChild(document.createTextNode(" — 칠은 저장되지 않습니다."));
  var 둘째 = [색줄.childNodes.length ? 색줄 : null];
  if (!칠함 && 후보들.length) 둘째.push("구문 강조가 켜져 있어 편집 상자에 칠하지 못했습니다(끄면 칠합니다) — 아래 목록에서 보세요.");
  if (답.흔들림) {
    둘째.push(공.만들기("div", "경고", "⚠ 이 쪽은 스캔과 전사문이 잘 맞춰지지 않았습니다 — 목록에 헛경보가 많을 수 있습니다."));
  } else if (답.흔들린열) {
    둘째.push("맞대기가 흔들린 열 " + 답.흔들린열 + "개는 뺐습니다.");
  }
  var 띠 = 공.띠결과({
    되돌리기: { 글: "되돌리기", 할일: 마지막되돌리기, 켬: false },
    말: 말,
    덧: 후보들.length ? [접기.겉] : [],
    둘째: 둘째,
    닫기: 공.결과걷기,
    닫기설명: "칠과 목록 닫기(고친 글은 그대로)",
  });
  띠쪽 = { 말: 말, 접기: 접기, 되돌리기: 띠 && 띠.되돌리기, 일치: 답.일치 };
  띠맞추기();
}

function 띠맞추기() {
  if (!띠쪽) return;
  var 남은 = 후보들.filter(function (c) { return 보일것(c) && !c.끝남; }).length;
  띠쪽.말.textContent = 후보들.length || 남은 ? "볼 곳 " + 남은 + "곳" : "스캔과 다른 곳을 찾지 못했습니다";
  var 작 = 공.만들기("small", "", " (스캔과 " + Math.round(띠쪽.일치 * 100) + "% 맞음)");
  띠쪽.말.appendChild(작);
  띠쪽.접기.이름.textContent = 목록보임 ? "목록 접기" : "목록 펼치기";
  if (띠쪽.되돌리기) {
    var 있음 = 고친차례.some(되돌릴수);
    띠쪽.되돌리기.켜기(있음);
    띠쪽.되돌리기.a.title = 있음 ? "마지막으로 바꾸거나 넣은 글자를 되돌립니다" : "되돌릴 고침이 없습니다";
  }
}

function 판세우기() {
  if (판) 판.remove();
  끝난것보기 = false;
  판 = document.createElement("div");
  판.id = "전사대조-판";
  판.style.cssText = "margin:0 0 8px;padding:8px 12px;border:1px solid var(--border-color-subtle,#c8ccd1);border-top:0;"
    + "background:var(--background-color-base,#fff);max-height:26em;overflow:auto";
  var 바뀜수 = 후보들.filter(확실).length;
  var 어긋남수 = 후보들.length - 바뀜수;
  if (어긋남수) {
    // 다르게 잘라 보면 사라지는 후보는 대개 자르기 실수라 접어 둔다
    var 펼 = document.createElement("button");
    펼.type = "button"; 펼.className = "cdx-button";
    펼.style.cssText = "font-size:12px;margin-bottom:4px";
    var 글 = function () { 펼.textContent = (어긋남보기 ? "자르기에 따라 달라진 곳 " + 어긋남수 + "곳 접기"
                                              : "자르기에 따라 달라진 곳 " + 어긋남수 + "곳도 보기 (자르기 실수가 많음)"); };
    글();
    펼.addEventListener("click", function () { 어긋남보기 = !어긋남보기; 글(); if (깔개) 깔개.그리기(); 목록그리기(); });
    판.appendChild(펼);
  }
  var 안내 = document.createElement("div");
  안내.style.cssText = "font-size:12px;color:#72777d;margin-bottom:4px";
  안내.textContent = "모델이 틀렸을 수도 있습니다 — 스캔 조각을 보고 정하세요. 원문 오식은 {{SIC}} 로 표시해 주세요.";
  판.appendChild(안내);
  var 몸 = document.createElement("div");
  몸.className = "전사대조-목록";
  판.appendChild(몸);
  공.띠아래(판);
  목록그리기();
}

// ── 단추를 눌렀을 때 ──────────────────────────────────────────────────
async function 시작() {
  var 쪽 = 지금쪽(), 상자 = 편집상자();
  if (!쪽 || !상자) return;
  if (!공.서버) { 공.알림("서버 주소가 없습니다 — Toolforge 도구가 내주는 주소(…/ocr.js)로 불러와 주세요.", "error"); return; }
  var 일 = 공.일("교정");
  if (!일) return;
  var 고른모델 = 공.모델(), 고른단 = 공.단();
  var t0 = performance.now();
  var 언제 = new Date(), 때 = {}, 결과 = [], 살핀 = null, 답 = null, t;
  var 재기 = function (이름, t) { 때[이름] = performance.now() - t; };
  try {
    var 본문 = 상자.value;
    결과.push(["편집 상자", 본문.length + "글자(UTF-16)"]);
    일.진행("전사문을 스캔과 맞대는 중…");
    t = performance.now();
    살핀 = await 공.서버살피기(쪽.파일, 일);
    재기("판형 살피기", t);
    일.진행("전사문을 스캔과 맞대는 중…");
    t = performance.now();
    살핀 = 공.단바꾸기(살핀, 고른단);
    답 = await 공.서버로("api/compare", { file: 쪽.파일, page: 쪽.쪽, text: 본문, model: 고른모델, tiers: 고른단 || "auto" }, 일);
    재기("대조(서버 왕복)", t);       // 후보 그림(data: 주소)까지 서버가 붙여 줌
    if (답.초 !== undefined) 때["└ 서버 셈"] = 답.초 * 1000;
    if (답.사유) throw new Error(답.사유);
    var 뒤쪽 = 지금쪽();
    if (!뒤쪽 || 뒤쪽.파일 !== 쪽.파일 || 뒤쪽.쪽 !== 쪽.쪽) throw 알릴오류("맞대는 사이에 쪽이 바뀌었습니다 — 다시 눌러 주세요.");
    if (상자.value !== 본문) throw 알릴오류("맞대는 사이에 편집 상자가 바뀌었습니다 — 다시 눌러 주세요.");
    답.초 = ((performance.now() - t0) / 1000).toFixed(1);
    공.결과놓기(결과걷기);
    후보들 = 답.후보.map(function (c) {
      c.원문 = 본문.slice(c.시작, c.끝);
      if (c.갈래 === "누락") {           // 넣기 전에 앞뒤가 그대로인지 볼 원문 몇 자
        c.앞원문 = 본문.slice(Math.max(0, c.시작 - 6), c.시작);
        c.뒤원문 = 본문.slice(c.시작, c.시작 + 6);
      }
      return c;
    });
    기준글 = 본문;
    고른것 = null;
    var 칠함 = 보이나(상자);
    띠세우기(답, 칠함);                  // 띠 · 목록을 먼저 놓아야 칠이 상자 자리에 맞음
    if (후보들.length) 판세우기();
    깔기(상자);
    결과.push(["볼 곳", 후보들.filter(확실).length + "곳" + (칠함 ? "" : " · 구문 강조라 칠 못함")]);
  } catch (e) {
    결과걷기();                         // 결과 구성 도중 실패한 경우도 남기지 않음
    공.띠걷기();
    var 메시지 = e && e.message ? e.message : e;
    if (e && e.취소) {
      공.알림("전사대조를 취소했습니다.");
      결과.push(["오류", "취소"]);
    } else {
      if (!(e && e.알림만)) console.error(e);
      공.알림(e && e.알림만 ? 메시지 : "전사대조가 멈췄습니다: " + 메시지, e && e.알림만 ? "warn" : "error");
      결과.push(["오류", String(메시지)]);
      if (e && e.stack && !e.알림만) 결과.push(["오류 자리", "\n  " + String(e.stack).split("\n").slice(0, 6).join("\n  ")]);
    }
  } finally {
    일.끝();
    try { 공.로그쓰기("교정", 공.로그머리("교정 (전사대조)", 쪽, 언제).concat(결과, 로그본문(살핀, 답, 때, t0))); }
    catch (e2) { console.error(e2); }
  }
}

function 알릴오류(글) { var e = new Error(글); e.알림만 = true; return e; }

전역.전사대조 = { 시작: 시작, 후보: function () { return 후보들; }, 되돌리기: 마지막되돌리기 };   // 시험용

공.세우기();
})(typeof self !== "undefined" ? self : this);
