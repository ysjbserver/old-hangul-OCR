/*
 * 옛한글 OCR — 인식: 편집 도구모음의 '옛한글 OCR' 단추
 *
 * 누르면 그 쪽을 Toolforge 서버에서 읽어 편집 상자에 넣고, 확신 낮은 글자를 상자 뒤에 칠함.
 * 셈은 서버, 이 파일은 화면만. 단추 · 띠 · 로그는 `공용.js`(`window.옛한글OCR`).
 */
(function () {
"use strict";
var 공 = window.옛한글OCR;
if (!공 || !공.들임("인식", "옛한글 OCR", "이 쪽 스캔을 옛한글 OCR 로 읽어 편집 상자에 넣습니다", 읽기시작, { 아이콘: true })) return;

var 편집상자 = 공.편집상자, 지금쪽 = 공.지금쪽, 보이나 = 공.보이나, 편집글 = 공.편집글;

function 살핀글(살핀) {
  return (공.단() ? "단은 직접 골라 " : "쪽을 살펴 ") + 공.판형글(살핀.단)
       + (살핀.자간비 ? " · 자간비 " + 살핀.자간비.toFixed(3) : " · 자간은 기본값")
       + (살핀.읽기자간비 ? "(읽기 " + 살핀.읽기자간비.toFixed(3) + ")" : "");
}

// ── 단추를 눌렀을 때 ─────────────────────────────────────────────────
async function 읽기시작() {
  var 상자 = 편집상자();
  var 쪽 = 지금쪽();
  if (!상자 || !쪽) { 공.알림("편집 창을 못 찾았습니다.", "error"); return; }
  if (!공.서버) { 공.알림("서버 주소가 없습니다 — Toolforge 도구가 내주는 주소(…/ocr.js)로 불러와 주세요.", "error"); return; }
  var 일 = 공.일("인식");
  if (!일) return;
  var 시작글 = 상자.value;
  var 고른모델 = 공.모델(), 고른단 = 공.단();
  var 언제 = new Date(), 처음 = performance.now(), 때 = {}, 결과 = [], 살핀, r;
  var 재기 = function (이름, t) { 때[이름] = performance.now() - t; };
  try {
    var 시작편집글 = 편집글(상자);
    var t;
    일.진행("옛한글 OCR 로 읽는 중…");
    t = performance.now();
    살핀 = await 공.서버살피기(쪽.파일, 일);
    재기("판형 살피기", t);
    일.진행("옛한글 OCR 로 읽는 중…");
    var t1 = performance.now();
    r = await 공.서버로("api/read", { file: 쪽.파일, page: 쪽.쪽, model: 고른모델, tiers: 고른단 || "auto", spacing: 공.띄움() }, 일);
    살핀 = r.살핀 || 공.단바꾸기(살핀, 고른단);
    재기("인식(서버 왕복)", t1);
    if (r.초 !== undefined) 때["└ 서버 셈"] = r.초 * 1000;
    결과.push(["판정", r.판정.등급 + (r.판정.까닭.length ? " — " + r.판정.까닭.join(" · ") : "")]);
    결과.push(["판형", 살핀글(살핀) + (고른모델 === "hanmun" ? " · 국한문 모델" : "")]);
    결과.push(["확신 낮은 글자", (r.표시비 * 100).toFixed(0) + "%"]);

    // 순서대로 편집에서 읽는 사이 쪽을 옮겼으면 넣지 않음 — 다른 쪽 글을 덮게 됨
    var 뒤쪽 = 지금쪽();
    if (!뒤쪽 || 뒤쪽.파일 !== 쪽.파일 || 뒤쪽.쪽 !== 쪽.쪽) {
      공.알림("읽는 사이에 쪽이 바뀌어(" + 쪽.쪽 + "쪽 → " + (뒤쪽 ? 뒤쪽.쪽 + "쪽" : "?")
           + ") 넣지 않았습니다. 다시 눌러 주세요.", "warn");
      결과.push(["넣음", "아니오 — 읽는 사이에 쪽이 바뀜"]);
      return;
    }
    // 기다리는 사이의 입력 · 초안 복원 · 편집기 교체도 덮지 않음
    if (편집상자() !== 상자 || 상자.value !== 시작글 || 편집글(상자) !== 시작편집글) {
      공.알림("읽는 사이에 편집 내용이 바뀌어 OCR 결과를 넣지 않았습니다. 현재 글을 유지했습니다. 다시 눌러 주세요.", "warn");
      결과.push(["넣음", "아니오 — 읽는 사이에 편집 내용이 바뀜"]);
      return;
    }
    if (!r.글월) {
      공.알림(쪽.쪽 + "쪽 판정: " + r.판정.등급 + " — " + (r.판정.까닭.join(" · ") || "열을 못 찾았습니다")
           + ". 넣지 않았습니다.", "warn");
      결과.push(["넣음", "아니오 — 읽은 글이 없음"]);
      return;
    }
    var 판 = { 상자: 상자, 옛글: 시작글, r: r, 쪽: 쪽 };
    공.결과놓기(결과걷기);
    if (r.판정.등급 === "못씀") {
      // 넣지 않고 띠 아래에 보여 줌 — 넣을지는 사람이
      공.알림(쪽.쪽 + "쪽은 '못씀' 이라 편집 상자에 넣지 않았습니다.", "warn");
      결과띠(판, false);
      보이기(판, true);
      결과.push(["넣음", "아니오 — 못씀"]);
    } else {
      // 편집 상자에는 표시 없는 글월(`⟪⟫` 가 저장되면 안 됨). 표시는 상자 뒤에 칠함
      넣기(상자, r.글월);
      판.넣음 = r.글월;
      결과띠(판, false);                 // 띠를 먼저 놓아야 칠이 상자 자리에 맞음
      var 칠함 = 표시깔기(상자, r.교정용);
      결과띠(판, 칠함);
      if (!칠함) 보이기(판, false);
      결과.push(["넣음", "예" + (칠함 ? " · 칠함" : " · 칠 못함(띠 아래 칸)")]);
    }
  } catch (e) {
    if (e && e.취소) {
      공.알림("읽기를 취소했습니다.");
      결과.push(["넣음", "아니오 — 취소"]);
    } else {
      공.알림("옛한글 OCR 이 멈췄습니다: " + ((e && e.message) || e), "error");
      console.error(e);
      결과.push(["오류", (e && e.message) || String(e)]);
      if (e && e.stack) 결과.push(["오류 자리", "\n  " + String(e.stack).split("\n").slice(0, 6).join("\n  ")]);
    }
  } finally {
    일.끝();
    try { 공.로그쓰기("인식", 공.로그머리("인식 (옛한글 OCR)", 쪽, 언제).concat(결과, 로그본문(살핀, r, 때, 처음))); }
    catch (e2) { console.error(e2); }
  }
}

/** 판형 · 읽은 결과 · 걸린 시간 */
function 로그본문(살핀, r, 때, 처음) {
  var 줄 = [];
  if (살핀) 줄.push(["판형 살핀 값", 공.판형글(살핀.단) + (살핀.자간비 ? " · 자간비 " + 살핀.자간비.toFixed(3) : " · 자간비 없음(기본값)")
                       + (살핀.읽기자간비 ? " · 읽기 자간비 " + 살핀.읽기자간비.toFixed(3) : "")
                       + (살핀.판짜임 ? " · 판짜임 " + JSON.stringify(살핀.판짜임) : "")]);
  if (r) {
    if (살핀 && 살핀.빈단) 줄.push(["선 없는 단", "경계 " + 살핀.빈단.join("~") + "px · 단별 자간비 "
        + 살핀.단별자간비.map(function (v) { return v.toFixed(3); }).join(" · ")]);
    줄.push(["읽은 것", r.상자수 + "자 · 표시 " + (r.표시비 * 100).toFixed(1) + "%"
             + (r.글월 ? " · 줄 " + r.글월.split("\n").length : "")]);
    if (r.글월) 줄.push(["줄마다 글자 수", r.글월.split("\n").map(function (l) { return l.replace(/\s/g, "").length; }).join(" ")]);
    var g = r.기하;
    if (g && g.cols) 줄.push(["기하", "열 " + g.cols.length + "개(가장자리 후보 포함) · 열 간격 " + (+g.xpitch).toFixed(1)
                             + "px · 글자 높이 " + (+g.pitch).toFixed(1) + "px" + (g.맞춤 ? " · 상자 맞춤" : "")]);
  }
  var 시간 = Object.keys(때).map(function (k) { return k + " " + 공.초글(때[k]); });
  시간.push("전체 " + 공.초글(performance.now() - 처음));
  줄.push(["걸린 시간", 시간.join(" · ")]);
  return 줄;
}

function 넣기(상자, 글) {
  상자.value = 글;
  // CodeMirror·2017 편집기가 바뀐 것을 알아채게
  상자.dispatchEvent(new Event("input", { bubbles: true }));
  상자.dispatchEvent(new Event("change", { bubbles: true }));
}

// ── 결과 띠 — [↶ 변환 되돌리기] … [×] · 아래 줄에 노란 칠 안내 ──
function 결과띠(판, 칠함) {
  var 둘째 = [];
  if (판.r.판정.등급 === "못씀" && !판.넣음) {
    둘째.push("이 쪽은 잘 읽히지 않아 넣지 않았습니다. 읽은 글은 아래 칸에 있습니다 — 처음부터 치는 편이 대개 빠릅니다.");
  } else if (칠함) {
    둘째.push(안내줄(깔개 && 깔개.자리.length
      ? "노란 칠은 확신이 낮은 글자입니다. 고치면 칠이 사라지고, 칠은 저장되지 않습니다."
      : "확신 낮은 글자가 없습니다."));
  } else if (판.넣음) {
    둘째.push("구문 강조가 켜져 있어 편집 상자에 칠하지 못했습니다 — 확신 낮은 글자는 아래 칸에 표시했습니다(끄고 다시 읽으면 상자에 칠합니다).");
  }
  if (판.r.판정.등급 === "의심") {
    var 경 = 공.만들기("div", "경고", "⚠ 잘 안 읽혔을 수 있는 쪽입니다 — 틀린 글자가 평소보다 많을 수 있습니다.");
    둘째.push(경);
  }
  공.띠결과({
    되돌리기: 판.넣음 ? { 글: "변환 되돌리기", 할일: function () { 되돌리기(판); } } : null,
    둘째: 둘째,
    닫기: 공.결과걷기,
    닫기설명: "칠과 안내 닫기(편집 상자 글은 그대로)",
  });
}

function 안내줄(글) {
  var 줄 = 공.만들기("div");
  var 빛 = 공.만들기("span", "빛");
  빛.style.background = "rgba(255,190,0,.6)";
  줄.appendChild(빛);
  줄.appendChild(document.createTextNode(글));
  return 줄;
}

/** OCR 전 글로 — 넣은 뒤 고친 것이 있으면 물어봄 */
function 되돌리기(판) {
  var 상자 = 편집상자();
  if (!상자 || 상자 !== 판.상자) { 공.알림("편집 상자가 바뀌어 되돌리지 못했습니다.", "warn"); return; }
  var 할일 = function () {
    넣기(상자, 판.옛글);
    공.결과걷기();
    공.알림("OCR 전 글로 되돌렸습니다.");
  };
  if (상자.value === 판.넣음) { 할일(); return; }
  공.확인("OCR 결과를 넣은 뒤에 고친 내용도 함께 사라집니다. 되돌릴까요?").then(function (예) { if (예) 할일(); });
}

function 결과걷기() {
  표시걷기();
  교정칸치우기();
}

// ── 편집 상자 안에 표시 깔기 ─────────────────────────────────────────
// 편집 상자 뒤에 같은 모양의 판을 깔고 확신 낮은 자리의 바탕만 칠함(저장되지 않음) · 고치면 칠도 따라 밀림
// ⚠ CodeMirror(구문 강조) 위에는 칠하지 않음 — 띠 아래 칸으로(`보이기`)
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

// 판이 편집 상자와 같은 자리에서 줄을 바꾸게 베낄 모양들
var 베낄모양 = ["paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
  "fontFamily", "fontSize", "fontWeight", "fontStyle", "fontVariant", "fontStretch",
  "fontKerning", "fontFeatureSettings", "lineHeight", "letterSpacing", "wordSpacing",
  "textIndent", "textTransform", "tabSize", "whiteSpace", "overflowWrap", "wordBreak",
  "direction", "textAlign"];

/** 편집 상자에 표시 깔기. 깔았으면 true (못 깔면 띠 아래 칸으로) */
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
  // ⚠ 도구 모음 · 구문 강조 전환은 input 없이 바뀌므로 0.5초마다 대 봄
  var 시계 = setInterval(function () {
    if (!상자.isConnected) { 표시걷기(); return; }
    따라가기(); 모양맞추기();
  }, 500);
  var 관찰 = window.ResizeObserver ? new ResizeObserver(모양맞추기) : null;
  if (관찰) 관찰.observe(상자);
  window.addEventListener("resize", 모양맞추기);

  깔개.맞추기 = 모양맞추기;
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

공.자리듣기(function () { if (깔개) 깔개.맞추기(); });   // 띠가 생기거나 걷히면 상자가 밀림

function 교정칸치우기() {
  var 칸 = document.getElementById("옛한글OCR-교정");
  if (칸) { 칸.remove(); 공.자리바뀜(); }
}

/** 편집 상자에 칠하지 못할 때('못씀' · 구문 강조) 띠 아래 칸에 보이기 */
function 보이기(판, 못씀) {
  교정칸치우기();
  var r = 판.r;
  var 칸 = document.createElement("div");
  칸.id = "옛한글OCR-교정";
  칸.style.cssText = "margin:0 0 8px;padding:10px 12px;border:1px solid var(--border-color-subtle,#c8ccd1);border-top:0;"
    + "background:var(--background-color-base,#fff);line-height:2;font-size:15px;"
    + "max-height:16em;overflow:auto;white-space:pre-wrap";   // 열마다 한 줄
  if (못씀) {                        // 그래도 넣을지는 사람이
    var 그래도 = document.createElement("button");
    그래도.type = "button";
    그래도.className = "cdx-button";
    그래도.style.cssText = "margin:0 0 8px;white-space:normal";
    그래도.textContent = "그래도 편집 상자에 넣기";
    그래도.addEventListener("click", function () {
      var 상자 = 편집상자();
      if (!상자) return;
      판.상자 = 상자;
      판.옛글 = 상자.value;
      넣기(상자, r.글월);
      판.넣음 = r.글월;
      var 칠함 = 표시깔기(상자, r.교정용);
      if (칠함) 교정칸치우기();
      else { 그래도.disabled = true; 그래도.textContent = "넣었습니다"; }
      결과띠(판, 칠함);
    });
    칸.appendChild(그래도);
    칸.appendChild(document.createElement("br"));
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
  공.띠아래(칸);
}

공.세우기();
})();
