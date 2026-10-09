/*
 * 옛한글 OCR — 사람이 친 영역 읽기
 *
 * 셈은 전부 `읽기.js` 의 것. 이 파일은 사람이 친 상자를 그 함수들이 받는 모양으로 바꿔 넘김.
 *   · 글자   — 상자 하나를 그대로 모델에
 *   · 열     — 상자를 한 열로 보고, 칸수를 모델 확신도로 고름(`구간읽기` 와 같은 셈). 글자 수를 주면 그 수로
 *   · 영역   — 상자 안을 작은 쪽으로 보고 열 찾기부터(`쪽기하` → `쪽읽기`)
 * 좌표는 모두 1920px 스캔의 픽셀.
 */
(function (전역) {
"use strict";

const 읽 = 전역.옛한글읽기;
const 속 = 읽._속;

function 자름(x) { return Math.trunc(x); }

/** 상자 안 가로 잉크 분포에서 글자가 있는 x 범위. 없으면 null */
function 잉크가로범위(g, b) {
  const W = g.너비, v = g.값, INK = (읽.설정 && 읽.설정.잉크문턱) || 120;
  const [x0, y0, x1, y1] = b;
  const n = new Int32Array(x1 - x0);
  for (let y = y0; y < y1; y++) {
    const o = y * W;
    for (let x = x0; x < x1; x++) if (v[o + x] < INK) n[x - x0]++;
  }
  const 문 = Math.max(1, (y1 - y0) * 0.02);
  let a = -1, z = -1;
  for (let i = 0; i < n.length; i++) if (n[i] >= 문) { if (a < 0) a = i; z = i + 1; }
  return a < 0 ? null : [x0 + a, x0 + z];
}

// 상자 높이의 이 몫 넘게 잉크인 x 는 세로줄(계선 · 광곽)로 봄 — 글자 획은 이만큼 이어지지 않음
const 세로줄몫 = 0.7;

/** 상자 높이 안에서 세로줄(계선 · 광곽)인 x 들 */
function 세로줄들(g, b, x0, x1) {
  const W = g.너비, v = g.값, INK = (읽.설정 && 읽.설정.잉크문턱) || 120;
  const out = [];
  for (let x = Math.max(0, x0); x < Math.min(W, x1); x++) {
    let s = 0;
    for (let y = b[1]; y < b[3]; y++) if (v[y * W + x] < INK) s++;
    if (s > (b[3] - b[1]) * 세로줄몫) out.push(x);
  }
  return out;
}

/**
 * 상자 안 [x0, x1) 의 줄마다 잉크 수 — 세로로 L 넘게 이어진 잉크(계선 · 광곽 세로줄)는 뺌.
 * 글자 획은 한 글자 높이를 못 넘으므로 L = 1.5 자간이면 줄만 걸림.
 * ⚠ 흐리고 끊긴 계선은 '덮개' 로는 못 거름 — 이음 길이로 거름
 */
function 줄잉크(g, b, x0, x1, L) {
  const W = g.너비, v = g.값, INK = (읽.설정 && 읽.설정.잉크문턱) || 120;
  const p = new Float64Array(g.높이);
  for (let x = Math.max(0, x0); x < Math.min(W, x1); x++) {
    let 시작 = -1;
    for (let y = b[1]; y <= b[3]; y++) {
      const 잉 = y < b[3] && v[y * W + x] < INK;
      if (잉) { if (시작 < 0) 시작 = y; continue; }
      if (시작 >= 0) {
        if (y - 시작 <= L) for (let k = 시작; k < y; k++) p[k]++;
        시작 = -1;
      }
    }
  }
  return p;
}

/** 쪽 열들 중 가운데가 상자 안에 있고 상자와 가장 많이 겹치는 열의 가운데 x(없으면 null) */
function 쪽열고르기(열들, b) {
  if (!열들) return null;
  let best = null, bv = 0;
  열들.forEach(function (c) {
    const m = (c[0] + c[1]) / 2;
    if (m < b[0] || m >= b[2]) return;
    const v = Math.min(c[1], b[2]) - Math.max(c[0], b[0]);
    if (v > bv) { bv = v; best = m; }
  });
  return best;
}

/** 상자 안에서 폭 창 짜리 띠에 잉크가 가장 많은 자리의 가운데 x. 창이 없거나 상자보다 넓으면 null */
function 열가운데(g, b, 창, 줄봄) {
  const [x0, y0, x1, y1] = b;
  if (!창 || 창 >= x1 - x0) return null;
  const W = g.너비, v = g.값, INK = (읽.설정 && 읽.설정.잉크문턱) || 120;
  const n = new Float64Array(x1 - x0 + 1);          // 누적합
  for (let x = x0; x < x1; x++) {
    let s = 0;
    for (let y = y0; y < y1; y++) if (v[y * W + x] < INK) s++;
    if (줄봄 && s > (y1 - y0) * 세로줄몫) s = 0;          // 계선 · 광곽 세로줄은 열이 아님
    n[x - x0 + 1] = n[x - x0] + s;
  }
  const w = Math.round(창);
  let best = -1, bx = null;
  for (let a = 0; a + w <= x1 - x0; a++) {
    const s = n[a + w] - n[a];
    if (s > best) { best = s; bx = x0 + a + w / 2; }
  }
  return best > 0 ? bx : null;
}

function 상자다듬기(g, b) {
  let [x0, y0, x1, y1] = b.map(Math.round);
  x0 = Math.max(0, Math.min(x0, g.너비 - 1)); x1 = Math.max(x0 + 1, Math.min(x1, g.너비));
  y0 = Math.max(0, Math.min(y0, g.높이 - 1)); y1 = Math.max(y0 + 1, Math.min(y1, g.높이));
  return [x0, y0, x1, y1];
}

function 부호빼기(글자, 확신, 상자) {
  const 뺄 = (읽.설정 && 읽.설정.부호빼기) || [];
  const g = [], h = [], s = [];
  for (let i = 0; i < 글자.length; i++) {
    if (뺄.indexOf(글자[i]) >= 0) continue;
    g.push(글자[i]); h.push(확신[i]); s.push(상자[i]);
  }
  return { 글자: g, 확신: h, 상자: s };
}

/** 글자 하나 */
async function 글자읽기(모델, g, b) {
  b = 상자다듬기(g, b);
  const r = await 모델.읽기(g, [b]);
  return { 글자: [모델.글자(r.초[0], r.중[0], r.종[0])], 확신: [r.확신[0]], 상자: [b] };
}

/**
 * 열 하나. 옵션: {자간비, 열간격(px, 쪽에서 잰 것 — 없으면 상자로 어림), 글자수(주면 그 수로), 폭(칸수 ±)}
 * 반환: {글자, 확신, 상자, 칸수, 후보: [{칸수, 점수}]}
 */
async function 열읽기(모델, g, b, 옵션) {
  옵션 = 옵션 || {};
  b = 상자다듬기(g, b);
  const 범 = 잉크가로범위(g, b);
  if (!범) return { 글자: [], 확신: [], 상자: [], 칸수: 0, 후보: [], 까닭: "상자 안에 잉크가 없습니다" };
  // 열 간격: 쪽에서 잰 값이 있으면 그것, 없으면 글자 폭 ÷ 0.75 로 어림
  const xp = 옵션.열간격 || (범[1] - 범[0]) / 0.75;
  // 세로줄(계선 · 광곽)을 볼지 — 상자가 글자 셋 높이보다 짧으면 안 봄(글자 하나의 ㅣ 획도 상자 높이를 거의 채움)
  const ratio = 옵션.자간비 || 읽.설정.기본자간비;
  const 줄봄 = b[3] - b[1] >= xp * ratio * 3;
  // 열 가운데: 쪽에서 찾은 열 가운데가 상자 안에 있으면 그것, 없으면 폭 0.6 열간격 창에 잉크가 가장 많은 자리
  const 쪽열 = 쪽열고르기(옵션.열들, b);
  const 가운데 = 쪽열 !== null ? 쪽열
    : (열가운데(g, b, 옵션.열간격 ? xp * 0.6 : null, 줄봄) || (범[0] + 범[1]) / 2);
  // 오리는 폭은 쪽 읽기와 같게 열 간격의 0.9 — 다만 사람이 친 상자 밖은 안 봄
  let cx0 = Math.max(b[0], 자름(가운데 - xp * 0.45));
  let cx1 = Math.min(b[2], 자름(가운데 + xp * 0.45));
  // 광곽 세로줄이 오릴 폭 안에 들면 그 줄 앞에서 자름 — 모델이 줄을 획으로 읽지 않게(끝 열을 느슨하게 쳤을 때)
  (줄봄 ? 세로줄들(g, b, cx0, cx1) : []).forEach(function (x) {
    if (x < 가운데) cx0 = Math.max(cx0, x + 2); else cx1 = Math.min(cx1, x - 1);
  });
  const pitch = xp * ratio;

  // 잉크 무늬 — 상자 위아래 밖은 0
  const prof = 줄잉크(g, b, cx0, cx1, xp * ratio * 1.5);
  // 열 폭의 90% 넘게 찬 줄은 광곽 가로줄 — 상자를 느슨하게 쳐 광곽이 들어와도 칸으로 세지 않게(`광곽한열` 과 같은 몫)
  for (let y = b[1]; y < b[3]; y++) if (prof[y] >= (cx1 - cx0) * 0.9) prof[y] = 0;
  const sm = 속.고르기(prof, Math.max(2.0, pitch / 9));
  // 글자가 있는 높이만 — 1.5 자간 넘게 빈 곳에서 토막을 나눠 따로 읽음. 글자 수를 주었으면 한 토막으로
  //   토막은 굵은 문턱(열 폭 10%)으로 찾고(끊긴 계선의 잉크 점을 피함), 끝만 가는 문턱(3%)으로 0.5 자간까지 늘림(`scan._이어잡기`)
  const 문 = Math.max(3, (cx1 - cx0) * 0.10), 가는문 = Math.max(1, (cx1 - cx0) * 0.03);
  let 토막 = [];
  for (let y = b[1]; y < b[3]; y++) {
    if (prof[y] < 문) continue;
    const t = 토막[토막.length - 1];
    if (t && y - t[1] <= pitch * 1.5) t[1] = y + 1; else 토막.push([y, y + 1]);
  }
  토막.forEach(function (t) {
    let a = t[0];
    for (let y = t[0] - 1; y >= Math.max(b[1], t[0] - pitch * 0.5); y--) if (prof[y] >= 가는문) a = y;
    let z = t[1];
    for (let y = t[1]; y < Math.min(b[3], t[1] + pitch * 0.5); y++) if (prof[y] >= 가는문) z = y + 1;
    t[0] = a; t[1] = z;
  });
  토막 = 토막.filter(function (t) { return t[1] - t[0] >= pitch * 0.3; });
  if (!토막.length) return { 글자: [], 확신: [], 상자: [], 칸수: 0, 후보: [], 까닭: "상자 안에 잉크가 없습니다" };
  if (옵션.글자수) 토막 = [[토막[0][0], 토막[토막.length - 1][1]]];
  const ya = 토막[0][0], yb = 토막[토막.length - 1][1];

  // 자를 자리 그림자 — 경계 검출기를 쪽 읽기와 같은 몫으로 섞음(`경계프로파일`)
  let smi = sm;
  if (모델.경계 && 읽.설정.경계) {
    const p = await 모델.경계(g, cx0, cx1);
    let 크기 = 1.0;
    for (let y = ya; y < yb; y++) if (sm[y] > 크기) 크기 = sm[y];
    const 섞기 = 읽.설정.경계섞기, 둥 = 읽.설정.경계반올림 || 10000;
    smi = new Float64Array(sm.length);
    for (let y = 0; y < sm.length; y++) {
      const q = 속.반올림(p[y] * 둥) / 둥;
      smi[y] = (1 - 섞기) * sm[y] + 섞기 * (1 - q) * 크기;
    }
  }

  const 폭 = 옵션.폭 === undefined ? 3 : 옵션.폭;
  const 글 = [], 확 = [], 상 = [], 후보 = [];
  let 칸수 = 0;
  for (const t of 토막) {
    const r = await 토막읽기(모델, g, smi, cx0, cx1, t[0], t[1], pitch, 옵션.글자수 ? [옵션.글자수] : null, 폭);
    // 빈 곳 너머 따로 떨어진 한두 칸이 모두 확신 0.5 미만이면 얼룩 · 끊긴 줄로 보고 버림(`align.NOTCHAR_CONF` 와 같은 값)
    if (토막.length > 1 && r.글자.length <= 2 && r.확신.every(function (c) { return c < 0.5; })) continue;
    r.글자.forEach(function (c, j) { 글.push(c); 확.push(r.확신[j]); 상.push(r.상자[j]); });
    칸수 += r.칸수;
    후보.push(r.후보);
  }
  const 남 = 부호빼기(글, 확, 상);
  return { 글자: 남.글자, 확신: 남.확신, 상자: 남.상자, 칸수: 칸수, 후보: 후보 };
}

/** 열의 [ya, yb) 한 토막 — 칸수를 여러 개로 잘라 보고 모델 확신(로그 기하평균)이 가장 높은 것(`구간읽기` 와 같은 셈) */
async function 토막읽기(모델, g, smi, cx0, cx1, ya, yb, pitch, 칸수들, 폭) {
  if (!칸수들) {
    const est = Math.max(1, 속.반올림((yb - ya) / pitch));
    칸수들 = [];
    for (let n = Math.max(1, est - 폭); n <= est + 폭; n++) 칸수들.push(n);
  }
  const cands = 속.자를후보(smi, ya, yb, pitch);
  const 계획 = [], 모든상자 = [];
  칸수들.forEach(function (n) {
    let cuts = 속.열가르기(smi, ya, yb, n, cands).자리;
    if (!cuts) {                       // 골짜기가 모자라면 고르게
      cuts = [];
      for (let k = 0; k <= n; k++) cuts.push(자름(ya + (yb - ya) * k / n));
    }
    const bx = [];
    for (let k = 0; k + 1 < cuts.length; k++) bx.push([cx0, cuts[k], cx1, cuts[k + 1]]);
    계획.push({ 칸수: n, 시작: 모든상자.length, 상자: bx });
    bx.forEach(function (x) { 모든상자.push(x); });
  });
  const r = await 모델.읽기(g, 모든상자);   // 같은 상자는 한 번만 읽음
  let best = null;
  const 후보 = [];
  계획.forEach(function (o) {
    let s = 0;
    for (let j = 0; j < o.상자.length; j++) s += Math.log(Math.max(r.확신[o.시작 + j], 1e-6));
    const 점수 = s / o.상자.length;
    후보.push({ 칸수: o.칸수, 점수: 점수 });
    if (best === null || 점수 > best.점수) best = { o: o, 점수: 점수 };
  });
  const o = best.o, 글 = [], 확 = [];
  for (let j = 0; j < o.상자.length; j++) {
    const i = o.시작 + j;
    글.push(모델.글자(r.초[i], r.중[i], r.종[i]));
    확.push(r.확신[i]);
  }
  return { 글자: 글, 확신: 확, 상자: o.상자, 칸수: o.칸수, 후보: 후보 };
}

/**
 * 영역 — 상자 안에서 열 자리만 찾고(`열찾기`), 열마다 `열읽기` 로. 오른쪽 열부터.
 * ⚠ 쪽 읽기(`쪽기하` → `쪽읽기`)를 작은 그림에 그대로 쓰면 안 됨 — 열이 몇 개뿐이면 한 열의 가로 획(ㅡ)도
 *   '여러 열이 합의한 광곽 줄' 로 잡혀 위아래가 잘림
 */
async function 영역읽기(모델, g, b, 옵션) {
  옵션 = 옵션 || {};
  b = 상자다듬기(g, b);
  const w = b[2] - b[0], h = b[3] - b[1];
  // 위아래 흰 여백 — `열찾기` 는 그림 높이의 12~88% 만 보므로 상자 전체가 그 안에 들게
  const 위 = 자름(h * 0.2) + 10, 옆 = 40;
  const W2 = w + 2 * 옆, H2 = h + 2 * 위;
  const v = new Uint8Array(W2 * H2).fill(255);
  for (let y = 0; y < h; y++) {
    const so = (b[1] + y) * g.너비 + b[0], to = (위 + y) * W2 + 옆;
    v.set(g.값.subarray(so, so + w), to);
  }
  // 쪽에서 찾은 열 가운데가 영역 안에 있으면 그 열들을, 없으면 영역 안에서 열을 새로 찾음
  let 열자리 = (옵션.열들 || []).map(function (c) { return (c[0] + c[1]) / 2; })
    .filter(function (m) { return m >= b[0] && m < b[2]; });
  let xp = 옵션.열간격 || null;
  if (!열자리.length) {
    const 찾 = 읽.열찾기({ 너비: W2, 높이: H2, 값: v }, false, null);
    if (!찾.열.length) return { 열들: [], 까닭: "영역 안에서 열을 못 찾았습니다 — 열 상자로 하나씩 쳐 보세요" };
    xp = xp || 찾.자간 || null;
    열자리 = 찾.열.map(function (c) { return (c[0] + c[1]) / 2 - 옆 + b[0]; });
  }
  열자리.sort(function (p, q) { return q - p; });
  const 열들 = [];
  for (const cx of 열자리) {
    const 반 = xp ? xp * 0.5 : w / (2 * 열자리.length);
    const 상 = [Math.max(b[0], 자름(cx - 반)), b[1], Math.min(b[2], 자름(cx + 반)), b[3]];
    const r = await 열읽기(모델, g, 상, { 자간비: 옵션.자간비, 열간격: xp, 열들: 옵션.열들 });
    if (r.글자.length) { r.원상자 = 상; 열들.push(r); }
  }
  return { 열들: 열들 };
}

/** 쪽 전체 자동 읽기(브라우저판 소도구와 같은 경로) — 열마다 {글자, 확신, 상자} */
async function 쪽전체(모델, g, 자간비) {
  const geo = 읽.쪽기하(g, 자간비 || 읽.설정.기본자간비, 1, true, null);
  if (!geo) return [];
  const r = await 읽.쪽읽기(모델, geo, 3);
  return r.줄들.map(function (z) { return { 글자: z.글자, 확신: z.확신, 상자: z.상자 }; });
}

/** 쪽 하나에서 자간비 · 열 간격을 잼(못 재면 null) */
function 쪽재기(g) {
  let 자간비 = null, 열간격 = null;
  try { 자간비 = 읽.쪽자간비(g, 1); } catch (e) { /* 못 잼 */ }
  let 열들 = null;
  // 판심 걸러내기는 끔 — 밀린 끝 열을 판심으로 떼는 일이 있음. 사람이 고른 상자만 읽으니 판심이 섞여도 됨
  try { const 찾 = 읽.열찾기(g, false, null); 열간격 = 찾.자간 || null; 열들 = 찾.열.length ? 찾.열 : null; } catch (e) { /* 못 잼 */ }
  return { 자간비: 자간비, 열간격: 열간격, 열들: 열들 };
}

전역.영역읽기 = { 글자읽기: 글자읽기, 열읽기: 열읽기, 영역읽기: 영역읽기, 쪽전체: 쪽전체, 쪽재기: 쪽재기 };
})(typeof self !== "undefined" ? self : this);
