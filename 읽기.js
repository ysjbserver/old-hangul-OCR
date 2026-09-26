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

/** `scan.ink_profile` — 뒤 계산이 모두 이것을 돌려쓴다. */
function 잉크무늬(g, cols) {
  return cols.map(function (c) { return 열잉크(g, c[0], c[1]); });
}

/**
 * `scan.spans_between` — T~B 안에서 열마다 글자가 시작하고 끝나는 y.
 * 뒷면 비침·계선 때문에 열 폭의 GLYPH 이상이 잉크인 줄만 글자 줄로 봄
 */
function 글자구간(prof, cols, T, B, pitch) {
  const spans = cols.map(function (c, i) {
    const p = prof[i], need = (c[1] - c[0]) * GLYPH;
    let a = -1, b = -1;
    for (let y = T; y < B; y++) if (p[y] > need) { if (a < 0) a = y; b = y; }
    return a < 0 ? null : [a, b + 1];
  });
  const real = spans.filter(function (s) { return s; });
  if (!real.length) return null;
  let Emax = -Infinity;
  for (let i = 0; i < real.length; i++) if (real[i][1] > Emax) Emax = real[i][1];
  return spans.map(function (s) {
    if (!s) return null;
    let a = s[0], b = s[1];
    if (a - T < pitch * 0.5) a = T;             // 첫 글자가 흐려도 위에서 시작
    if (Emax - b < pitch * 0.6) b = Emax;       // 끝도 마찬가지
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
    spans = 글자구간(prof, cols0, T, B, pitch);
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
function 자를계획(geo, centers, span, 빈열허용) {
  const 계획 = [], 상자 = [];
  for (let i = 0; i < geo.crop_cols.length; i++) {
    const x0 = geo.crop_cols[i][0], x1 = geo.crop_cols[i][1];
    const opts = [];
    const sp = geo.spans[i];
    if (sp) {
      const y0 = sp[0], y1 = sp[1];
      const cands = 자를후보(geo.sm[i], y0, y1, geo.pitch);
      for (let n = Math.max(1, centers[i] - span); n <= centers[i] + span; n++) {
        const r = 열가르기(geo.sm[i], y0, y1, n, cands);
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
  return { 글자: out, 확신: conf, 줄들: 줄들, 상자수: r.상자수, 남긴열: 남 };
}

/**
 * `align.열마다읽기` — 열마다 가장 자신 있는 칸수로 읽는다(`쪽읽기` 의 앞 절반).
 * 열들[i] = {점수(로그 확신 평균), 글자, 확신} — 읽을 것이 없는 열은 null.
 */
async function 열마다읽기(모델, geo, span) {
  if (span === undefined) span = 3;
  const bp = 자를계획(geo, geo.est, span, false);
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
    const 글 = [], 확 = [];
    for (let j = 0; j < best.개수; j++) {
      const c = cf[best.시작 + j];
      const 자 = 모델.글자(pL[best.시작 + j], pV[best.시작 + j], pT[best.시작 + j]);
      if (c < NOTCHAR_CONF && NOTCHAR_KEEP.indexOf(자) < 0) {
        const m = 칸모양(geo.그림, best.상자들[j]);
        if (m[0] < NOTCHAR_WIDTH || m[1] >= NOTCHAR_ROW) continue;
      }
      글.push(자);
      확.push(c);
    }
    열들.push({ 점수: bestv, 글자: 글, 확신: 확 });
  }
  return { 열들: 열들, 상자수: bp.상자.length };
}

let EDGE_DROP = 0.3, EDGE_MAX = 3, EDGE_OVERLAP = 0.6, EDGE_DROP_IN = 0.7;   // align.py 와 같은 값
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

  const 나쁨 = function (i, d) { return 열들[i] === null || 열들[i].점수 < 기준 - d; };
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
 * `PIL.Image.resize` 의 BICUBIC 계수 — 파이썬과 똑같이.
 * a = −0.5 · support 2 · 축소 때 커널을 배율만큼 늘림 · 합이 1 이 되게 나눔
 */
function 접기계수(n_in, n_out) {
  const scale = n_in / n_out;
  const fscale = Math.max(scale, 1.0);
  const sup = 2.0 * fscale;
  const out = [];
  for (let xx = 0; xx < n_out; xx++) {
    const center = (xx + 0.5) * scale;
    const xmin = Math.max(0, Math.floor(center - sup + 0.5));
    const xmax = Math.min(n_in, Math.ceil(center + sup + 0.5));
    const w = new Float64Array(Math.max(0, xmax - xmin));
    let s = 0;
    for (let x = xmin; x < xmax; x++) {
      const t = Math.abs((x - center + 0.5) / fscale);
      let v = 0;
      if (t < 1) v = ((-0.5 + 2) * t - (-0.5 + 3)) * t * t + 1;
      else if (t < 2) v = ((t - 5) * t + 8) * t * (-0.5) - 4 * (-0.5);
      w[x - xmin] = v; s += v;
    }
    if (s) for (let i = 0; i < w.length; i++) w[i] /= s;
    out.push({ 처음: xmin, 무게: w });
  }
  return out;
}

const _계수보관 = new Map();
function 계수(n_in, n_out) {
  const key = n_in + "x" + n_out;
  let v = _계수보관.get(key);
  if (!v) { v = 접기계수(n_in, n_out); _계수보관.set(key, v); }
  return v;
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
  const kx = 계수(cw, size), ky = 계수(ch, size);
  const 가로 = new Float64Array(ch * size);
  for (let y = 0; y < ch; y++) {
    const so = y * cw, to = y * size;
    for (let j = 0; j < size; j++) {
      const k = kx[j], w = k.무게;
      let s = 0;
      for (let t = 0; t < w.length; t++) s += src[so + k.처음 + t] * w[t];
      // ② 가로 패스 결과를 uint8 로
      s = Math.round(s);
      가로[to + j] = s < 0 ? 0 : (s > 255 ? 255 : s);
    }
  }
  const out = new Float32Array(size * size);
  for (let i = 0; i < size; i++) {
    const k = ky[i], w = k.무게, to = i * size;
    for (let j = 0; j < size; j++) {
      let s = 0;
      for (let t = 0; t < w.length; t++) s += 가로[(k.처음 + t) * size + j] * w[t];
      s = Math.round(s);
      s = s < 0 ? 0 : (s > 255 ? 255 : s);
      out[to + j] = (s / 255 - 0.5) / 0.5;           // ocr.py 와 같은 정규화
    }
  }
  return out;
}

/**
 * 학습된 CNN 한 벌. `ocr.Model` 과 짝입니다.
 * `만들기(설정, onnx세션)` 로 만들고 `읽기(그림, 상자들)` 로 씁니다.
 */
function 모델만들기(설정, 세션, ort) {
  const size = 설정.그림크기;
  return {
    설정: 설정,
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
      for (let s = 0; s < n; s += 뭉치) {
        const m = Math.min(뭉치, n - s);
        const buf = new Float32Array(m * size * size);
        for (let k = 0; k < m; k++) buf.set(오리기(g, boxes[s + k], size), k * size * size);
        const r = await 세션.run({ x: new ort.Tensor("float32", buf, [m, 1, size, size]) });
        const L = r.L.data, V = r.V.data, T = r.T.data;
        for (let k = 0; k < m; k++) {
          const a = 최대소프트맥스(L, k * nL, nL);
          const b = 최대소프트맥스(V, k * nV, nV);
          const c = 최대소프트맥스(T, k * nT, nT);
          초[s + k] = a.자리; 중[s + k] = b.자리; 종[s + k] = c.자리;
          확신[s + k] = Math.min(a.값, Math.min(b.값, c.값));
        }
        if (알림) 알림(Math.min(s + m, n), n);
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

/** `step4_read.확신표시` — 확신 낮은 글자를 `⟪…⟫` 로 감쌈 (기본 문턱 0.7) */
function 확신표시(글자, 확신, 문턱) {
  if (문턱 === undefined) 문턱 = 0.7;
  const 조각 = [];
  let 셀 = 0, 켬 = false;
  for (let i = 0; i < 글자.length; i++) {
    const 낮 = 확신[i] < 문턱;
    if (낮 && !켬) { 조각.push(안쪽); 켬 = true; }
    else if (!낮 && 켬) { 조각.push(바깥); 켬 = false; }
    조각.push(글자[i]);
    if (낮) 셀++;
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
    const t = 확신표시(줄.글자, 줄.확신, 문턱);
    글.push(줄.글자.join("")); 표.push(t.글월); 셀 += t.표시;
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
    자를후보: 자를후보, 열가르기: 열가르기, 접기계수: 접기계수, 오리기: 오리기,
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
  열마다읽기: 열마다읽기,
  가장자리다듬기: 가장자리다듬기,
  쪽읽기: 쪽읽기,
  모델만들기: 모델만들기,
  확신표시: 확신표시,
  줄글월: 줄글월,

  /** `설정.json` 넣기 — 상수들이 파이썬에서 그대로 옴 */
  설정넣기: function (s) {
    INK = s.잉크문턱; GLYPH = s.글자줄비율;
    YX_RATIO = s.기본자간비; TEDURI = s.테두리배수;
    if (s.가장자리문턱 !== undefined) {
      EDGE_DROP = s.가장자리문턱; EDGE_MAX = s.가장자리최대; EDGE_OVERLAP = s.가장자리겹침;
    }
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
