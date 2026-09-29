/*
 * 옛한글 OCR — 브라우저판 읽기 셈 (파이썬을 옮긴 것)
 *
 * ⚠ 파이썬과 짝 — 규칙이 같아야 함:
 *   scan.py        열찾기 · 가장자리후보 · 광곽 · 글자구간 · 자를후보 · 열가르기 · 쪽기하 · 가름줄 판형
 *   page.py        쪽건강 · 테두리열버리기(안 씀) · 기하 · 판형정하기
 *   align.py       자를계획 · 열마다읽기 · 가장자리다듬기 · 쪽읽기
 *   ocr.py         오리기 · 글자
 *   step4_read.py  확신표시 · 줄글월
 * ⚠ 고쳤으면 `대조.html` 로 단계마다 맞춰 볼 것 (정답은 `대조뽑기.py`)
 */
(function (전역) {
"use strict";

// ════════════════════════════════════════════════════════════════════
//  파이썬의 셈을 그대로 옮긴 것들 — ⚠ "대충 같은 것" 으로 바꾸지 말 것
// ════════════════════════════════════════════════════════════════════

/**
 * 파이썬 `round()` — 은행가 반올림(0.5 는 짝수 쪽). `Math.round` 와 다름
 * ⚠ `est` 와 빠진 열 채우기에서 결과가 바뀜
 */
function 반올림(x) {
  const f = Math.floor(x), d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return (f % 2 === 0) ? f : f + 1;
}

/** numpy `np.median` — 짝수 개면 가운데 **둘의 평균**. */
function 중앙값(a) {
  if (!a.length) return NaN;
  const s = Float64Array.from(a).sort();
  const m = s.length >> 1;
  return (s.length % 2) ? s[m] : (s[m - 1] + s[m]) / 2;
}

/** numpy `np.percentile` 의 기본값(선형 보간). */
function 백분위(a, q) {
  if (!a.length) return NaN;
  const s = Float64Array.from(a).sort();
  const p = (s.length - 1) * q / 100;
  const lo = Math.floor(p), hi = Math.ceil(p);
  return lo === hi ? s[lo] : s[lo] * (hi - p) + s[hi] * (p - lo);
}

/** 파이썬 `int()` — 0 쪽으로 자름. 음수에서 `Math.floor` 와 다릅니다. */
const 자름 = Math.trunc;

// ════════════════════════════════════════════════════════════════════
//  회색조 그림 한 장 — {너비, 높이, 값}  값[y*너비 + x]
// ════════════════════════════════════════════════════════════════════

/**
 * RGBA → 회색조.
 * ⚠ `PIL.convert("L")` 과 같은 고정소수점 식 — `0.299R+…` 반올림은 1 씩 어긋남
 */
function 그림만들기(rgba, 너비, 높이) {
  const v = new Uint8Array(너비 * 높이);
  for (let i = 0, j = 0; i < v.length; i++, j += 4) {
    v[i] = (rgba[j] * 19595 + rgba[j + 1] * 38470 + rgba[j + 2] * 7471 + 32768) >> 16;
  }
  return { 너비: 너비, 높이: 높이, 값: v };
}

/** 이미지/캔버스 → 회색조 그림. */
function 그림읽기(src) {
  const w = src.naturalWidth || src.width;
  const h = src.naturalHeight || src.height;
  let cv;
  if (typeof OffscreenCanvas !== "undefined") cv = new OffscreenCanvas(w, h);
  else { cv = document.createElement("canvas"); cv.width = w; cv.height = h; }
  const cx = cv.getContext("2d", { willReadFrequently: true });
  cx.drawImage(src, 0, 0);
  return 그림만들기(cx.getImageData(0, 0, w, h).data, w, h);
}

// ════════════════════════════════════════════════════════════════════
//  scan.py
// ════════════════════════════════════════════════════════════════════

let INK = 120;          // 이보다 어두우면 잉크로 본다
let GLYPH = 0.35;       // 글자가 있는 줄은 열 폭의 이만큼 이상이 잉크다
let SPAN_EXTEND = true, SPAN_LOW = 0.15, SPAN_REACH = 1.5, SPAN_GAP = 0.4;   // scan._이어잡기
let FRAME_LOCAL = true, FRAME_LOCAL_FILL = 0.6, FRAME_LOCAL_REACH = 0.35, FRAME_LOCAL_EDGE = 8;   // scan._열광곽
let YX_RATIO = 0.867;   // 세로 자간 ÷ 가로 자간 (기본값)

let FRAME_SEG = 300, FRAME_FILL = 0.85, FRAME_AGREE = 0.6;   // scan.py 와 같은 값

/**
 * `scan.세로줄있나` — x 가 [xa, xb) 인 띠에 끊기지 않은 세로줄(광곽 선·제본 골)이
 * 있는가. [T, B) 를 토막으로 나눠, 토막마다 어느 x 한 줄이라도 잉크가 덮개 이상이면
 * 그 토막에 줄이 있다. 토막의 합의 이상에 있으면 참.
 */
function 세로줄있나(g, xa, xb, T, B) {
  const a = Math.trunc(Math.min(xa, xb)), b = Math.trunc(Math.max(xa, xb));
  if (b - a < 3) return false;
  const v = g.값, W = g.너비;
  let 칸 = 0, 맞 = 0;
  for (let y = T; y < B - Math.floor(FRAME_SEG / 2); y += FRAME_SEG) {
    const y1 = Math.min(B, y + FRAME_SEG), 줄수 = y1 - y;
    칸++;
    for (let x = a; x < b; x++) {
      let s = 0;
      for (let yy = y; yy < y1; yy++) if (v[yy * W + x] < INK) s++;
      if (s >= FRAME_FILL * 줄수) { 맞++; break; }
    }
  }
  return 칸 > 0 && 맞 >= 칸 * FRAME_AGREE;
}

/**
 * `scan.칸모양` — 상자 [x0,y0,x1,y1] 안 잉크의 [가로 폭 비율, 한 행이 폭을 채운
 * 최대 비율]. 잉크가 없으면 [0, 0].
 */
function 칸모양(g, b) {
  const v = g.값, W = g.너비;
  const x0 = Math.max(0, b[0]), x1 = Math.min(W, b[2]);
  const y0 = Math.max(0, b[1]), y1 = Math.min(g.높이, b[3]);
  const w = x1 - x0;
  if (w <= 0 || y1 <= y0) return [0.0, 0.0];
  let 왼 = -1, 오른 = -1, 행최대 = 0;
  for (let y = y0; y < y1; y++) {
    let s = 0; const o = y * W;
    for (let x = x0; x < x1; x++) {
      if (v[o + x] < INK) {
        s++;
        if (왼 < 0 || x - x0 < 왼) 왼 = x - x0;
        if (x - x0 > 오른) 오른 = x - x0;
      }
    }
    if (s > 행최대) 행최대 = s;
  }
  if (왼 < 0) return [0.0, 0.0];
  return [(오른 - 왼 + 1) / w, 행최대 / w];
}

let EDGE_MOVE = true, EDGE_MOVE_GAP = 0.45, EDGE_MOVE_MIN = 0.6, EDGE_MOVE_INK = 0.45;   // scan.py 와 같은 값

/** `scan.세로줄자리` — 줄이 있으면 [줄 왼끝, 줄 오른끝](토막마다의 중앙값), 없으면 null. */
function 세로줄자리(g, xa, xb, T, B) {
  const a = Math.trunc(Math.min(xa, xb)), b = Math.trunc(Math.max(xa, xb));
  if (b - a < 3) return null;
  const v = g.값, W = g.너비;
  let 칸 = 0; const 왼 = [], 오 = [];
  for (let y = T; y < B - Math.floor(FRAME_SEG / 2); y += FRAME_SEG) {
    const y1 = Math.min(B, y + FRAME_SEG), 줄수 = y1 - y;
    칸++;
    let 첫 = -1, 끝 = -1;
    for (let x = a; x < b; x++) {
      let s = 0;
      for (let yy = y; yy < y1; yy++) if (v[yy * W + x] < INK) s++;
      if (s >= FRAME_FILL * 줄수) { if (첫 < 0) 첫 = x; 끝 = x; }
    }
    if (첫 >= 0) { 왼.push(첫); 오.push(끝); }
  }
  if (칸 === 0 || 왼.length < 칸 * FRAME_AGREE) return null;
  return [중앙값(왼), 중앙값(오)];
}

/** `scan._줄에서비키기` — 쪽 끝 후보 열 상자 안으로 세로줄이 지나면 줄 안쪽으로 옮긴다. */
function 줄에서비키기(g, cols0, xpitch, T, B) {
  const cols = cols0.map(function (c) { return [c[0], c[1]]; });
  const n = cols.length;
  if (n < 6) return cols;
  const w = Math.trunc(중앙값(cols.map(function (c) { return c[1] - c[0]; })));
  const 가 = function (c) { return (c[0] + c[1]) / 2; };
  const W = g.너비, v = g.값;
  const 잉크 = function (a, b) {
    const x0 = Math.max(0, a), x1 = Math.min(W, Math.max(0, b));
    if (b <= a || x1 <= x0 || B <= T) return 0.0;
    let s = 0;
    for (let y = T; y < B; y++) { const o = y * W; for (let x = x0; x < x1; x++) if (v[o + x] < INK) s++; }
    return s / ((B - T) * (x1 - x0));
  };
  const 가운데들 = [];
  for (let i = 3; i < n - 3; i++) 가운데들.push(잉크(cols[i][0], cols[i][1]));
  const 기준잉크 = n > 6 ? 중앙값(가운데들) : 0.0;
  const m = Math.min(3, n >> 1), ks = [];
  for (let k = 0; k < m; k++) ks.push(k);
  for (let k = n - 1; k > n - 1 - m; k--) ks.push(k);
  ks.forEach(function (k) {
    const a = cols[k][0], b = cols[k][1];
    const 줄 = 세로줄자리(g, a, b, T, B);
    if (줄 === null) return;
    const 오른끝 = k < (n >> 1);
    const 안 = 오른끝 ? cols[k + 1] : cols[k - 1];
    let c;
    if (오른끝) {
      c = Math.max(줄[0] - xpitch * EDGE_MOVE_GAP, 가(안) + xpitch * EDGE_MOVE_MIN);
      if (c >= 가([a, b])) return;
    } else {
      c = Math.min(줄[1] + xpitch * EDGE_MOVE_GAP, 가(안) - xpitch * EDGE_MOVE_MIN);
      if (c <= 가([a, b])) return;
    }
    const 새 = [Math.trunc(c - w / 2), Math.trunc(c + w / 2)];
    if (잉크(새[0], 새[1]) < 기준잉크 * EDGE_MOVE_INK) return;
    cols[k] = 새;
  });
  return cols;
}

/** 열 [x0,x1) 에서 y 줄마다 잉크 픽셀 수. */
function 열잉크(g, x0, x1) {
  const p = new Float64Array(g.높이), v = g.값, W = g.너비;
  for (let y = 0; y < g.높이; y++) {
    let s = 0; const o = y * W;
    for (let x = x0; x < x1; x++) if (v[o + x] < INK) s++;
    p[y] = s;
  }
  return p;
}

/** `scan._columns_at` — 한 문턱으로 잉크 덩어리를 잡아 [덩어리들, 자간]. */
function 덩어리잡기(ink, W, th) {
  const runs = [];
  let s = null;
  for (let x = 0; x < W; x++) {
    if (ink[x] > th && s === null) s = x;
    else if (ink[x] <= th && s !== null) { if (x - s > 10) runs.push([s, x]); s = null; }
  }
  if (s !== null && W - s > 10) runs.push([s, W]);
  if (runs.length < 3) return null;

  const wmed = 중앙값(runs.map(function (r) { return r[1] - r[0]; }));
  const r2 = runs.filter(function (r) { return (r[1] - r[0]) > wmed * 0.55; });
  if (r2.length < 3) return null;

  const cen = r2.map(function (r) { return (r[0] + r[1]) / 2; });
  const d = [];
  for (let i = 1; i < cen.length; i++) {
    const gg = cen[i] - cen[i - 1];
    if (gg > 40) d.push(gg);
  }
  if (!d.length) return null;
  return [r2, 중앙값(d)];
}

/** `scan._drop_margin_column` — 양 끝에서 이웃과 유난히 먼 열(판심)을 뗀다. */
function 판심떼기(cols, ratio) {
  if (ratio === undefined) ratio = 1.18;
  for (let t = 0; t < 2; t++) {
    if (cols.length < 5) break;
    const cen = cols.map(function (c) { return (c[0] + c[1]) / 2; });
    const gaps = [];
    for (let i = 0; i + 1 < cen.length; i++) gaps.push(cen[i + 1] - cen[i]);
    const med = 중앙값(gaps);
    if (!(med > 0)) break;
    if (gaps[0] > med * ratio) cols = cols.slice(1);
    else if (gaps[gaps.length - 1] > med * ratio) cols = cols.slice(0, -1);
    else break;
  }
  return cols;
}

/**
 * `scan.find_columns` — 열 간격이 일정하다는 성질로 열 찾기. 반환 {자간, 열} (오른쪽 열부터)
 * ① 잉크로 대략 잡기 ② 쪽번호 걸러내기 ③ 쪼개진 열 합치기 ④ 빠진 열 끼우기 ⑤ 판심 떼기
 * 판심뗌=false 는 읽을 때(한 단)만 — `쪽기하` 가 `가장자리후보` 를 붙임
 * ⚠ 문턱을 두 번 시험하는 것이 핵심 (흐린 쪽에서는 첫 문턱이 너무 높음)
 */
let PITCH_OFF = 0.15, PITCH_ON = 0.10, PITCH_USE = true;   // scan.py · page.py 와 같은 값

function 열찾기(g, 판심뗌, 표준자간) {
  if (판심뗌 === undefined) 판심뗌 = true;
  const H = g.높이, W = g.너비, v = g.값;
  const y0 = 자름(H * 0.12), y1 = 자름(H * 0.88);
  const ink = new Float64Array(W);
  for (let y = y0; y < y1; y++) {
    const o = y * W;
    for (let x = 0; x < W; x++) if (v[o + x] < INK) ink[x]++;
  }
  let mx = 0;
  for (let x = 0; x < W; x++) if (ink[x] > mx) mx = ink[x];
  if (!(mx > 0)) return { 자간: null, 열: [] };

  let 골랐 = null;
  const 잡은 = [];
  const 문턱들 = [mx * 0.12, 백분위(ink, 90) * 0.25];
  for (let t = 0; t < 문턱들.length; t++) {
    const got = 덩어리잡기(ink, W, 문턱들[t]);
    잡은.push(got);
    if (got === null) continue;
    if (골랐 === null) 골랐 = got;          // 둘 다 통과 못 하면 첫 번째
    const wm = 중앙값(got[0].map(function (r) { return r[1] - r[0]; }));
    if (wm > got[1] * 0.18) { 골랐 = got; break; }
  }
  if (골랐 === null) return { 자간: null, 열: [] };
  // 읽을 때만 — 자간이 표준에서 PITCH_OFF 넘게 벗어나면 PITCH_ON 안인 다른 문턱으로
  if (표준자간 && Math.abs(골랐[1] - 표준자간) > 표준자간 * PITCH_OFF) {
    if (잡은.length < 2) 잡은.push(덩어리잡기(ink, W, 문턱들[1]));   // 첫 문턱에서 끝났으면 둘째도
    for (let t = 0; t < 잡은.length; t++) {
      const got = 잡은[t];
      if (got !== null && got !== 골랐 && Math.abs(got[1] - 표준자간) <= 표준자간 * PITCH_ON) {
        골랐 = got; break;
      }
    }
  }
  const runs = 골랐[0];
  let pitch = 골랐[1];

  const merged = [runs[0].slice()];                     // ③ 쪼개진 열 합치기
  for (let i = 1; i < runs.length; i++) {
    const r = runs[i], last = merged[merged.length - 1];
    if ((r[0] + r[1]) / 2 - (last[0] + last[1]) / 2 < pitch * 0.6) last[1] = r[1];
    else merged.push(r.slice());
  }
  const cen = merged.map(function (r) { return (r[0] + r[1]) / 2; });
  if (cen.length > 2) {
    const d = [];
    for (let i = 1; i < cen.length; i++) d.push(cen[i] - cen[i - 1]);
    pitch = 중앙값(d);
  }

  const wmed2 = 중앙값(merged.map(function (r) { return r[1] - r[0]; }));
  const boxes = [merged[0].slice()];                    // ④ 빠진 열 채우기
  for (let i = 1; i < merged.length; i++) {
    const r = merged[i], c = (r[0] + r[1]) / 2;
    const prev = boxes[boxes.length - 1], pc = (prev[0] + prev[1]) / 2;
    const k = Math.max(1, 반올림((c - pc) / pitch));
    for (let t = 1; t < k; t++) {
      const mid = pc + (c - pc) * t / k;
      boxes.push([자름(mid - wmed2 / 2), 자름(mid + wmed2 / 2)]);
    }
    boxes.push(r.slice());
  }
  let out = boxes.map(function (bb) {          // 지나치게 넓어진 열은 가운데만
    let a = bb[0], b = bb[1];
    if (b - a > pitch * 0.8) {
      const c = (a + b) / 2;
      a = 자름(c - wmed2 / 2); b = 자름(c + wmed2 / 2);
    }
    return [Math.max(0, a), Math.min(W, b)];
  });
  if (판심뗌) out = 판심떼기(out);                          // ⑤ 판심 걸러내기
  out.reverse();
  return { 자간: pitch, 열: out };
}

/**
 * `scan._가장자리후보` — 읽을 때 양 끝에 후보 열 붙이기. 버릴지는 `가장자리다듬기` 가 확신도로.
 * 한쪽에 둘 — 둘째 열에서 자간 하나 바깥(제자리), 가장자리 열에서 한 칸 더 바깥
 * ⚠ 붙이는 차례와 안정 정렬을 파이썬과 똑같이
 */
function 가장자리후보(cols, pitch, W) {
  const w = 자름(중앙값(cols.map(function (c) { return c[1] - c[0]; })));
  const 가 = function (c) { return (c[0] + c[1]) / 2; };
  const 상자 = function (x) {
    const a = 자름(x - w / 2), b = 자름(x + w / 2);
    // ⚠ 이미 있는 열과 똑같은 후보는 안 붙임 — 점수가 거의 같아 남길 쪽이 파이썬과 뒤집힘
    const 있던 = cols.some(function (c) { return c[0] === a && c[1] === b; });
    return (a >= 0 && b <= W && !있던) ? [a, b] : null;
  };
  const 오른 = [상자(가(cols[0]) + pitch)];
  const 왼 = [상자(가(cols[cols.length - 1]) - pitch)];
  if (cols.length > 2) {
    오른.push(상자(가(cols[1]) + pitch));                // 제자리
    왼.unshift(상자(가(cols[cols.length - 2]) - pitch));
  }
  const 있음 = function (x) { return x !== null; };
  const out = 오른.filter(있음).concat(cols, 왼.filter(있음));
  out.sort(function (p, q) { return (q[0] + q[1]) - (p[0] + p[1]); });
  return out;
}

/** `scan._frame` — 이 열에서 광곽 가로줄의 위·아래. **자르기 경로**용. */
function 광곽한열(g, x0, x1) {
  const H = g.높이, p = 열잉크(g, x0, x1), need = (x1 - x0) * 0.90;
  let top = -1, bot = -1;
  for (let y = 0; y < H; y++) {
    if (p[y] < need) continue;
    if (y < H * 0.25 && top < 0) top = y;
    if (y > H * 0.75) bot = y;
  }
  return (top < 0 || bot < 0) ? null : [top + 6, bot - 6];
}

/**
 * `scan._frame_read` — 광곽 안쪽 위·아래를 열들의 합의로 찾기 (여러 열을 가로지르는 것은 광곽뿐)
 * ⚠ 읽을 때만 — 자를 때 쓰면 학습이 망가짐
 */
function 광곽합의(g, cols, fill, agree) {
  if (fill === undefined) fill = 0.90;
  if (agree === undefined) agree = 0.30;
  const H = g.높이, 표 = new Float64Array(H);
  for (let i = 0; i < cols.length; i++) {
    const x0 = cols[i][0], x1 = cols[i][1];
    const p = 열잉크(g, x0, x1), need = (x1 - x0) * fill;
    for (let y = 0; y < H; y++) if (p[y] >= need) 표[y]++;
  }
  const 줄 = [];
  for (let y = 0; y < H; y++) {
    if (표[y] / cols.length < agree) continue;
    const last = 줄[줄.length - 1];
    if (last && y - last[1] <= 3) last[1] = y; else 줄.push([y, y]);
  }
  const 쓸 = 줄.filter(function (r) {          // 스캔 가장자리의 검은 띠 제외
    return r[0] > H * 0.01 && r[1] < H * 0.99;
  });
  const 위 = 쓸.filter(function (r) { return r[1] < H * 0.30; });
  const 아래 = 쓸.filter(function (r) { return r[0] > H * 0.70; });
  if (!위.length || !아래.length) return null;
  const T = 위[위.length - 1][1] + 4;          // 가장 안쪽 줄의 안쪽
  const B = 아래[0][0] - 4;
  return (B - T > H * 0.4) ? [T, B] : null;
}

/**
 * `scan.page_frame` — 광곽 안쪽 위·아래. ⚠ 읽기와 자르기가 일부러 다름
 *   읽기 → `광곽합의`(안쪽까지 바짝), 자르기 → 옛 방식(넉넉하게)
 */
function 광곽(g, cols, 읽기) {
  if (읽기) {
    const got = 광곽합의(g, cols);
    if (got) return got;
  }
  const H = g.높이;
  const got = [];
  for (let i = 0; i < cols.length; i++) {
    const f = 광곽한열(g, cols[i][0], cols[i][1]);
    if (f) got.push(f);
  }
  let T, B;
  if (got.length < Math.max(2, Math.floor(cols.length / 3))) {
    T = 자름(H * 0.06); B = 자름(H * 0.95);
  } else {
    T = 자름(중앙값(got.map(function (f) { return f[0]; })));
    B = 자름(중앙값(got.map(function (f) { return f[1]; })));
  }
  if (B - T < H * 0.4) { T = 자름(H * 0.06); B = 자름(H * 0.95); }
  return [T, B];
}

/**
 * `scan._열광곽` — 열마다 광곽 안쪽 위·아래(쪽 값보다 안쪽으로만). 읽을 때 · `광곽합의` 가 찾았을 때만.
 * 열 + 쪽 가운데 쪽 고랑 띠가 찬 줄 = 광곽(글자 획은 고랑을 안 건넘). 못 찾은 열은 x 로 양옆을 곧게 이음
 */
function 열광곽(g, cols, T, B, xpitch, pitch) {
  const W = g.너비, H = g.높이;
  const R = Math.max(6, Math.trunc(FRAME_LOCAL_REACH * pitch));
  let 합 = 0;
  for (let i = 0; i < cols.length; i++) 합 += (cols[i][0] + cols[i][1]) / 2;
  const 쪽가운데 = 합 / cols.length;
  const 위 = [], 아래 = [], xs = [];
  for (let i = 0; i < cols.length; i++) {
    const x0 = cols[i][0], x1 = cols[i][1];
    const 고랑 = Math.max(0, Math.trunc(xpitch - (x1 - x0)));
    let a, b;
    if ((x0 + x1) / 2 < 쪽가운데) { a = x0; b = Math.min(W, x1 + 고랑); }
    else { a = Math.max(0, x0 - 고랑); b = x1; }
    const 띠 = 열잉크(g, a, b), 열 = 열잉크(g, x0, x1);
    const 찬 = function (y) { return 띠[y] >= (b - a) * FRAME_LOCAL_FILL; };
    const 획 = function (y) { return 열[y] > (x1 - x0) * GLYPH; };
    let y0 = Math.max(0, T - 4 - R), y = -1;
    for (let k = y0; k < Math.min(H, T - 4 + R); k++) if (찬(k)) y = k;       // 가장 안쪽(아래) 찬 줄
    if (y >= 0) {
      let e = y;
      while (e + 1 < H && e + 1 - y <= FRAME_LOCAL_EDGE && 획(e + 1)) e++;
      위.push(Math.max(y + 4, e + 2));
    } else 위.push(null);
    y0 = Math.max(0, B + 4 - R); y = -1;
    for (let k = y0; k < Math.min(H, B + 4 + R); k++) if (찬(k)) { y = k; break; }   // 가장 안쪽(위) 찬 줄
    if (y >= 0) {
      let e = y;
      while (e - 1 >= 0 && y - (e - 1) <= FRAME_LOCAL_EDGE && 획(e - 1)) e--;
      아래.push(Math.min(y - 4, e - 2));
    } else 아래.push(null);
    xs.push((x0 + x1) / 2);
  }
  function 잇기(v, 쪽값, 안쪽) {
    const 있 = [];
    for (let i = 0; i < v.length; i++) if (v[i] !== null) 있.push(i);
    if (!있.length) return v.map(function () { return 쪽값; });
    return v.map(function (t, i) {
      if (t === null) {
        let l = null, r = null;               // 파이썬 max/min(key) 처럼 같은 x 면 먼저 나온 것
        for (let k = 0; k < 있.length; k++) {
          const j = 있[k];
          if (xs[j] <= xs[i] && (l === null || xs[j] > xs[l])) l = j;
          if (xs[j] >= xs[i] && (r === null || xs[j] < xs[r])) r = j;
        }
        if (l === null || r === null || xs[r] === xs[l]) t = v[r === null ? l : r];
        else t = Math.floor(v[l] + (v[r] - v[l]) * (xs[i] - xs[l]) / (xs[r] - xs[l]));
      }
      return 안쪽(쪽값, t);
    });
  }
  return [잇기(위, T, Math.max), 잇기(아래, B, Math.min)];
}

/** `scan.ink_profile` — 뒤 계산이 모두 이것을 돌려쓴다. */
function 잉크무늬(g, cols) {
  return cols.map(function (c) { return 열잉크(g, c[0], c[1]); });
}

/**
 * `scan._이어잡기` — 구간 끝의 가는 글자(GLYPH 를 못 넘는 `이` 등)를 이어 붙임. 읽을 때만.
 * ⚠ `int(a - REACH·pitch)` 는 파이썬 절삭 — Math.trunc
 */
function 이어잡기(p, a, b, w, T, B, pitch) {
  let lim = Math.max(T, Math.trunc(a - SPAN_REACH * pitch)), 끝 = a;
  for (let y = a - 1; y >= lim; y--) {
    if (p[y] > w * SPAN_LOW) 끝 = y;
    else if (끝 - y > SPAN_GAP * pitch) break;
  }
  const a2 = 끝;
  lim = Math.min(B, Math.trunc(b + SPAN_REACH * pitch)); 끝 = b;
  for (let y = b; y < lim; y++) {
    if (p[y] > w * SPAN_LOW) 끝 = y + 1;
    else if (y - 끝 > SPAN_GAP * pitch) break;
  }
  return [a2, 끝];
}

/**
 * `scan.spans_between` — T~B 안에서 열마다 글자가 시작하고 끝나는 y.
 * 뒷면 비침·계선 때문에 열 폭의 GLYPH 이상이 잉크인 줄만 글자 줄로 봄
 */
function 글자구간(prof, cols, T, B, pitch, 이어) {
  const Ts = Array.isArray(T) ? T : cols.map(function () { return T; });   // 열마다 목록이어도 됨(`열광곽`)
  const Bs = Array.isArray(B) ? B : cols.map(function () { return B; });
  const spans = cols.map(function (c, i) {
    const p = prof[i], need = (c[1] - c[0]) * GLYPH, t = Ts[i], bb = Bs[i];
    let a = -1, b = -1;
    for (let y = t; y < bb; y++) if (p[y] > need) { if (a < 0) a = y; b = y; }
    if (a < 0) return null;
    return (이어 && SPAN_EXTEND) ? 이어잡기(p, a, b + 1, c[1] - c[0], t, bb, pitch) : [a, b + 1];
  });
  const real = spans.filter(function (s) { return s; });
  if (!real.length) return null;
  let Emax = -Infinity;
  for (let i = 0; i < real.length; i++) if (real[i][1] > Emax) Emax = real[i][1];
  return spans.map(function (s, i) {
    if (!s) return null;
    let a = s[0], b = s[1];
    if (a - Ts[i] < pitch * 0.5) a = Ts[i];                 // 첫 글자가 흐려도 위에서 시작
    if (Emax - b < pitch * 0.6) b = Math.min(Emax, Bs[i]);  // 끝도 마찬가지 (열 광곽 너머로는 안 감)
    return [a, b];
  });
}

/**
 * `scan.tier_peak` — 쪽 가운데 띠에서 열들이 가장 많이 합의하는 가로줄.
 * ⚠ 열 하나만 보면 획·계선도 잡힘 — 열들의 합의로
 */
function 단봉우리(g, cols, lo, hi) {
  if (lo === undefined) lo = 0.30;
  if (hi === undefined) hi = 0.70;
  const H = g.높이;
  if (cols.length < 3) return null;
  const frac = new Float64Array(H);
  for (let i = 0; i < cols.length; i++) {
    const x0 = cols[i][0], x1 = cols[i][1];
    const p = 열잉크(g, x0, x1), need = (x1 - x0) * 0.90;
    for (let y = 0; y < H; y++) if (p[y] >= need) frac[y]++;
  }
  for (let y = 0; y < H; y++) frac[y] /= cols.length;
  const y0 = 자름(H * lo), y1 = 자름(H * hi);
  if (y1 - y0 <= 0) return null;
  let k = y0;
  for (let y = y0; y < y1; y++) if (frac[y] > frac[k]) k = y;
  const peak = frac[k], th = Math.max(0.10, peak * 0.6);
  let a = k, b = k;
  while (a > y0 && frac[a - 1] >= th) a--;
  while (b + 1 < y1 && frac[b + 1] >= th) b++;
  return [peak, k / H, a, b + 1];
}

/** `scan.tier_divider` — 단을 가르는 가운데 가로줄. */
function 단가름(g, cols, agree) {
  const r = 단봉우리(g, cols);
  return (r === null || r[0] < agree) ? null : [r[2], r[3]];
}

/** `scan.tier_measure` — 이 쪽의 [가운데 가로줄 합의도, 쪽 높이에서의 자리]. 못 재면 null. */
function 단측정(g) {
  const 찾 = 열찾기(g);
  if (!찾.열.length) return null;
  const r = 단봉우리(g, 찾.열);
  return r === null ? null : [r[0], r[1]];
}

// ── 가름줄 판형 (가로줄로 단을 나눈 것) — scan.py 의 같은 절 ──
// 잣대는 열 사이 고랑 — 글자 획은 고랑에서 끊기고 가름줄은 고랑을 가로지름
// ⚠ 쪽 하나로는 못 가림 — `판형정하기` 가 문헌 단위로 높이를 정하고, 쪽에서는 그 근처만

/** `scan.고랑곡선` — 행마다, 열 사이 고랑 중 가로로 잉크가 꽉 찬 것의 비율. */
function 고랑곡선(g, cols, 띠, 채움) {
  if (띠 === undefined) 띠 = 4;
  if (채움 === undefined) 채움 = 0.8;
  const H = g.높이, W = g.너비, v = g.값;
  // ⚠ 파이썬 `sorted(cols)` — 앞 값, 같으면 뒤 값으로
  const c = cols.map(function (x) { return [x[0], x[1]]; })
                .sort(function (p, q) { return (p[0] - q[0]) || (p[1] - q[1]); });
  const 고랑 = [];
  for (let i = 0; i + 1 < c.length; i++) {
    if (c[i + 1][0] - c[i][1] >= 4) 고랑.push([c[i][1], c[i + 1][0]]);
  }
  const G = new Float64Array(H);
  if (!고랑.length) return G;
  const 누적 = new Int32Array(H + 1), 셈 = new Int32Array(H);
  for (let k = 0; k < 고랑.length; k++) {
    const a = 고랑[k][0], b = 고랑[k][1], need = (b - a) * 채움;
    셈.fill(0);
    for (let x = a; x < b; x++) {
      누적[0] = 0;                              // 이 x 줄의 세로 누적 잉크
      for (let y = 0; y < H; y++) 누적[y + 1] = 누적[y] + (v[y * W + x] < INK ? 1 : 0);
      for (let y = 0; y < H; y++) {           // 위아래 `띠` 안에 잉크가 있는가
        if (누적[Math.min(y + 띠 + 1, H)] - 누적[Math.max(y - 띠, 0)] > 0) 셈[y]++;
      }
    }
    for (let y = 0; y < H; y++) if (셈[y] >= need) G[y]++;
  }
  for (let y = 0; y < H; y++) G[y] /= 고랑.length;
  return G;
}

/** `scan._줄덩이` — 곡선이 문턱을 넘는 이어진 행들 → [[시작, 끝, 최대값], …] */
function 줄덩이(G, 문턱) {
  if (문턱 === undefined) 문턱 = 0.15;
  const out = [], H = G.length;
  let y = 0;
  while (y < H) {
    if (G[y] >= 문턱) {
      let e = y, m = G[y];
      while (e + 1 < H && G[e + 1] >= 문턱) { e++; if (G[e] > m) m = G[e]; }
      out.push([y, e + 1, m]);
      y = e + 1;
    } else y++;
  }
  return out;
}

/** `scan.가름줄측정` — [쪽 안쪽의 가장 센 봉우리, [[가운데 높이 비율, 세기], …]]. 못 재면 null. */
function 가름줄측정(g) {
  const H = g.높이;
  const 찾 = 열찾기(g);
  if (!찾.열.length) return null;
  const TB = 광곽(g, 찾.열, true);
  const a = 자름(TB[0] + 3 * 찾.자간), b = 자름(TB[1] - 3 * 찾.자간);
  if (b <= a) return null;
  const G = 고랑곡선(g, 찾.열, 4, 0.6);        // ⚠ 판정은 채움 0.6
  let mx = -Infinity;
  for (let y = a; y < b; y++) if (G[y] > mx) mx = G[y];
  const 덩 = 줄덩이(G).filter(function (d) {
    const m = (d[0] + d[1]) / 2;
    return a <= m && m < b;
  }).map(function (d) { return [(d[0] + d[1]) / 2 / H, d[2]]; });
  return [mx, 덩];
}

/** `scan.최소쪽` — 판정에 쓸 쪽 수. 보통 4, 쪽이 적은 파일은 있는 만큼(2 이상). */
function 최소쪽(n) { return Math.max(2, Math.min(4, n)); }

/**
 * `scan.가름줄정하기` — 쪽마다 잰 것(못 잰 쪽은 null) → 가름줄 높이 목록 또는 null.
 * ⚠ 파이썬 `round(x, 4)` 와 끝자리가 드물게 갈리지만 결과는 같음
 */
function 가름줄정하기(잰것들, 문턱, 센줄, 모음) {
  if (문턱 === undefined) 문턱 = 0.5;
  if (센줄 === undefined) 센줄 = 0.4;
  if (모음 === undefined) 모음 = 0.03;
  const got = 잰것들.filter(function (v) { return v; });
  if (got.length < 최소쪽(잰것들.length)
      || 중앙값(got.map(function (v) { return v[0]; })) < 문턱) return null;
  const 점 = [];
  got.forEach(function (v, k) {
    v[1].forEach(function (d) {
      if (d[1] >= 센줄 && 0.2 <= d[0] && d[0] <= 0.8) 점.push([d[0], k]);
    });
  });
  점.sort(function (p, q) { return (p[0] - q[0]) || (p[1] - q[1]); });
  const 줄 = [];                       // 이웃 점과 `모음` 안으로 붙은 것끼리 한 무리
  점.forEach(function (pk) {
    const 끝 = 줄[줄.length - 1];
    if (끝 && pk[0] - 끝[끝.length - 1][0] <= 모음) 끝.push(pk);
    else 줄.push([pk]);
  });
  const out = [];
  줄.forEach(function (z) {
    const 쪽들 = new Set(z.map(function (pk) { return pk[1]; }));
    if (쪽들.size * 2 > got.length) {
      out.push(Math.round(중앙값(z.map(function (pk) { return pk[0]; })) * 1e4) / 1e4);
    }
  });
  return out.length ? out : null;
}

/**
 * `page.doc_tiers` 의 판정 — 문헌(파일)의 판형: 1 · 2 · 가름줄 높이 목록. 가름줄을 먼저 봄
 * 가름잰것들 = 12쪽의 `가름줄측정`, 단잰것들 = 8쪽의 `단측정` (못 잰 쪽은 null)
 */
function 판형정하기(가름잰것들, 단잰것들) {
  const 가름 = 가름줄정하기(가름잰것들);
  if (가름) return 가름;
  const got = 단잰것들.filter(function (v) { return v; });
  if (got.length < 최소쪽(단잰것들.length)) return 1;
  const 합의 = 중앙값(got.map(function (v) { return v[0]; }));
  const 자리 = got.map(function (v) { return v[1]; });
  const 가운데 = 중앙값(자리);
  const 흔들림 = 중앙값(자리.map(function (p) { return Math.abs(p - 가운데); }));
  return (합의 >= 0.40 && 흔들림 <= 0.02) ? 2 : 1;
}

/** 그림의 [a, b) 행만 (값은 같은 버퍼) */
function 행자르기(g, a, b) {
  return { 너비: g.너비, 높이: b - a, 값: g.값.subarray(a * g.너비, b * g.너비) };
}

/** `scan._가름판_geometry` — 단을 가르고 **단마다 열을 따로** 찾는다. */
function 가름판기하(g, ratio, 가름) {
  const H = g.높이, W = g.너비;
  const 찾 = 열찾기(g);
  const xp0 = 찾.자간, cols0 = 찾.열;
  if (!cols0.length) return null;
  const 덩 = 줄덩이(고랑곡선(g, cols0));
  const 자름들 = [];
  가름.forEach(function (p) {                    // 문헌이 정한 높이 근처의 가장 센 줄
    const y = p * H;
    let 고른 = null;
    덩.forEach(function (d) {                   // 파이썬 max — 같으면 먼저 나온 것
      if (Math.abs((d[0] + d[1]) / 2 - y) <= 2 * xp0 && (고른 === null || d[2] > 고른[2])) 고른 = d;
    });
    자름들.push(고른 ? [고른[0], 고른[1]] : [자름(y) - 4, 자름(y) + 4]);
  });
  덩.forEach(function (d) { if (d[2] >= 0.9) 자름들.push([d[0], d[1]]); });   // 광곽·제호 상자
  자름들.sort(function (p, q) { return (p[0] - q[0]) || (p[1] - q[1]); });
  let 구간 = [], 끝 = 0;
  자름들.forEach(function (se) {
    if (se[0] > 끝) 구간.push([끝, se[0]]);
    끝 = Math.max(끝, se[1]);
  });
  구간.push([끝, H]);
  let 키 = 0;
  구간.forEach(function (r) { if (r[1] - r[0] > 키) 키 = r[1] - r[0]; });
  구간 = 구간.filter(function (r) { return r[1] - r[0] >= Math.max(6 * xp0, 0.4 * 키); });

  const 단들 = [];
  구간.forEach(function (r) {
    const f = 열찾기(행자르기(g, r[0], r[1]));
    if (f.열.length && f.자간) 단들.push([r[0], r[1], f.자간, f.열]);
  });
  if (!단들.length) return null;
  const xpitch = 중앙값(단들.map(function (d) { return d[2]; }));
  const pitch = xpitch * ratio, half = xpitch * 0.45;
  let cols = [], spans = [], sm = [];
  단들.forEach(function (d) {
    const prof = 잉크무늬(g, d[3]);
    const sp = 글자구간(prof, d[3], d[0] + 2, d[1] - 2, pitch);
    if (sp === null) return;
    cols = cols.concat(d[3]); spans = spans.concat(sp);
    sm = sm.concat(prof.map(function (p) { return 고르기(p, Math.max(2.0, pitch / 9)); }));
  });
  if (!cols.length) return null;
  const est = spans.map(function (s) {
    return s === null ? 0 : Math.max(1, 반올림((s[1] - s[0]) / pitch));
  });
  const crop_cols = cols.map(function (c) {
    const mid = (c[0] + c[1]) / 2;
    return [Math.max(0, 자름(mid - half)), Math.min(W, 자름(mid + half))];
  });
  return {
    그림: g, cols: cols, crop_cols: crop_cols, spans: spans, sm: sm,
    pitch: pitch, xpitch: xpitch, est: est, 단: 단들.length, 가장자리: false,
    본열수: cols0.length,
  };
}

/**
 * `scan.smooth` — 가우시안.
 * ⚠ 커널은 `np.arange(-3s, 3s+1)` 그대로 — s 가 실수라 정수 격자가 아니고 길이가 짝수일 수도.
 *   정수 대칭 커널로 바꾸면 자를 자리가 1px 밀림
 * ⚠ `np.convolve(…, 'same')` — 시작 자리는 `(n−1)//2`
 */
function 고르기(a, s) {
  const 시작 = -3 * s;
  const n = Math.ceil(3 * s + 1 - 시작);       // np.arange(-3s, 3s+1) 의 길이
  const k = new Float64Array(n);
  let sum = 0;
  for (let i = 0; i < n; i++) {
    const t = (시작 + i) / s;
    k[i] = Math.exp(-0.5 * t * t);
    sum += k[i];
  }
  for (let i = 0; i < n; i++) k[i] /= sum;
  const L = a.length, out = new Float64Array(L), off = Math.floor((n - 1) / 2);
  for (let i = 0; i < L; i++) {
    let v = 0;
    for (let j = 0; j < n; j++) {
      const t = i + off - j;
      if (t >= 0 && t < L) v += a[t] * k[j];
    }
    out[i] = v;
  }
  return out;
}

/** `scan.cut_points` — 글자 사이 골짜기를 자를 자리 후보로 삼는다. */
function 자를후보(sp, y0, y1, pitch) {
  const c = [], end = Math.min(y1 - 1, sp.length - 1);
  for (let y = y0 + 1; y < end; y++) {
    if (sp[y] <= sp[y - 1] && sp[y] < sp[y + 1]) c.push(y);
  }
  if (c.length >= 4) return c;
  const out = [], step = Math.max(4, 자름(pitch / 6));
  for (let y = y0 + 자름(pitch * 0.5); y < y1 - 자름(pitch * 0.5); y += step) out.push(y);
  return out;
}

const INF = 1e9;

/**
 * `scan.split_column` — 한 열을 정확히 n 칸으로 가른다.
 * 비용 = 자른 자리의 잉크량 + lam × (칸 높이가 고르지 못한 정도)
 * 반환: {자리, 비용}. 못 하면 {자리:null, 비용:INF}
 */
function 열가르기(sp, y0, y1, n, cands, lam) {
  if (lam === undefined) lam = 1.2;
  if (n <= 0) return { 자리: null, 비용: INF };
  const pitch = (y1 - y0) / n;
  if (n === 1) return { 자리: [y0, y1], 비용: 0.0 };
  const pts = [y0];
  for (let i = 0; i < cands.length; i++) {
    const c = cands[i];
    if (c > y0 && c < y1) pts.push(c);
  }
  pts.push(y1);
  const m = pts.length;
  if (m < n + 1) return { 자리: null, 비용: INF };
  let mx = 1.0;
  const lim = Math.min(y1, sp.length);
  for (let y = y0; y < lim; y++) if (sp[y] > mx) mx = sp[y];
  const lo = pitch * 0.45, hi = pitch * 2.0;
  const dp = [], prev = [];
  for (let c = 0; c <= n; c++) {
    dp.push(new Float64Array(m).fill(INF));
    prev.push(new Int32Array(m).fill(-1));
  }
  dp[0][0] = 0.0;
  for (let c = 1; c <= n; c++) {
    for (let j = 1; j < m; j++) {
      const yj = pts[j];
      let best = INF, bi = -1;
      for (let i = j - 1; i >= 0; i--) {
        const h = yj - pts[i];
        if (h < lo) continue;
        if (h > hi) break;
        if (dp[c - 1][i] >= INF) continue;
        let cost = dp[c - 1][i] + Math.pow((h - pitch) / pitch, 2) * lam;
        if (c < n) cost += sp[Math.min(yj, sp.length - 1)] / mx;
        if (cost < best) { best = cost; bi = i; }
      }
      dp[c][j] = best; prev[c][j] = bi;
    }
  }
  if (dp[n][m - 1] >= INF) return { 자리: null, 비용: INF };
  const out = [];
  let c = n, j = m - 1;
  while (c > 0) { out.push(pts[j]); j = prev[c][j]; c--; }
  out.push(pts[0]);
  out.sort(function (a, b) { return a - b; });
  return { 자리: out, 비용: dp[n][m - 1] };
}

/**
 * `scan.page_geometry` — 쪽 그림 → 열·글자 구간·세로 자간. 못 읽으면 null.
 * 무거운 계산은 여기 한 번뿐이고 뒤 단계는 이 결과를 돌려쓴다.
 */
function 쪽기하(g, ratio, 단, 읽기, 표준자간) {
  ratio = ratio || YX_RATIO;
  if (Array.isArray(단)) return 가름판기하(g, ratio, 단);   // 가름줄 판형
  단 = 단 || 1;
  const 후보 = !!읽기 && 단 === 1;
  const 찾 = 열찾기(g, !후보, 읽기 ? 표준자간 : null);
  const xpitch = 찾.자간;
  let cols0 = 찾.열;
  if (!cols0.length || !xpitch) return null;
  let 본열수 = null;
  if (후보) {
    본열수 = 판심떼기(cols0.slice().reverse()).length;
    cols0 = 가장자리후보(cols0, xpitch, g.너비);
  }
  const pitch = xpitch * ratio;
  let prof = 잉크무늬(g, cols0);
  const TB = 광곽(g, cols0, 읽기), T = TB[0], B = TB[1];
  const 쪽광곽 = !!읽기 && FRAME_LOCAL && 광곽합의(g, cols0) !== null;   // 열마다 다듬을 수 있나(`열광곽`)
  if (후보 && EDGE_MOVE) {
    cols0 = 줄에서비키기(g, cols0, xpitch, T, B);
    prof = 잉크무늬(g, cols0);
  }

  // 두 단임은 문헌 단위로 알고 들어옴 — '있는가' 가 아니라 '어디인가' 만 물음(문턱 0.10)
  let div = (단 >= 2) ? 단가름(g, cols0, 0.10) : null;
  let 위 = null, 아래 = null;
  if (div) {
    위 = 글자구간(prof, cols0, T, Math.max(T + 1, div[0] - 6), pitch);
    아래 = 글자구간(prof, cols0, Math.min(B - 1, div[1] + 6), B, pitch);
    if (위 === null || 아래 === null) div = null;
  }
  const sm0 = prof.map(function (p) { return 고르기(p, Math.max(2.0, pitch / 9)); });
  let spans, cols, sm;
  if (div) {
    spans = 위.concat(아래);
    cols = cols0.concat(cols0);              // 같은 x 자리를 두 번 쓴다
    sm = sm0.concat(sm0);
  } else {
    let TT = T, BB = B;
    if (쪽광곽) { const 열TB = 열광곽(g, cols0, T, B, xpitch, pitch); TT = 열TB[0]; BB = 열TB[1]; }
    spans = 글자구간(prof, cols0, TT, BB, pitch, !!읽기);
    cols = cols0; sm = sm0;
  }
  if (spans === null) return null;
  const est = spans.map(function (s) {
    return s === null ? 0 : Math.max(1, 반올림((s[1] - s[0]) / pitch));
  });

  // 글자 상자는 열보다 넓게(가로 자간 기준) — 오른쪽의 가는 모음 획이 잘리면 아래아와 구별이 안 됨
  const half = xpitch * 0.45, W = g.너비;
  const crop_cols = cols.map(function (c) {
    const mid = (c[0] + c[1]) / 2;
    return [Math.max(0, 자름(mid - half)), Math.min(W, 자름(mid + half))];
  });
  const out = {
    그림: g, cols: cols, crop_cols: crop_cols, spans: spans, sm: sm,
    pitch: pitch, xpitch: xpitch, est: est, 단: div ? 2 : 1, 가장자리: 후보,
  };
  if (본열수 !== null) out.본열수 = 본열수;
  return out;
}

// ════════════════════════════════════════════════════════════════════
//  page.py
// ════════════════════════════════════════════════════════════════════

let TEDURI = 1.6;   // 잉크가 다른 열 중앙값의 이 배를 넘으면 광곽 선으로 본다

/**
 * `page.쪽건강` — 이 쪽이 제대로 잘렸는가(전사문 없이). 반환 {등급: 좋음 · 의심 · 못씀, 까닭}
 * ⚠ '잘 잘렸는가' 만 — '얼마나 잘 읽었는가' 는 `확신표시` 몫
 * ⚠ 두 단 판형은 열이 두 배라 `단` 으로 나눠 셈
 */
function 쪽건강(geo, 표준) {
  const 까닭 = [];
  if (!geo || !geo.cols || !geo.cols.length) {
    return { 등급: "못씀", 까닭: ["열을 찾지 못했습니다"] };
  }
  if (표준) {
    const xp = geo.xpitch;
    let n = Math.floor(geo.cols.length / Math.max(geo.단 || 1, 1));
    // ⚠ 읽는 경로는 가장자리 후보가 붙어 있어 판심만 뗀 열 수로 셈
    if (geo.본열수 !== undefined) n = geo.본열수;
    if (xp && Math.abs(xp - 표준.자간) > 표준.자간 * 0.25) {
      // ⚠ 파이썬 `f"{x:.0f}"` 는 은행가 반올림 — `toFixed(0)` 과 다름
      까닭.push("열 간격이 이 문헌 표준과 다릅니다 ("
                + 반올림(xp) + " 대 " + 반올림(표준.자간) + ")");
      return { 등급: "못씀", 까닭: 까닭 };
    }
    if (표준.열수 && Math.abs(n - 표준.열수) > 표준.열수 * 0.25) {
      까닭.push("열이 " + n + "개입니다 (이 문헌은 보통 " + 표준.열수 + "개)");
    }
  }
  return { 등급: 까닭.length ? "의심" : "좋음", 까닭: 까닭 };
}

/**
 * `page.테두리열버리기` — 광곽 선이 열로 잡힌 것 버리기.
 * ⚠ 지금은 안 씀(파이썬도) — 진짜 본문 열을 버렸음. 대조·실험용
 * ⚠ 첫 열·끝 열만 봄. 두 단 판형에서는 부르지 않음
 */
function 테두리열버리기(geo, 배수) {
  if (배수 === undefined) 배수 = TEDURI;
  const n = geo.cols.length;
  if (n < 4) return geo;
  const prof = 잉크무늬(geo.그림, geo.cols);
  const v = [];
  for (let i = 0; i < n; i++) {
    const sp = geo.spans[i];
    const w = Math.max(1, geo.cols[i][1] - geo.cols[i][0]);
    if (!sp) { v.push(0.0); continue; }
    let s = 0;
    for (let y = sp[0]; y < sp[1]; y++) s += prof[i][y];
    v.push(s / w);
  }
  const med = 중앙값(v);
  const 버릴 = {};
  [0, n - 1].forEach(function (i) { if (v[i] > med * 배수) 버릴[i] = true; });
  if (!Object.keys(버릴).length) return geo;
  const 남 = [];
  for (let i = 0; i < n; i++) if (!버릴[i]) 남.push(i);
  const 새 = {};
  for (const k in geo) 새[k] = geo[k];
  ["cols", "crop_cols", "spans", "sm", "est"].forEach(function (k) {
    새[k] = 남.map(function (i) { return geo[k][i]; });
  });
  return 새;
}

/**
 * `page.geometry` — 문헌의 자간 비율·판형을 반영한 쪽 기하.
 * ⚠ 읽을 때만 하는 것 둘 — 가장자리 후보 열 붙이기, 광곽 경계를 안쪽까지 바짝
 */
function 기하(g, 문헌설정, 읽기) {
  const s = 문헌설정 || {};
  const 단 = s.단 || 1;
  const r = (읽기 && s.읽기자간비) || s.자간비 || YX_RATIO;
  const 표준 = (읽기 && s.판짜임 && PITCH_USE) ? s.판짜임.자간 : null;   // `page.geometry` 와 같게
  return 쪽기하(g, r, 단, 읽기, 표준);
}

// ════════════════════════════════════════════════════════════════════
//  align.py
// ════════════════════════════════════════════════════════════════════

/**
 * `align.build_plans` — 열마다 여러 칸수로 잘라 본 후보들.
 *   계획[i] = [{칸수, 상자들, 시작, 개수, 비용}, …] · 상자 = 모든 후보 상자를 한 줄로
 * ⚠ 읽을 때는 `빈열허용=false` — 칸수 0 은 자를 때만
 */
function 자를계획(geo, centers, span, 빈열허용, 그림자) {
  const 계획 = [], 상자 = [];
  for (let i = 0; i < geo.crop_cols.length; i++) {
    const x0 = geo.crop_cols[i][0], x1 = geo.crop_cols[i][1];
    const opts = [];
    const sp = geo.spans[i];
    if (sp) {
      const y0 = sp[0], y1 = sp[1];
      const smi = 그림자 ? 그림자[i] : geo.sm[i];   // `그림자` = 검출기로 바꾼 것(`align.CUT_LEARN`)
      const cands = 자를후보(smi, y0, y1, geo.pitch);
      for (let n = Math.max(1, centers[i] - span); n <= centers[i] + span; n++) {
        const r = 열가르기(smi, y0, y1, n, cands);
        if (!r.자리) continue;
        const bx = [];
        for (let k = 0; k + 1 < r.자리.length; k++) {
          bx.push([x0, r.자리[k], x1, r.자리[k + 1]]);
        }
        opts.push({ 칸수: n, 상자들: bx, 시작: 상자.length, 개수: bx.length, 비용: r.비용 });
        for (let k = 0; k < bx.length; k++) 상자.push(bx[k]);
      }
      if (!opts.length) {              // 한 열이 안 갈라져도 쪽은 버리지 않음
        const n = Math.max(1, centers[i]);
        const bx = [];
        for (let k = 0; k < n; k++) {
          bx.push([x0, 자름(y0 + (y1 - y0) * k / n), x1, 자름(y0 + (y1 - y0) * (k + 1) / n)]);
        }
        opts.push({ 칸수: n, 상자들: bx, 시작: 상자.length, 개수: bx.length, 비용: 3.0 * n });
        for (let k = 0; k < bx.length; k++) 상자.push(bx[k]);
      }
    }
    if (빈열허용 || !opts.length) {
      opts.push({ 칸수: 0, 상자들: [], 시작: 상자.length, 개수: 0, 비용: 0.0 });
    }
    계획.push(opts);
  }
  return { 계획: 계획, 상자: 상자 };
}

/**
 * `align.read_page` — 전사문 없이 쪽 읽기. 열마다 여러 칸수로 잘라 보고 모델이 가장 자신 있어 한 것을 고름
 * ⚠ 점수는 로그 기하평균, 모델 확신도만 — 다른 묶기·벌점은 전부 나빠짐
 * `geo.가장자리` 면 양 끝 열을 `가장자리다듬기` 로 가림
 */
async function 쪽읽기(모델, geo, span) {
  const r = await 열마다읽기(모델, geo, span);
  const 열들 = r.열들;
  let 남 = [];
  if (geo.가장자리) 남 = 가장자리다듬기(geo, 열들);
  else for (let i = 0; i < 열들.length; i++) 남.push(i);
  const out = [], conf = [], 줄들 = [];
  남.forEach(function (i) {
    if (열들[i] === null) return;
    줄들.push(열들[i]);                 // 열 하나 = 원문 한 줄 (`align.read_page_lines`)
    for (let j = 0; j < 열들[i].글자.length; j++) {
      out.push(열들[i].글자[j]); conf.push(열들[i].확신[j]);
    }
  });
  let 띄움 = null;
  if (SPACE) {                        // `read_page_lines(…, 띄움=True)` — 줄.빈[k] = k 번째 글자 뒤를 띄우는가
    띄움 = 띄울자리(geo.그림, 줄들);
    줄들.forEach(function (z, k) { z.빈 = 띄움.빈[k]; });
  }
  return { 글자: out, 확신: conf, 줄들: 줄들, 상자수: r.상자수, 남긴열: 남, 띄움: 띄움 };
}

// ── 띄어쓰기 (`align.띄울자리`, 2026-09-29) ─────────────────────────
// 한 열 안 이웃 글자의 잉크 빈틈 ÷ 칸 높이 중앙값 − 모양 고침 > 쪽마다 오츠 문턱이면 띄움. 열 끝은 못 봄
// ⚠ 합은 앞에서부터 차례로 — 파이썬도 그렇게 짬(numpy 합은 차례가 달라 안 씀)
let SPACE = true, SPACE_ROW = 0.03, SPACE_ETA = 0.5, SPACE_LOW = 0.2;
let SPACE_FRAC = [0.08, 0.6], SPACE_CLIP = [-0.5, 1.5], SPACE_BEFORE = {}, SPACE_AFTER = {};   // 표는 설정.json 에서

/** `align._띄움모양` — 중성(없으면 글자 그대로) + 받침이 있으면 '받침' */
function 띄움모양(c) {
  return (c.length > 1 ? c[1] : c) + (c.length > 2 ? "받침" : "");
}

function 표값(표, k) {
  return Object.prototype.hasOwnProperty.call(표, k) ? 표[k] : 0.0;
}

/** `align._잉크위아래` — 상자 안 잉크 행의 첫 · 끝(쪽 좌표). 없으면 null */
function 잉크위아래(g, b) {
  const W = g.너비, H = g.높이, v = g.값;
  const x0 = b[0], y0 = b[1], x1 = b[2], y1 = b[3];
  const ya = Math.max(0, y0), yb = Math.min(H, Math.max(0, y1));
  const xa = Math.max(0, x0), xb = Math.min(W, Math.max(0, x1));
  if (yb <= ya || xb <= xa) return null;
  const 문 = Math.max(2, (x1 - x0) * SPACE_ROW);
  let 첫 = -1, 끝 = -1;
  for (let y = ya; y < yb; y++) {
    let n = 0;
    const o = y * W;
    for (let x = xa; x < xb; x++) if (v[o + x] < INK) n++;
    if (n > 문) { if (첫 < 0) 첫 = y; 끝 = y; }
  }
  return 첫 < 0 ? null : [첫, 끝];
}

/** `align.빈틈값` — 한 열의 이웃 글자 쌍마다 빈틈 값. 잴 수 없으면 null */
function 빈틈값(글, 상, 잉크) {
  if (!상.length) return [];
  const h = 중앙값(상.map(function (b) { return b[3] - b[1]; }));
  const out = [];
  for (let k = 0; k + 1 < 글.length; k++) {
    const a = 잉크[k], b = 잉크[k + 1];
    if (a === null || b === null || h <= 0) { out.push(null); continue; }
    let x = (b[0] - a[1]) / h;
    x -= 표값(SPACE_BEFORE, 띄움모양(글[k])) + 표값(SPACE_AFTER, 띄움모양(글[k + 1]));
    out.push(x);
  }
  return out;
}

/** `align.빈틈가르기` — 쪽의 빈틈을 둘로 가르는 문턱(오츠). 띄우지 말아야 하면 null */
function 빈틈가르기(값들) {
  const lo = SPACE_CLIP[0], hi = SPACE_CLIP[1];
  const v = Float64Array.from(값들, function (x) { return Math.min(Math.max(x, lo), hi); }).sort();
  const n = v.length;
  if (n < 10) return null;
  const 누적 = new Float64Array(n + 1);
  for (let i = 0; i < n; i++) 누적[i + 1] = 누적[i] + v[i];
  const m = 누적[n] / n;
  let 제곱 = 0.0;
  for (let i = 0; i < n; i++) 제곱 += (v[i] - m) * (v[i] - m);
  if (제곱 <= 0) return null;
  let 최고 = -1.0, 자리 = -1;
  for (let i = 1; i < n; i++) {
    if (v[i - 1] === v[i]) continue;
    const ma = 누적[i] / i, mb = (누적[n] - 누적[i]) / (n - i);
    const s = i * (n - i) * (ma - mb) * (ma - mb);
    if (s > 최고) { 최고 = s; 자리 = i; }
  }
  if (자리 < 0) return null;
  const η = 최고 / (n * 제곱), i = 자리;
  const 아래 = (i % 2) ? v[(i - 1) >> 1] : (v[i / 2 - 1] + v[i / 2]) / 2;
  const 위몫 = (n - i) / n;
  if (η < SPACE_ETA || 아래 >= SPACE_LOW || !(SPACE_FRAC[0] <= 위몫 && 위몫 <= SPACE_FRAC[1])) return null;
  return (v[i - 1] + v[i]) / 2;
}

/** `align.띄울자리` — 줄마다 [글자 뒤를 띄우는가]. 반환: {빈, 문턱, 값(대조용)} */
function 띄울자리(g, 줄들) {
  const 값 = 줄들.map(function (z) {
    return 빈틈값(z.글자, z.상자, z.상자.map(function (b) { return 잉크위아래(g, b); }));
  });
  const 모두 = [];
  값.forEach(function (열) { 열.forEach(function (x) { if (x !== null) 모두.push(x); }); });
  const t = 빈틈가르기(모두);
  const 빈 = 값.map(function (열, k) {
    const r = 열.map(function (x) { return t !== null && x !== null && x > t; });
    if (줄들[k].글자.length) r.push(false);
    return r;
  });
  return { 빈: 빈, 문턱: t, 값: 값 };
}

/**
 * `align.열마다읽기` — 열마다 가장 자신 있는 칸수로 읽는다(`쪽읽기` 의 앞 절반).
 * 열들[i] = {점수(로그 확신 평균), 글자, 확신} — 읽을 것이 없는 열은 null.
 */
async function 열마다읽기(모델, geo, span) {
  if (span === undefined) span = 3;
  const 그림자 = (CUT_LEARN && 모델.경계) ? await 경계프로파일(모델, geo) : null;
  const bp = 자를계획(geo, geo.est, span, false, 그림자);
  const 읽음 = await 모델.읽기(geo.그림, bp.상자);
  const pL = 읽음.초, pV = 읽음.중, pT = 읽음.종, cf = 읽음.확신;
  const logc = new Float64Array(cf.length);
  for (let i = 0; i < cf.length; i++) logc[i] = Math.log(Math.max(cf[i], 1e-6));

  const 열들 = [];
  for (let i = 0; i < bp.계획.length; i++) {
    const opts = bp.계획[i].filter(function (o) { return o.칸수 > 0; });
    if (!opts.length) { 열들.push(null); continue; }
    // ⚠ 파이썬 `max` 는 동점이면 먼저 나온 것 — 그래서 `>` (`>=` 아님)
    let best = null, bestv = -Infinity;
    for (let k = 0; k < opts.length; k++) {
      const o = opts[k];
      let s = 0;
      for (let j = 0; j < o.개수; j++) s += logc[o.시작 + j];
      const v = o.개수 ? s / o.개수 : NaN;
      if (v > bestv) { bestv = v; best = o; }
    }
    // 글자가 아닌 칸(작은 절 번호 · 광곽 가로줄)은 글자에서 뺀다 — 점수는 그대로
    const 글 = [], 확 = [], 상 = [];
    for (let j = 0; j < best.개수; j++) {
      const c = cf[best.시작 + j];
      const 자 = 모델.글자(pL[best.시작 + j], pV[best.시작 + j], pT[best.시작 + j]);
      if (c < NOTCHAR_CONF && NOTCHAR_KEEP.indexOf(자) < 0) {
        const m = 칸모양(geo.그림, best.상자들[j]);
        if (m[0] < NOTCHAR_WIDTH || m[1] >= NOTCHAR_ROW) continue;
      }
      글.push(자);
      확.push(c);
      상.push(best.상자들[j]);
    }
    열들.push({ 점수: bestv, 글자: 글, 확신: 확, 칸수: best.개수, 상자: 상 });
  }
  if (HEADING) await 큰제목읽기(모델, geo, 열들, span);
  return { 열들: 열들, 상자수: bp.상자.length };
}

let CUT_LEARN = true, CUT_MIX = 0.5, 경계폭 = 32, CUT_CLIP = 0.0, CUT_ROUND = 10000;   // align.CUT_LEARN · CUT_MIX · 경계검출.폭

/**
 * `경계검출.띠` — 열 [x0, x1) 를 쪽 높이째 잘라 가로 `경계폭` 으로 줄인 띠(BICUBIC, `오리기` 와 같은 두 패스).
 * 반환: {값: Float32Array(높이 × 경계폭), 높이, 배율}
 */
function 경계띠(g, x0, x1) {
  const W = g.너비, H = g.높이, v = g.값;
  x0 = Math.max(0, 자름(x0)); x1 = Math.min(W, 자름(x1));
  const cw = Math.max(1, x1 - x0), s = 경계폭 / cw;
  const h = Math.max(8, 반올림(H * s));
  const src = new Uint8Array(cw * H);
  for (let y = 0; y < H; y++) {
    const so = y * W + x0, to = y * cw;
    for (let x = 0; x < cw; x++) src[to + x] = v[so + x];
  }
  const px = 줄이기8(src, cw, H, 경계폭, h);           // Pillow BICUBIC 과 픽셀까지 같게
  const out = new Float32Array(h * 경계폭);
  for (let k = 0; k < out.length; k++) out[k] = (px[k] / 255 - 0.5) / 0.5;
  return { 값: out, 높이: h, 배율: s };
}

/**
 * `align.경계프로파일` — 열마다 자르기에 쓸 그림자 = (1 − 섞기) × 잉크 그림자 + 섞기 × (1 − 경계 확률) × 잉크 크기.
 * 경계 확률은 띠 줄마다 → 쪽 높이로 선형 보간(`np.interp` — 끝은 끝값).
 */
async function 경계프로파일(모델, geo) {
  const out = [];
  for (let i = 0; i < geo.crop_cols.length; i++) {
    const sm = geo.sm[i], sp = geo.spans[i];
    if (!sp) { out.push(sm); continue; }
    const p = await 모델.경계(geo.그림, geo.crop_cols[i][0], geo.crop_cols[i][1]);
    let 크기 = 1.0;
    if (sp[1] > sp[0]) {
      let mx = -Infinity;
      for (let y = sp[0]; y < Math.min(sp[1], sm.length); y++) if (sm[y] > mx) mx = sm[y];
      크기 = Math.max(1.0, mx);
    }
    const r = new Float64Array(sm.length);
    // ⚠ 경계 확률을 [CUT_CLIP, 1 − CUT_CLIP] 로 — 빈 곳 · 포화된 곳을 정확히 평평하게(계산 잡음이 자를 후보에 닿지 않게)
    const lo = CUT_CLIP, hi = 1 - CUT_CLIP;
    for (let y = 0; y < sm.length; y++) {
      const c = p[y] < lo ? lo : (p[y] > hi ? hi : p[y]);
      const q = 반올림(c * CUT_ROUND) / CUT_ROUND;        // np.round 와 같은 은행가 반올림
      r[y] = (1 - CUT_MIX) * sm[y] + CUT_MIX * (1 - q) * 크기;
    }
    out.push(r);
  }
  return out;
}

let HEADING = true, HEADING_LOW = 0.25, HEADING_GAIN = 0.10, HEADING_CONF = 0.5, HEADING_INK = 0.15;   // align.py 와 같은 값
let HEADING_K = [2, 3, 4, 5, 6], HEADING_H = [1.5, 1.7, 1.9, 2.1];

/** `align._잉크범위` — [y0, y1) 의 처음 잉크 덩어리. `틈`(px) 넘게 비면 끊음. 없으면 null */
function 잉크범위(prof, y0, y1, 틈) {
  const 끝자리 = Math.min(y1, prof.length);          // 파이썬 prof[y0:y1] 은 길이에서 멈춤
  if (끝자리 - y0 <= 0) return null;
  let mx = -Infinity;
  for (let y = y0; y < 끝자리; y++) if (prof[y] > mx) mx = prof[y];
  if (!(mx > 0)) return null;
  const 문 = mx * HEADING_INK;
  let 첫 = -1, 끝 = -1;
  for (let t = 0; t < 끝자리 - y0; t++) {
    if (!(prof[y0 + t] > 문)) continue;
    if (첫 < 0) { 첫 = t; 끝 = t; continue; }
    if (틈 !== undefined && t - 끝 > 틈) break;
    끝 = t;
  }
  return 첫 < 0 ? null : [y0 + 첫, y0 + 끝 + 1];
}

/** `align._구간읽기` — 열 i 의 [y0, y1) 만 따로 나눠 읽기. {합, n, 글, 확} · 못 읽으면 null */
async function 구간읽기(모델, geo, i, y0, y1, span) {
  const x0 = geo.crop_cols[i][0], x1 = geo.crop_cols[i][1], sm = geo.sm[i];
  const r = (y1 - y0 >= geo.pitch * 0.6) ? 잉크범위(sm, y0, y1, geo.pitch * 1.5) : null;
  if (r === null || r[1] - r[0] < geo.pitch * 0.6) return { 합: 0.0, n: 0, 글: [], 확: [], 상: [] };
  y0 = r[0]; y1 = r[1];
  const cands = 자를후보(sm, y0, y1, geo.pitch);
  const est = Math.max(1, 반올림((y1 - y0) / geo.pitch));
  let best = null;
  for (let n = Math.max(1, est - span); n <= est + span; n++) {
    let cuts = 열가르기(sm, y0, y1, n, cands).자리;
    if (!cuts) {                       // 골짜기가 모자라면 고르게 — 파이썬과 같게
      cuts = [];
      for (let k = 0; k <= n; k++) cuts.push(자름(y0 + (y1 - y0) * k / n));
    }
    const bx = [];
    for (let k = 0; k + 1 < cuts.length; k++) bx.push([x0, cuts[k], x1, cuts[k + 1]]);
    const 읽 = await 모델.읽기(geo.그림, bx);
    let s = 0;
    for (let j = 0; j < bx.length; j++) s += Math.log(Math.max(읽.확신[j], 1e-6));
    if (best === null || s / bx.length > best.합 / best.n) {
      const 글 = [];
      for (let j = 0; j < n; j++) 글.push(모델.글자(읽.초[j], 읽.중[j], 읽.종[j]));
      best = { 합: s, n: n, 글: 글, 확: Array.from(읽.확신), 상: bx };
    }
  }
  return best;
}

/**
 * `align.큰제목읽기` — 두 열에 걸친 큰 활자 편 제목(시편촬요 「뎨팔편」)을 넓은 칸으로 다시 읽기. 열들을 제자리에서 고침
 * ⚠ 차례: 큰 제목 → 오른쪽 열 나머지 → 왼쪽 열 나머지. 열 점수는 그대로(가장자리다듬기 판단을 안 바꾸려고)
 */
async function 큰제목읽기(모델, geo, 열들, span) {
  const 점 = [];
  열들.forEach(function (o) { if (o !== null) 점.push(o.점수); });
  if (점.length < 5) return;
  const 가운데 = 중앙값(점);
  const sp = geo.spans, cc = geo.crop_cols;
  let i = 0;
  while (i + 1 < 열들.length) {
    const a = 열들[i], b = 열들[i + 1];
    if (a === null || b === null || !sp[i] || !sp[i + 1] ||
        a.점수 > 가운데 - HEADING_LOW || b.점수 > 가운데 - HEADING_LOW) { i++; continue; }
    const X0 = Math.min(cc[i][0], cc[i + 1][0]), X1 = Math.max(cc[i][1], cc[i + 1][1]);
    const 바닥 = Math.max(sp[i][1], sp[i + 1][1]);
    const 합쳐 = new Float64Array(geo.sm[i].length);
    for (let y = 0; y < 합쳐.length; y++) 합쳐[y] = geo.sm[i][y] + geo.sm[i + 1][y];
    const r = 잉크범위(합쳐, Math.min(sp[i][0], sp[i + 1][0]), 바닥);
    if (r === null) { i++; continue; }
    const y0 = r[0];
    const 옛 = (a.점수 * a.칸수 + b.점수 * b.칸수) / Math.max(1, a.칸수 + b.칸수);
    let 최고 = null;
    for (let ki = 0; ki < HEADING_K.length; ki++) {
      const k = HEADING_K[ki];
      for (let hi = 0; hi < HEADING_H.length; hi++) {
        const h = geo.xpitch * HEADING_H[hi];
        const y1 = 자름(y0 + k * h);
        if (y1 >= 바닥) continue;
        const cuts = 열가르기(합쳐, y0, y1, k, 자를후보(합쳐, y0, y1, h)).자리;
        if (!cuts) continue;
        const bx = [];
        for (let j = 0; j + 1 < cuts.length; j++) bx.push([X0, cuts[j], X1, cuts[j + 1]]);
        const 읽 = await 모델.읽기(geo.그림, bx);
        const 제 = [];
        for (let j = 0; j < k; j++) 제.push(모델.글자(읽.초[j], 읽.중[j], 읽.종[j]));
        if (제.some(function (x) { return NOTCHAR_KEEP.indexOf(x) >= 0; })) continue;   // 광곽 세로줄
        let 합 = 0;
        for (let j = 0; j < k; j++) 합 += Math.log(Math.max(읽.확신[j], 1e-6));
        if (합 / k < Math.log(HEADING_CONF)) continue;              // 본문 글자 둘을 큰 글자 하나로
        const ra = await 구간읽기(모델, geo, i, y1, sp[i][1], span);
        const rb = await 구간읽기(모델, geo, i + 1, y1, sp[i + 1][1], span);
        if (ra === null || rb === null) continue;
        const v = (합 + ra.합 + rb.합) / (k + ra.n + rb.n);
        if (최고 === null || v > 최고.v) {
          최고 = { v: v, 글: 제.concat(ra.글), 확: Array.from(읽.확신).concat(ra.확), 글2: rb.글, 확2: rb.확,
                  상: bx.concat(ra.상), 상2: rb.상 };
        }
      }
    }
    if (최고 !== null && 최고.v > 옛 + HEADING_GAIN) {
      열들[i] = { 점수: a.점수, 글자: 최고.글, 확신: 최고.확, 칸수: a.칸수, 상자: 최고.상 };
      열들[i + 1] = { 점수: b.점수, 글자: 최고.글2, 확신: 최고.확2, 칸수: b.칸수, 상자: 최고.상2 };
      i += 2;
    } else {
      i++;
    }
  }
}

let EDGE_DROP = 0.3, EDGE_MAX = 3, EDGE_OVERLAP = 0.6, EDGE_DROP_IN = 0.7;   // align.py 와 같은 값
let EDGE_BAR = 0.5;   // align.EDGE_BAR — 끝 열이 이 몫 넘게 `ㅣ` 면 광곽 세로줄로 보고 뗌 (null = 끔)
let NOTCHAR_CONF = 0.5, NOTCHAR_WIDTH = 0.5, NOTCHAR_ROW = 0.9, NOTCHAR_KEEP = ["ㅣ"];   // align.py 와 같은 값

/**
 * `align.가장자리다듬기` — 쪽 양 끝 열을 모델 확신도로 가림. 남길 열 번호를 차례대로.
 * ① 겹친 이웃(가운데가 자간×겹침 안)은 점수 높은 쪽만 — 같으면 앞의 것
 * ② 끝 쪽 이웃 사이에 광곽 세로줄이 있으면 가장 안쪽 줄 너머를 떼고, 그쪽 문턱은 안δ
 * ③ 끝에서부터, 가운데 열 중앙값보다 로그 확신이 문턱 넘게 낮은 열을 한쪽에 `최대` 개까지.
 *   다섯 열 아래로는 안 뗌
 */
function 가장자리다듬기(geo, 열들, δ, 최대, 겹침, 안δ) {
  if (δ === undefined) δ = EDGE_DROP;
  if (최대 === undefined) 최대 = EDGE_MAX;
  if (겹침 === undefined) 겹침 = EDGE_OVERLAP;
  if (안δ === undefined) 안δ = EDGE_DROP_IN;
  const 점 = function (i) { return 열들[i] === null ? -9.0 : 열들[i].점수; };
  const 가 = function (i) { return (geo.cols[i][0] + geo.cols[i][1]) / 2; };
  const 남 = [];
  for (let i = 0; i < 열들.length; i++) 남.push(i);
  let k = 0;
  while (k < 남.length - 1) {
    const a = 남[k], b = 남[k + 1];
    if (Math.abs(가(a) - 가(b)) < geo.xpitch * 겹침) 남.splice(점(a) >= 점(b) ? k + 1 : k, 1);
    else k++;
  }
  const 안 = [];
  for (let t = 2; t < 남.length - 2; t++) if (열들[남[t]] !== null) 안.push(열들[남[t]].점수);
  const 기준 = 안.length ? 중앙값(안) : -1.0;

  // 광곽 세로줄 — 양쪽마다 가장 안쪽 줄을 찾아 그 너머를 뗀다
  const 속 = [];
  for (let t = 2; t < 남.length - 2; t++) if (geo.spans[남[t]]) 속.push(geo.spans[남[t]]);
  let d앞 = δ, d뒤 = δ;
  if (속.length && 남.length > 4) {
    let T = Infinity, B = -Infinity;
    속.forEach(function (s) { T = Math.min(T, s[0]); B = Math.max(B, s[1]); });
    const 줄 = function (i, j) { return 세로줄있나(geo.그림, 가(i), 가(j), T, B); };
    for (let t = Math.min(최대, 남.length - 5); t > 0; t--) {          // 앞(오른쪽) 끝
      if (줄(남[t], 남[t - 1])) { 남.splice(0, t); d앞 = 안δ; break; }
    }
    for (let t = Math.min(최대, 남.length - 5); t > 0; t--) {          // 뒤(왼쪽) 끝
      const n = 남.length;
      if (줄(남[n - 1 - t], 남[n - t])) { 남.splice(n - t, t); d뒤 = 안δ; break; }
    }
  }

  // ⚠ 광곽 세로줄을 한 열 통째 `ㅣ` 로 자신 있게 읽으면 확신으로는 못 뗌 (align.py 의 `막대`)
  const 막대 = function (i) {
    if (EDGE_BAR === null || 열들[i] === null || 열들[i].글자.length === 0) return false;
    let n = 0;
    for (const 자 of 열들[i].글자) if (자 === "ㅣ") n++;
    return n > EDGE_BAR * 열들[i].글자.length;
  };
  const 나쁨 = function (i, d) { return 열들[i] === null || 열들[i].점수 < 기준 - d || 막대(i); };
  for (let t = 0; t < 최대; t++) {
    if (남.length > 4 && 나쁨(남[0], d앞)) 남.shift(); else break;
  }
  for (let t = 0; t < 최대; t++) {
    if (남.length > 4 && 나쁨(남[남.length - 1], d뒤)) 남.pop(); else break;
  }
  return 남;
}

// ════════════════════════════════════════════════════════════════════
//  ocr.py — 상자를 오려 64px 로
// ════════════════════════════════════════════════════════════════════

/**
 * ★ Pillow `Resample.c` 그대로(10.2) — `precompute_coeffs` + `normalize_coeffs_8bpc`. 8비트 그림은 가중치를
 * 2^22 배 정수로 바꿔 더한다(PRECISION_BITS 22 · 처음값 2^21 · 오른쪽 옮김 · 0~255 자름). `오리기` ·
 * `경계띠` 가 씀. ⚠ 실수 계산으로 흉내 내면 픽셀이 가끔 1/255 달라 경계 검출기의 자를 후보가 바뀜.
 */
function 정수계수(n_in, n_out) {
  const scale = n_in / n_out;
  let filterscale = scale;
  if (filterscale < 1.0) filterscale = 1.0;
  const support = 2.0 * filterscale;                 // bicubic support 2
  const out = [];
  for (let xx = 0; xx < n_out; xx++) {
    const center = (xx + 0.5) * scale;
    let ww = 0.0;
    const ss = 1.0 / filterscale;
    let xmin = Math.trunc(center - support + 0.5);
    if (xmin < 0) xmin = 0;
    let xmax = Math.trunc(center + support + 0.5);
    if (xmax > n_in) xmax = n_in;
    xmax -= xmin;
    const k = new Float64Array(Math.max(0, xmax));
    for (let x = 0; x < xmax; x++) {
      let t = (x + xmin - center + 0.5) * ss;
      if (t < 0.0) t = -t;
      let w;
      if (t < 1.0) w = ((-0.5 + 2.0) * t - (-0.5 + 3.0)) * t * t + 1;
      else if (t < 2.0) w = (((t - 5) * t + 8) * t - 4) * -0.5;
      else w = 0.0;
      k[x] = w; ww += w;
    }
    const ki = new Float64Array(Math.max(0, xmax));
    for (let x = 0; x < xmax; x++) {
      const v = ww !== 0.0 ? k[x] / ww : k[x];
      ki[x] = v < 0 ? Math.trunc(-0.5 + v * 4194304) : Math.trunc(0.5 + v * 4194304);   // (int) 은 0 쪽으로 자름
    }
    out.push({ 처음: xmin, 무게: ki });
  }
  return out;
}

/** Pillow `clip8` — ss >> 22 를 0~255 로. */
function 자름8(ss) {
  if (ss >= 1073741824) return 255;                  // (1 << 22) << 8
  if (ss <= 0) return 0;
  return Math.floor(ss / 4194304);
}

const _정수계수보관 = new Map();
function 정수계수표(n_in, n_out) {
  const key = n_in + "x" + n_out;
  let v = _정수계수보관.get(key);
  if (!v) { v = 정수계수(n_in, n_out); _정수계수보관.set(key, v); }
  return v;
}

/** 8비트 회색 그림(src, w×h, 0~255 정수) → ow×oh — Pillow 와 픽셀까지 같게(가로 패스 뒤 세로 패스). 반환: 0~255 정수 배열 */
function 줄이기8(src, w, h, ow, oh) {
  const kx = 정수계수표(w, ow), ky = 정수계수표(h, oh);
  const 가로 = new Uint8Array(h * ow);
  for (let y = 0; y < h; y++) {
    const so = y * w, to = y * ow;
    for (let j = 0; j < ow; j++) {
      const k = kx[j], wt = k.무게;
      let ss = 2097152;                               // 1 << 21
      for (let t = 0; t < wt.length; t++) ss += src[so + k.처음 + t] * wt[t];
      가로[to + j] = 자름8(ss);
    }
  }
  const out = new Uint8Array(oh * ow);
  for (let i = 0; i < oh; i++) {
    const k = ky[i], wt = k.무게, to = i * ow;
    for (let j = 0; j < ow; j++) {
      let ss = 2097152;
      for (let t = 0; t < wt.length; t++) ss += 가로[(k.처음 + t) * ow + j] * wt[t];
      out[to + j] = 자름8(ss);
    }
  }
  return out;
}

/**
 * 상자 하나를 오려 `size × size` 회색조로 — `ocr.Model.crops` 와 짝.
 * ⚠ ① 그림 밖은 0(검정)으로 — PIL 과 같게 (흰색이면 결과가 달라짐)
 * ⚠ ② 가로 패스 결과를 uint8 로 담음(반올림 + 자름) — 빠뜨리면 1순위 글자가 갈림
 */
function 오리기(g, b, size) {
  const x0 = b[0] - 4, y0 = b[1] - 4, x1 = b[2] + 4, y1 = b[3] + 4;
  const cw = x1 - x0, ch = y1 - y0;
  const src = new Float64Array(cw * ch);            // ① 밖은 0 (검정)
  const W = g.너비, H = g.높이, v = g.값;
  for (let y = 0; y < ch; y++) {
    const sy = y0 + y;
    if (sy < 0 || sy >= H) continue;
    const so = sy * W, po = y * cw;
    for (let x = 0; x < cw; x++) {
      const sx = x0 + x;
      if (sx < 0 || sx >= W) continue;
      src[po + x] = v[so + sx];
    }
  }
  // ② Pillow 와 같은 정수 계산으로 줄임(가로 패스를 uint8 로 담는 것 포함) — `줄이기8`
  const px = 줄이기8(src, cw, ch, size, size);
  const out = new Float32Array(size * size);
  for (let i = 0; i < size; i++) {
    const to = i * size;
    for (let j = 0; j < size; j++) {
      const s = px[to + j];
      out[to + j] = (s / 255 - 0.5) / 0.5;           // ocr.py 와 같은 정규화
    }
  }
  return out;
}

/**
 * 학습된 CNN 한 벌. `ocr.Model` 과 짝입니다.
 * `만들기(설정, onnx세션)` 로 만들고 `읽기(그림, 상자들)` 로 씁니다.
 */
function 모델만들기(설정, 세션, ort, 경계세션) {
  const size = 설정.그림크기;
  return {
    설정: 설정,
    /** `경계검출.검출기.경계확률` — 열 하나 → 쪽 높이 길이의 경계 확률(Float64Array). 경계 세션이 없으면 null. */
    경계: 경계세션 ? async function (g, x0, x1) {
      const b = 경계띠(g, x0, x1);
      const r = await 경계세션.run({ x: new ort.Tensor("float32", b.값, [1, 1, b.높이, 경계폭]) });
      const z = r.z.data, n = b.높이, H = g.높이;
      const p = new Float64Array(n);
      for (let k = 0; k < n; k++) p[k] = 1 / (1 + Math.exp(-z[k]));
      const out = new Float64Array(H);
      for (let y = 0; y < H; y++) {                    // np.interp(y × 배율, 0..n−1, p)
        const u = y * b.배율;
        if (u <= 0) { out[y] = p[0]; continue; }
        if (u >= n - 1) { out[y] = p[n - 1]; continue; }
        const lo = Math.floor(u), f = u - lo;
        out[y] = p[lo] * (1 - f) + p[lo + 1] * f;
      }
      return out;
    } : null,
    글자: function (l, v, t) {
      const s = 설정.초성[l] + 설정.중성[v] + 설정.종성[t];
      // 채움 문자로 실은 ㅣ · ○ 를 제 글자로 (`wikitext.특수표시` 와 같게)
      return s === "ᅟᅵ" ? "ㅣ" : (s === "○ᅠ" ? "○" : s);
    },
    /** 상자들 → {초, 중, 종, 확신}. 확신은 세 머리 최댓값의 **최솟값**. */
    읽기: async function (g, boxes, 뭉치, 알림) {
      뭉치 = 뭉치 || 256;
      const n = boxes.length;
      const 초 = new Int32Array(n), 중 = new Int32Array(n);
      const 종 = new Int32Array(n), 확신 = new Float64Array(n);
      if (!n) return { 초: 초, 중: 중, 종: 종, 확신: 확신 };
      const nL = 설정.초성.length, nV = 설정.중성.length, nT = 설정.종성.length;
      // ★ 같은 상자는 한 번만(2026-09-29) — 칸수를 est±폭으로 여러 번 자르면 같은 자리 상자가 되풀이됨
      //   (서로 다른 것 22~25%). WASM 은 뭉치가 달라도 상자마다 답이 같음 — 파이썬(CUDA)은 아님(1e-4)
      const 자리 = new Int32Array(n), 읽을 = [];
      if (this.중복빼기 === false) {
        for (let i = 0; i < n; i++) { 자리[i] = i; 읽을.push(boxes[i]); }
      } else {
        const 본 = new Map();
        for (let i = 0; i < n; i++) {
          const b = boxes[i], 열쇠 = b[0] + "," + b[1] + "," + b[2] + "," + b[3];
          let j = 본.get(열쇠);
          if (j === undefined) { j = 읽을.length; 본.set(열쇠, j); 읽을.push(b); }
          자리[i] = j;
        }
      }
      const u = 읽을.length;
      const 초u = new Int32Array(u), 중u = new Int32Array(u);
      const 종u = new Int32Array(u), 확신u = new Float64Array(u);
      for (let s = 0; s < u; s += 뭉치) {
        const m = Math.min(뭉치, u - s);
        const buf = new Float32Array(m * size * size);
        for (let k = 0; k < m; k++) buf.set(오리기(g, 읽을[s + k], size), k * size * size);
        const r = await 세션.run({ x: new ort.Tensor("float32", buf, [m, 1, size, size]) });
        const L = r.L.data, V = r.V.data, T = r.T.data;
        for (let k = 0; k < m; k++) {
          const a = 최대소프트맥스(L, k * nL, nL);
          const b = 최대소프트맥스(V, k * nV, nV);
          const c = 최대소프트맥스(T, k * nT, nT);
          초u[s + k] = a.자리; 중u[s + k] = b.자리; 종u[s + k] = c.자리;
          확신u[s + k] = Math.min(a.값, Math.min(b.값, c.값));
        }
        if (알림) 알림(Math.min(s + m, u), u);
      }
      for (let i = 0; i < n; i++) {
        const j = 자리[i];
        초[i] = 초u[j]; 중[i] = 중u[j]; 종[i] = 종u[j]; 확신[i] = 확신u[j];
      }
      return { 초: 초, 중: 중, 종: 종, 확신: 확신 };
    },
  };
}

/** 소프트맥스의 최댓값과 그 자리. (넘침을 막으려고 최댓값을 뺍니다.) */
function 최대소프트맥스(a, off, n) {
  let mx = -Infinity, 자리 = 0;
  for (let i = 0; i < n; i++) if (a[off + i] > mx) { mx = a[off + i]; 자리 = i; }
  let s = 0;
  for (let i = 0; i < n; i++) s += Math.exp(a[off + i] - mx);
  return { 자리: 자리, 값: 1 / s };
}

// ════════════════════════════════════════════════════════════════════
//  step4_read.py
// ════════════════════════════════════════════════════════════════════

const 안쪽 = "⟪", 바깥 = "⟫";     // ⟪ ⟫
let MARK = 0.9;                   // step4_read.표시문턱 — 설정.json 의 표시문턱으로 덮음

/** `step4_read.확신표시` — 확신 낮은 글자를 `⟪…⟫` 로 감쌈 (기본 문턱 MARK) */
function 확신표시(글자, 확신, 문턱, 빈) {
  if (문턱 === undefined) 문턱 = MARK;
  const 조각 = [];
  let 셀 = 0, 켬 = false;
  for (let i = 0; i < 글자.length; i++) {
    const 낮 = 확신[i] < 문턱;
    if (낮 && !켬) { 조각.push(안쪽); 켬 = true; }
    else if (!낮 && 켬) { 조각.push(바깥); 켬 = false; }
    조각.push(글자[i]);
    if (낮) 셀++;
    if (빈 && 빈[i]) {                 // 띄어쓰기 — ⟪⟫ 는 빈칸을 감싸지 않음
      if (켬) { 조각.push(바깥); 켬 = false; }
      조각.push(" ");
    }
  }
  if (켬) 조각.push(바깥);
  return { 글월: 조각.join(""), 표시: 셀 };
}

/**
 * `step4_read.줄글월` — 열마다 한 줄로. 원문의 줄바꿈을 살린다.
 * 표시(⟪⟫)는 줄마다 따로 붙인다(줄을 넘어가면 지우기 번거로움).
 * ⚠ 위키문헌에서 줄바꿈 하나는 띄어쓰기로 보임 — 저장 전에 줄 잇기.
 */
function 줄글월(줄들, 문턱) {
  const 글 = [], 표 = [];
  let 셀 = 0;
  줄들.forEach(function (줄) {
    const t = 확신표시(줄.글자, 줄.확신, 문턱, 줄.빈);
    글.push(줄.글자.map(function (c, k) { return c + (줄.빈 && 줄.빈[k] ? " " : ""); }).join(""));
    표.push(t.글월); 셀 += t.표시;
  });
  return { 글월: 글.join("\n"), 교정용: 표.join("\n"), 표시: 셀 };
}

// ════════════════════════════════════════════════════════════════════
//  바깥에서 쓰는 것
// ════════════════════════════════════════════════════════════════════

const API = {
  // 파이썬과 대조할 때 쓰는 속살
  _속: {
    반올림: 반올림, 중앙값: 중앙값, 백분위: 백분위, 고르기: 고르기,
    열잉크: 열잉크, 잉크무늬: 잉크무늬, 광곽합의: 광곽합의,
    글자구간: 글자구간, 단봉우리: 단봉우리, 단가름: 단가름,
    고랑곡선: 고랑곡선, 줄덩이: 줄덩이, 가름판기하: 가름판기하,
    자를후보: 자를후보, 열가르기: 열가르기, 오리기: 오리기,
  },
  그림만들기: 그림만들기,
  그림읽기: 그림읽기,
  열찾기: 열찾기,
  광곽: 광곽,
  쪽기하: 쪽기하,
  쪽건강: 쪽건강,
  // 문헌(파일) 판형 판정 — 소도구가 처음 보는 파일에 부름
  단측정: 단측정,
  가름줄측정: 가름줄측정,
  가름줄정하기: 가름줄정하기,
  판형정하기: 판형정하기,
  테두리열버리기: 테두리열버리기,
  가장자리후보: 가장자리후보,
  기하: 기하,
  자를계획: 자를계획,
  경계프로파일: 경계프로파일,
  줄이기8: 줄이기8,
  열마다읽기: 열마다읽기,
  가장자리다듬기: 가장자리다듬기,
  쪽읽기: 쪽읽기,
  모델만들기: 모델만들기,
  확신표시: 확신표시,
  줄글월: 줄글월,
  빈틈값: 빈틈값,
  빈틈가르기: 빈틈가르기,
  띄울자리: 띄울자리,

  /** `설정.json` 넣기 — 상수들이 파이썬에서 그대로 옴 */
  설정넣기: function (s) {
    INK = s.잉크문턱; GLYPH = s.글자줄비율;
    YX_RATIO = s.기본자간비; TEDURI = s.테두리배수;
    if (s.가장자리문턱 !== undefined) {
      EDGE_DROP = s.가장자리문턱; EDGE_MAX = s.가장자리최대; EDGE_OVERLAP = s.가장자리겹침;
    }
    if (s.가장자리막대 !== undefined) EDGE_BAR = s.가장자리막대;
    if (s.가장자리안문턱 !== undefined) {
      EDGE_DROP_IN = s.가장자리안문턱;
      FRAME_SEG = s.세로줄토막; FRAME_FILL = s.세로줄덮개; FRAME_AGREE = s.세로줄합의;
    }
    if (s.끝열옮김 !== undefined) {
      EDGE_MOVE = s.끝열옮김; EDGE_MOVE_GAP = s.끝열옮김거리;
      EDGE_MOVE_MIN = s.끝열옮김이웃; EDGE_MOVE_INK = s.끝열옮김잉크;
    }
    if (s.빈칸확신 !== undefined) {
      NOTCHAR_CONF = s.빈칸확신; NOTCHAR_WIDTH = s.빈칸폭; NOTCHAR_ROW = s.빈칸가로;
      if (s.빈칸살림 !== undefined) NOTCHAR_KEEP = s.빈칸살림;
    }
    if (s.표시문턱 !== undefined) MARK = s.표시문턱;
    if (s.경계 !== undefined) { CUT_LEARN = s.경계; CUT_MIX = s.경계섞기; 경계폭 = s.경계폭; CUT_CLIP = s.경계자름 !== undefined ? s.경계자름 : 0.0; CUT_ROUND = s.경계반올림 || 10000; }
    if (s.큰제목 !== undefined) {
      HEADING = s.큰제목; HEADING_LOW = s.큰제목낮음; HEADING_GAIN = s.큰제목이득; HEADING_CONF = s.큰제목확신;
      HEADING_INK = s.큰제목잉크; HEADING_K = s.큰제목글자수; HEADING_H = s.큰제목높이;
    }
    if (s.열광곽 !== undefined) {
      FRAME_LOCAL = s.열광곽; FRAME_LOCAL_FILL = s.열광곽잉크; FRAME_LOCAL_REACH = s.열광곽거리; FRAME_LOCAL_EDGE = s.열광곽가장자리;
    }
    if (s.구간이어 !== undefined) {
      SPAN_EXTEND = s.구간이어; SPAN_LOW = s.구간이어잉크; SPAN_REACH = s.구간이어거리; SPAN_GAP = s.구간이어빈줄;
    }
    if (s.띄움 !== undefined) {
      SPACE = s.띄움; SPACE_ROW = s.띄움행; SPACE_ETA = s.띄움갈림; SPACE_LOW = s.띄움아래;
      SPACE_FRAC = s.띄움몫; SPACE_CLIP = s.띄움자름; SPACE_BEFORE = s.띄움앞; SPACE_AFTER = s.띄움뒤;
    } else {
      SPACE = false;                  // 표가 없는 옛 설정.json 이면 띄우지 않음
    }
    API.설정 = s;
    return s;
  },

  /**
   * 쪽 하나를 처음부터 끝까지. `읽기.py` 의 한 쪽 처리와 같은 차례입니다.
   *
   *   const r = await 옛한글읽기.한쪽(모델, 그림, "시편촬요_1898년");
   *   r.판정.등급 · r.글월(붙여넣을 것) · r.교정용(⟪⟫ 표시)
   */
  한쪽: async function (모델, g, 문헌, 옵션) {
    옵션 = 옵션 || {};
      // `옵션.문헌설정` — 처음 보는 파일에 소도구가 살펴 준 것
    const s = 옵션.문헌설정
      || (API.설정 && API.설정.문헌 && API.설정.문헌[문헌]) || {};
    const geo = 기하(g, s, true);
    const 건강 = 쪽건강(geo, s.판짜임);
    if (!geo) return { 판정: 건강, 글월: "", 교정용: "", 확신: [], 상자수: 0 };
    const r = await 쪽읽기(모델, geo, 옵션.폭 === undefined ? 3 : 옵션.폭);
    const 표 = 줄글월(r.줄들, 옵션.표시문턱);
    return {
      판정: 건강, 기하: geo,
      글월: 표.글월, 교정용: 표.교정용,     // 둘 다 열마다 한 줄
      확신: r.확신, 표시: 표.표시, 상자수: r.상자수,
      표시비: r.글자.length ? 표.표시 / r.글자.length : 0,
    };
  },
};

전역.옛한글읽기 = API;
if (typeof module !== "undefined" && module.exports) module.exports = API;
})(typeof self !== "undefined" ? self : this);
