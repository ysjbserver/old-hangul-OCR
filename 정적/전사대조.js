/*
 * 전사대조 — 위키문헌 '페이지:' 편집 창에서 **이미 전사된 글**을 그 쪽 스캔과 맞대어,
 * 전사문이 틀렸을 만한 자리를 편집 상자 안에 칠하는 소도구. OCR 소도구와 **따로 켭니다**:
 *
 *   window.옛한글OCR자료 = "https://cdn.jsdelivr.net/gh/ysjbserver/old-hangul-OCR@…/";
 *   mw.loader.load(window.옛한글OCR자료 + "소도구.js");      ← OCR (있던 줄)
 *   mw.loader.load(window.옛한글OCR자료 + "전사대조.js");    ← 이 줄을 더하면 켜짐
 *
 * 셈은 모두 브라우저 안에서(모델 · `읽기.js` 는 OCR 과 같은 것). 저장은 하지 않음 — 사람이 확인하고 누름.
 * 파이썬 짝: `전사대조/대조.py`(인쇄글자 · 맞대기 · 한쪽) · `부품/align.py`(to_text) · `부품/wikitext.py`(printed_text)
 */
(function (전역) {
"use strict";

// ════════════════════════════════════════════════════════════════════
//  셈 — 파이썬 `전사대조/대조.py` 를 옮긴 것
// ════════════════════════════════════════════════════════════════════

// `대조.py` 의 문턱 (재기.py 로 고름)
const P_TR_MAX = 0.05, TOP_MIN = 0.80, 일치문턱 = 0.75, 다시볼일치 = 0.9, 열문턱 = 0.75, 받침잘림높이 = 0.8;
const MIN_LETTERS = 50;                                  // page.MIN_LETTERS
// `align.py` 의 무게
const W_L = 0.40, W_V = 0.40, W_T = 0.20, W_ALL = 0.20, UNKNOWN = 0.45;
const W_CONF = 0.20, W_PITCH = 22.0, PITCH_CAP = 0.20, W_CUT = 0.4, EMPTY_PEN = 6.0;

// ── 위키 원문 → 인쇄된 글자 + 원문 자리 (`대조.인쇄글자` = `wikitext.printed_text`) ──
// ⚠ 틀 표(DROP · LAST · JOIN · FIRST)는 `wikitext.py` 를 옮겨 적은 것 — 그쪽을 고치면 여기도.
const DROP = new Set(["절", "marginNote", "nop", "upe", "여백", "점선 요약", "목차용 점선",
  "references", "reflist", "pagequality", "-"]);
const LAST = new Set(["왼쪽 여백"]), JOIN = new Set(["분주"]);
const FIRST = new Set(["u", "du", "wu", "물결밑줄", "밑줄", "더크게", "더더크게", "크게", "작게",
  "가운데", "복원", "SIC", "sc", "글자크기"]);
const 오식틀 = new Set(["SIC"]);
const 큰틀 = new Set(["크게", "더크게", "더더크게"]);   // `대조.큰틀` — 큰 활자, '빼고 맞대기' 후보
// 파이썬 `\s` 와 같은 빈칸(자바스크립트 `\s` 와 조금 다름 — \x1c-\x1f · \x85 가 있고 ﻿ 가 없음)
const S = "\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const 속성 = new RegExp("^[" + S + "]*[A-Za-z-]+[" + S + "]*=");
const 다듬기 = function (s) { return s.replace(new RegExp("^[" + S + "]+|[" + S + "]+$", "g"), ""); };
const 제목꼴 = new RegExp("(?<![^\\n])[" + S + "]*=+[" + S + "]*([^\\n]*?)[" + S + "]*=+[" + S + "]*(?![^\\n])", "gd");
const 빈칸꼴 = new RegExp("[" + S + "\\u200b]+", "g");

function 틀남길것(이름, 인자, 큰빼기) {
  if (DROP.has(이름) || 이름.indexOf("왼쪽 여백/") === 0 || (큰빼기 && 큰틀.has(이름))) return [];
  if (JOIN.has(이름)) return 인자.slice(0, 2);
  if (LAST.has(이름)) return 인자.slice(-1);
  if (FIRST.has(이름)) return 인자.slice(0, 1);
  return [];
}

/** 맞음마다 그 자리를 `남길것(m)` 이 돌려준 구간들로 바꿈 — 남는 글자는 원문 자리(pos)를 그대로 데려감 */
function 걷어내기(t, pos, 맞음들, 남길것) {
  const nt = [], npos = [];
  let p = 0;
  for (const m of 맞음들) {
    nt.push(t.slice(p, m.s));
    for (let k = p; k < m.s; k++) npos.push(pos[k]);
    for (const ab of 남길것(m)) {
      nt.push(t.slice(ab[0], ab[1]));
      for (let k = ab[0]; k < ab[1]; k++) npos.push(pos[k]);
    }
    p = m.e;
  }
  nt.push(t.slice(p));
  for (let k = p; k < t.length; k++) npos.push(pos[k]);
  return [nt.join(""), npos];
}

function 찾기(꼴, t) {
  const out = [];
  for (const m of t.matchAll(꼴)) {
    out.push({ s: m.index, e: m.index + m[0].length, 묶음: m.indices ? m.indices[1] : null });
  }
  return out;
}

/** `wikitext.표구간` — 표 문법 `{| … |}`: 칸 글자는 남기고 표시 · 속성만 걷음 */
function 표구간(t, 표) {
  if (!표) return [];
  const out = [];
  for (const m of t.matchAll(/(?<![^\n])[ \t]*(\{\||\|\}|\|-|\|\+|\||!)([^\n]*)(?![^\n])/gd)) {
    const a = m.index, b = a + m[0].length, s = m.indices[2][0], 표시 = m[1];
    if (표시 === "{|" || 표시 === "|-") { out.push({ s: a, e: b, 남길: [] }); continue; }
    if (표시 === "|}") { out.push({ s: a, e: s, 남길: [] }); continue; }
    const 칸들 = [];
    let p = s;
    for (const d of t.slice(s, b).matchAll(표시 === "!" ? /\|\||!!/g : /\|\|/g)) {
      칸들.push([p, s + d.index]); p = s + d.index + d[0].length;
    }
    칸들.push([p, b]);
    const 남길 = [];
    for (let [ca, cb] of 칸들) {
      const i = t.indexOf("|", ca);
      if (i >= 0 && i < cb && 속성.test(t.slice(ca, i))) ca = i + 1;
      남길.push([ca, cb]);
    }
    out.push({ s: a, e: b, 남길: 남길 });
  }
  return out;
}

/**
 * `대조.인쇄글자` — 위키 원문 → [[글자, 원문 시작, 원문 끝, {{SIC}} 안인가], …]
 * 글자는 `wikitext.letters(wikitext.printed_text(raw, 제목))` 와 같음. 자리는 자바스크립트 문자열 자리(UTF-16).
 */
function 인쇄글자(raw, 제목, 큰빼기) {
  let t = raw, pos = new Array(raw.length);
  for (let i = 0; i < raw.length; i++) pos[i] = i;
  const 오식 = new Set();
  const 표 = /(?<!\{)\{\|/.test(raw);
  [t, pos] = 걷어내기(t, pos, 찾기(/<noinclude>[\s\S]*?<\/noinclude>/g, t), function () { return []; });
  for (;;) {                                              // 안쪽 틀부터 하나씩
    const m = /\{\{([^{}]*)\}\}/.exec(t);
    if (!m) break;
    const s1 = m.index + 2, e1 = m.index + m[0].length - 2;
    const 조각 = [];
    let a = s1;
    for (let i = s1; i < e1; i++) if (t[i] === "|") { 조각.push([a, i]); a = i + 1; }
    조각.push([a, e1]);
    const 이름 = 다듬기(t.slice(조각[0][0], 조각[0][1]));
    const 인자 = 조각.slice(1).filter(function (ab) { return !속성.test(t.slice(ab[0], ab[1])); });
    const 남길 = 틀남길것(이름, 인자, 큰빼기);
    if (오식틀.has(이름)) for (const ab of 남길) for (let k = ab[0]; k < ab[1]; k++) 오식.add(pos[k]);
    [t, pos] = 걷어내기(t, pos, [{ s: m.index, e: m.index + m[0].length }], function () { return 남길; });
  }
  [t, pos] = 걷어내기(t, pos, 찾기(제목꼴, t), function (m) { return 제목 ? [m.묶음] : []; });
  [t, pos] = 걷어내기(t, pos, 찾기(/^[ \t]*:+/gm, t), function () { return []; });   // 줄 머리 `:` 들여쓰기 (2026-10-06)
  [t, pos] = 걷어내기(t, pos, 찾기(/'{2,}/g, t), function () { return []; });   // `''` · `'''` 굵게 · 기울임 (2026-10-06)
  [t, pos] = 걷어내기(t, pos, 찾기(/\[\[[^|\]]*\|([^\]]*)\]\]/gd, t), function (m) { return [m.묶음]; });
  [t, pos] = 걷어내기(t, pos, 찾기(/\[\[([^\]]*)\]\]/gd, t), function (m) { return [m.묶음]; });
  [t, pos] = 걷어내기(t, pos, 표구간(t, 표), function (m) { return m.남길; });
  [t, pos] = 걷어내기(t, pos, 찾기(/<[^>]+>/g, t), function () { return []; });
  [t, pos] = 걷어내기(t, pos, 찾기(빈칸꼴, t), function () { return []; });

  const out = [];                                         // `wikitext.letters` 와 같은 묶기(코드 포인트로)
  let cur = null;
  for (let i = 0; i < t.length;) {
    const o = t.codePointAt(i), w = o > 0xFFFF ? 2 : 1;
    const ps = w === 2 ? [pos[i], pos[i + 1]] : [pos[i]];
    const 꼬리 = (0x1160 <= o && o <= 0x11FF) || (0xA960 <= o && o <= 0xA97F) || (0xD7B0 <= o && o <= 0xD7FF);
    if (꼬리 && cur) { cur.c += t.slice(i, i + w); cur.p.push.apply(cur.p, ps); }
    else { if (cur) out.push(cur); cur = { c: t.slice(i, i + w), p: ps }; }
    i += w;
  }
  if (cur) out.push(cur);
  return out.map(function (x) {
    return [x.c, Math.min.apply(null, x.p), Math.max.apply(null, x.p) + 1, x.p.some(function (q) { return 오식.has(q); })];
  });
}

// ── 글자 → 모델 번호 (`wikitext.decompose` · `ocr.Model.codes`) ──
const 특수 = { "ㅣ": ["ᅟ", "ᅵ", ""], "○": ["○", "ᅠ", ""], "〇": ["○", "ᅠ", ""], "々": ["々", "ᅠ", ""], "ㅅ": ["ᄉ", "ᅠ", ""],
  ",": [",", "ᅠ", ""], ".": [".", "ᅠ", ""] };
function 가르기(cl) {
  if (특수[cl]) return 특수[cl];
  const cps = Array.from(cl);
  if (cps.length === 1) {
    const o = cl.codePointAt(0);
    if (o >= 0xAC00 && o <= 0xD7A3) {
      const i = o - 0xAC00;
      return [String.fromCharCode(0x1100 + Math.floor(i / 588)), String.fromCharCode(0x1161 + Math.floor((i % 588) / 28)),
        i % 28 ? String.fromCharCode(0x11A7 + i % 28) : ""];
    }
  }
  let L = "", V = "", T = "";
  for (const ch of cps) {
    const o = ch.codePointAt(0);
    if (o >= 0x1100 && o <= 0x115F) L += ch;
    else if (o >= 0x1160 && o <= 0x11A7) V += ch;
    else if (o >= 0x11A8 && o <= 0x11FF) T += ch;
  }
  return [L, V, T];
}

function 번호표(설정) {
  if (설정._번호표) return 설정._번호표;
  const 표 = function (a) { const m = new Map(); a.forEach(function (c, i) { if (!m.has(c)) m.set(c, i); }); return m; };
  return (설정._번호표 = { L: 표(설정.초성), V: 표(설정.중성), T: 표(설정.종성) });
}

function 번호들(설정, letters) {
  const 표 = 번호표(설정), n = letters.length;
  const rL = new Int32Array(n), rV = new Int32Array(n), rT = new Int32Array(n);
  for (let k = 0; k < n; k++) {
    const p = 가르기(letters[k]);
    rL[k] = 표.L.has(p[0]) ? 표.L.get(p[0]) : -1;
    rV[k] = 표.V.has(p[1]) ? 표.V.get(p[1]) : -1;
    rT[k] = 표.T.has(p[2]) ? 표.T.get(p[2]) : -1;
  }
  return { rL: rL, rV: rV, rT: rT };
}

// ── 상자마다 세 머리의 확률 — 한 쪽 안에서는 같은 상자를 한 번만 읽음 ──
function 읽개만들기(모델, g) {
  const 설정 = 모델.설정, nL = 설정.초성.length, nV = 설정.중성.length, nT = 설정.종성.length;
  const 본 = new Map();
  const 열쇠 = function (b) { return b[0] + "," + b[1] + "," + b[2] + "," + b[3]; };
  function 큰것(a) {
    let k = 0;
    for (let i = 1; i < a.length; i++) if (a[i] > a[k]) k = i;
    return k;
  }
  return {
    채우기: async function (boxes, geo) {
      const 새 = [], 새열쇠 = new Set();
      for (const b of boxes) {
        const k = 열쇠(b);
        if (!본.has(k) && !새열쇠.has(k)) { 새열쇠.add(k); 새.push(b); }
      }
      if (!새.length) return;
      const r = await 모델.확률(g, geo ? 전역.옛한글읽기.맞춤상자(g, 새, geo) : 새);   // 행간 넓은 쪽은 글자 크기 상자로(`align._맞춤상자`, 2026-10-06)
      새.forEach(function (b, i) {
        const L = r.L.slice(i * nL, (i + 1) * nL), V = r.V.slice(i * nV, (i + 1) * nV), T = r.T.slice(i * nT, (i + 1) * nT);
        const kL = 큰것(L), kV = 큰것(V), kT = 큰것(T);
        본.set(열쇠(b), { L: L, V: V, T: T, kL: kL, kV: kV, kT: kT,
          확신: Math.min(L[kL], Math.min(V[kV], T[kT])), 읽음: L[kL] * V[kV] * T[kT] });
      });
    },
    값: function (b) { return 본.get(열쇠(b)); },
  };
}

// ── 전사문을 정답지 삼아 자르기 (`align.to_text`) ──
function 풀기(plans, M, N, 덤) {
  const NEG = -1e18;
  let dp = [new Float64Array(N + 1).fill(NEG), new Float64Array(N + 1).fill(NEG)];
  dp[0][0] = 0.0;
  const back = [];
  for (let i = 0; i < plans.length; i++) {
    const nd = [new Float64Array(N + 1).fill(NEG), new Float64Array(N + 1).fill(NEG)];
    const bo = [new Int32Array(N + 1).fill(-1), new Int32Array(N + 1).fill(-1)];
    const bs = [new Int8Array(N + 1), new Int8Array(N + 1)];
    plans[i].forEach(function (o, oi) {
      const n = o.칸수;
      if (n > N) return;
      const K = N - n + 1, add = new Float64Array(K);
      for (let j = 0; j < n; j++) {
        const b = o.시작 + j;
        for (let t = 0; t < K; t++) add[t] += M(b, j + t);
      }
      if (덤 && n) for (let t = 0; t < K; t++) add[t] += 덤[i][oi];
      if (n === 0) for (let t = 0; t < K; t++) add[t] -= EMPTY_PEN;
      for (const st of [0, 1]) {
        const to = n ? st : st + 1;
        if (to > 1) continue;
        for (let t = 0; t < K; t++) {
          const d = dp[st][t];
          const cand = d > NEG / 2 ? d + add[t] : NEG;
          if (cand > nd[to][n + t]) { nd[to][n + t] = cand; bo[to][n + t] = oi; bs[to][n + t] = st; }
        }
      }
    });
    dp = nd; back.push([bo, bs]);
  }
  let st = dp[0][N] >= dp[1][N] ? 0 : 1;
  if (dp[st][N] <= NEG / 2) return null;
  const chosen = [];
  let k = N;
  for (let i = plans.length - 1; i >= 0; i--) {
    const bo = back[i][0], bs = back[i][1];
    const oi = bo[st][k];
    if (oi < 0) return null;
    const n = plans[i][oi].칸수;
    if (n) chosen.push([i, oi, k - n]);
    st = bs[st][k]; k -= n;
  }
  return k === 0 ? chosen.reverse() : null;
}

function 덤매기기(plans, geo, logc, 쪽자간) {            // `align._bonus`
  return plans.map(function (opts, i) {
    return opts.map(function (o) {
      if (o.개수 === 0) return 0.0;
      const y0 = geo.spans[i][0], y1 = geo.spans[i][1];
      let 합 = 0;
      for (let k = o.시작; k < o.시작 + o.개수; k++) 합 += logc[k];
      const mlog = 합 / o.개수;
      const dev = Math.min(Math.abs((y1 - y0) / o.칸수 - 쪽자간) / Math.max(1.0, 쪽자간), PITCH_CAP);
      return o.칸수 * (W_CONF * mlog - W_PITCH * dev * dev) - W_CUT * o.비용;
    });
  });
}

function 읽어내기(chosen, plans, exact, rL, cf) {          // `align._readout`
  const boxes = [], assign = [], conf = [];
  let hit = 0, known = 0;
  for (const c of chosen) {
    const o = plans[c[0]][c[1]], k0 = c[2];
    for (let j = 0; j < o.칸수; j++) {
      boxes.push(o.상자들[j]); assign.push(k0 + j);
      conf.push(cf[o.시작 + j]);
      if (exact(o.시작 + j, k0 + j)) hit++;
      if (rL[k0 + j] >= 0) known++;
    }
  }
  return { boxes: boxes, assign: assign, conf: conf, hit: hit, known: known };
}

async function 정답지자르기(A, 모델, 읽개, geo, letters, r, span, 경계) {
  const 중앙값 = A._속.중앙값, 반올림 = A._속.반올림;
  const N = letters.length, ncol = geo.cols.length;
  const base = geo.est.reduce(function (s, e) { return s + e; }, 0);
  const tries = [[geo.est.slice(), span]];
  if (Math.abs(N - base) > span * ncol * 0.5) {            // 짐작이 크게 빗나가면 넓게 다시
    const k = Math.max(0.35, N / Math.max(1, base));
    tries.push([geo.est.map(function (e) { return Math.max(1, 반올림(e * k)); }),
      span + 2 + Math.trunc(Math.abs(N - base) / Math.max(1, ncol))]);
  }
  const rL = r.rL, rV = r.rV, rT = r.rT;
  const 그림자 = 경계 ? await A.경계프로파일(모델, geo) : null;
  let why = "글자 수를 맞추지 못함";
  for (const tr of tries) {
    const bp = A.자를계획(geo, tr[0], tr[1], true, 그림자);
    const plans = bp.계획, flat = bp.상자;
    const mins = [];
    let hi = 0;
    for (const c of plans) {
      let mn = Infinity, mx = 0;
      for (const o of c) { if (o.칸수 > 0 && o.칸수 < mn) mn = o.칸수; if (o.칸수 > mx) mx = o.칸수; }
      if (mn < Infinity) mins.push(mn);
      hi += mx;
    }
    const lo = mins.reduce(function (s, v) { return s + v; }, 0) - (mins.length ? Math.max.apply(null, mins) : 0);
    if (!(lo <= N && N <= hi)) { why = "글자 수를 맞추지 못함 (그림은 " + lo + "~" + hi + "칸, 전사문은 " + N + "자)"; continue; }

    await 읽개.채우기(flat, geo);
    const nb = flat.length;
    const pL = new Int32Array(nb), pV = new Int32Array(nb), pT = new Int32Array(nb);
    const cf = new Float64Array(nb), logc = new Float64Array(nb);
    for (let b = 0; b < nb; b++) {
      const v = 읽개.값(flat[b]);
      pL[b] = v.kL; pV[b] = v.kV; pT[b] = v.kT; cf[b] = v.확신;
      logc[b] = Math.log(Math.max(v.확신, 1e-6));
    }
    const 모름 = new Uint8Array(N);
    for (let k = 0; k < N; k++) 모름[k] = (rL[k] < 0 || rV[k] < 0) ? 1 : 0;
    const M = function (b, k) {                           // `align._match_matrix`
      if (모름[k]) return UNKNOWN;
      const a = pL[b] === rL[k], c = pV[b] === rV[k], d = pT[b] === rT[k];
      return W_L * (a ? 1 : 0) + W_V * (c ? 1 : 0) + W_T * (d ? 1 : 0) + W_ALL * (a && c && d ? 1 : 0);
    };
    const exact = function (b, k) { return pL[b] === rL[k] && pV[b] === rV[k] && pT[b] === rT[k]; };
    const 자간들 = function (ch) {
      return 중앙값(ch.map(function (c) {
        return (geo.spans[c[0]][1] - geo.spans[c[0]][0]) / plans[c[0]][c[1]].칸수;
      }));
    };

    let best = null;
    const ch = 풀기(plans, M, N, null);
    if (ch) {
      best = 읽어내기(ch, plans, exact, rL, cf);
      best.방법 = 1;
      const seen = [];
      let pit = 자간들(ch);
      for (const step of [2, 3, 4]) {                     // 잰 자간으로 벌점을 주고 다시 풂
        if (seen.some(function (q) { return Math.abs(pit - q) < q * 0.01; })) break;
        seen.push(pit);
        const ch2 = 풀기(plans, M, N, 덤매기기(plans, geo, logc, pit));
        if (!ch2) break;
        const cand = 읽어내기(ch2, plans, exact, rL, cf);
        cand.방법 = step;
        if (cand.hit > best.hit) best = cand;           // 실제로 더 맞은 쪽만
        pit = 자간들(ch2);
      }
    }
    if (best === null) continue;
    best.일치 = best.hit / Math.max(1, best.known);
    best.사유 = null;
    return best;
  }
  return { 사유: why };
}

// ── 맞대기 (`대조.맞대기`) ──
async function 맞대기(A, 모델, 읽개, geo, 글자들, span, 경계) {
  const letters = 글자들.map(function (g) { return g[0]; });
  if (letters.length < MIN_LETTERS) return { 사유: "글자가 너무 적습니다(" + letters.length + "자)" };
  const 번호 = 번호들(모델.설정, letters);
  const r = await 정답지자르기(A, 모델, 읽개, geo, letters, 번호, span, 경계);
  if (r.사유) return { 사유: r.사유 };
  const 중앙값 = A._속.중앙값;
  const boxes = r.boxes, assign = r.assign, n = boxes.length, N = letters.length;
  const rL = 번호.rL, rV = 번호.rV, rT = 번호.rT;
  const v = boxes.map(function (b) { return 읽개.값(b); });
  const 아는 = [], 같음 = [], 전사확률 = [], 스캔 = [];
  for (let i = 0; i < n; i++) {
    const k = assign[i], w = v[i];
    아는.push(rL[k] >= 0 && rV[k] >= 0 && rT[k] >= 0);
    같음.push(아는[i] && w.kL === rL[k] && w.kV === rV[k] && w.kT === rT[k]);
    전사확률.push(아는[i] ? w.L[rL[k]] * w.V[rV[k]] * w.T[rT[k]] : 0.0);
    스캔.push(모델.글자(w.kL, w.kV, w.kT).normalize("NFC"));   // 현대 글자는 완성형으로
  }
  // 열마다 일치 — 한 열이 통째로 어긋나면 그 열의 '글자가 다름' 은 내지 않음
  const 열 = boxes.map(function (b) { return b[0]; });
  const 열들 = Array.from(new Set(열));
  const 흔들린열 = new Set();
  열들.forEach(function (x) {
    let 셈 = 0, 맞 = 0;
    for (let j = 0; j < n; j++) if (열[j] === x && 아는[j]) { 셈++; if (같음[j]) 맞++; }
    if ((셈 >= 5 ? 맞 / 셈 : 1.0) < 열문턱) 흔들린열.add(x);
  });
  const 높이 = boxes.map(function (b) { return b[3] - b[1]; });
  const 열높이 = new Map();
  열들.forEach(function (x) { 열높이.set(x, 중앙값(높이.filter(function (h, j) { return 열[j] === x; }))); });
  const 높이비 = function (j) { return 높이[j] / Math.max(1.0, 열높이.get(열[j])); };
  const 맞음 = function (i, kk) {
    return 0 <= kk && kk < N && rL[kk] >= 0 && rV[kk] >= 0 && rT[kk] >= 0
      && v[i].kL === rL[kk] && v[i].kV === rV[kk] && v[i].kT === rT[kk];
  };
  const 후보 = [];
  const 넣기 = function (갈래, i, 점수) {
    const 이웃 = [];
    for (const j of [i - 1, i + 1]) if (0 <= j && j < n && 열[j] === 열[i]) 이웃.push(높이비(j));
    후보.push({ 갈래: 갈래, 번호: assign[i], 상자번호: i, 전사: letters[assign[i]], 스캔: 스캔[i],
      전사확률: 전사확률[i], 확신: v[i].확신, 점수: 점수, 높이비: 높이비(i), 이웃높이비: 이웃 });
  };
  const 표 = 번호표(모델.설정);
  const 빈종성 = 표.T.has("") ? 표.T.get("") : -1;
  const 받침잘림 = function (j) {
    const kk = assign[j];
    return v[j].kL === rL[kk] && v[j].kV === rV[kk] && rT[kk] !== 빈종성 && v[j].kT === 빈종성 && 높이비(j) < 받침잘림높이;
  };
  const 바뀜인가 = function (j, 엄격) {
    엄격 = 엄격 === undefined ? 1.0 : 엄격;
    return 아는[j] && !글자들[assign[j]][3] && 전사확률[j] < P_TR_MAX * 엄격
      && v[j].확신 >= TOP_MIN && !흔들린열.has(열[j]) && !받침잘림(j);
  };
  const 점수 = function (j) { return Math.log(v[j].읽음) - Math.log(Math.max(전사확률[j], 1e-12)); };

  let i = 0;
  while (i < n) {                                         // 읽는 차례로 '다름' 이 이어진 덩이마다
    if (같음[i]) { i++; continue; }
    let e = i;
    while (e + 1 < n && !같음[e + 1]) e++;
    const 덩이 = [];
    for (let j = i; j <= e; j++) 덩이.push(j);
    if (덩이.length === 1) {
      if (글자들[assign[i]][3]) {
        // {{SIC}} 안 — 원문 오식으로 이미 표시됨
      } else if (!아는[i]) {
        if (v[i].확신 >= TOP_MIN && !흔들린열.has(열[i])) 넣기("모르는자모", i, 0.0);
      } else if (바뀜인가(i)) {
        넣기("바뀜", i, 점수(i));
      }
      i = e + 1;
      continue;
    }
    const 옮김 = new Map();                               // 상자마다 '몇 칸 옮기면 맞나'
    for (const j of 덩이) {
      let d = null;
      for (const q of [-1, 1, -2, 2, -3, 3]) if (맞음(j, assign[j] + q)) { d = q; break; }
      옮김.set(j, d);
    }
    let 옮김수 = 0;
    옮김.forEach(function (d) { if (d !== null) 옮김수++; });
    if (옮김수 >= 2) {                                    // 밀림 — 옮김 값이 바뀌는 자리마다 '빠짐 · 더들어감'
      let 지금 = 0, 틈 = i;
      const 사건 = [];
      for (const j of 덩이) {
        const d = 옮김.get(j);
        if (d === null) continue;
        if (d !== 지금) {
          사건.push(j);
          넣기(d < 지금 ? "빠짐" : "더들어감", 틈, Math.abs(d - 지금));
          후보[후보.length - 1].끝번호 = assign[j];
          후보[후보.length - 1].칸 = Math.abs(d - 지금);
          지금 = d;
        }
        틈 = j + 1;
      }
      for (const j of 덩이) {
        if (옮김.get(j) === null && 사건.every(function (q) { return Math.abs(j - q) > 2; })
            && 바뀜인가(j, 0.2) && v[j].확신 >= 0.95) {
          넣기("바뀜", j, 점수(j)); 후보[후보.length - 1].붙음 = true;
        }
      }
    } else {
      for (const j of 덩이) {
        if (바뀜인가(j, 0.2) && v[j].확신 >= 0.95) { 넣기("바뀜", j, 점수(j)); 후보[후보.length - 1].붙음 = true; }
      }
    }
    i = e + 1;
  }
  const 차례 = { "바뀜": 0, "모르는자모": 1, "깨진글자": 1, "빠짐": 2, "더들어감": 2 };
  후보.sort(function (a, b) { return (차례[a.갈래] - 차례[b.갈래]) || (b.점수 - a.점수); });
  return { 사유: null, 일치: r.일치, 상자: boxes, assign: assign, 후보: 후보,
    흔들림: r.일치 < 일치문턱, 흔들린열: 흔들린열.size, 열수: 열들.length, 글자수: N };
}

const 낱갈래 = ["바뀜", "모르는자모"];
function 같은후보(c, 들) {                                // 다른 자르기에도 같은 자리 · 같은 글자로 나왔나
  return 들.some(function (d) {
    if (낱갈래.indexOf(c.갈래) >= 0) return d.갈래 === c.갈래 && d.번호 === c.번호 && d.스캔 === c.스캔;
    return d.갈래 === c.갈래 && Math.abs(d.번호 - c.번호) <= 2;
  });
}

// ── 한 쪽 (`대조.한쪽` · `_한번`) ──
// 기하 후보: false = 자르는 기하 · true = 읽는 기하 · "끝띠" = 제본 그림자 띠를 지운 자르는 기하(권2 0003 — 전사문과 더 잘 맞을 때만)
// · "판심" = 판심 걸러내기를 끈 읽는 기하(훈아진언 1894 PDF 58쪽 — 광곽에 붙은 끝 열을 판심으로 뗌).
// 큰빼기: 큰 활자 틀(책 이름) 안 글자를 빼고 맞대기 — null 이면 그대로 해 보고, 잘 안 맞고 큰 활자 틀이 있으면 빼고도.
async function 한번(A, 모델, 읽개, 기하얻기, raw, 제목, 경계, 기하들, 큰빼기) {
  const 시도 = (제목 === null || 제목 === undefined) ? [false, true] : [제목];
  const 큰있음 = Array.from(큰틀).some(function (n) { return new RegExp("\\{\\{[" + S + "]*" + n + "[" + S + "]*\\|").test(raw); });
  const 빼기들 = (큰빼기 === null || 큰빼기 === undefined) ? [false, true] : [큰빼기];
  let best = null;
  const 본열 = {};
  for (const 빼기 of 빼기들) {
    if (빼기 && (큰빼기 === null || 큰빼기 === undefined) && (!큰있음 || (best && (best[0].일치 || 0) >= 다시볼일치))) break;
    for (const 판 of 기하들) {
      if (best && (best[0].일치 || 0) >= 다시볼일치) break;     // 자르는 기하로 잘 맞았으면 그만
      const 판심 = 판 === "판심", 읽기 = 판 === true || 판심, 끝띠 = 판 === "끝띠";
      if (끝띠 && !("자르기" in 본열)) { const g0 = 기하얻기(false, false); 본열.자르기 = g0 ? g0.cols : null; }
      if (판심 && !("읽기" in 본열)) { const g0 = 기하얻기(true, false); 본열.읽기 = g0 ? g0.cols : null; }
      const geo = 기하얻기(읽기, 끝띠, 판심);
      if (!geo) continue;
      if (끝띠 && JSON.stringify(geo.cols) === JSON.stringify(본열.자르기)) continue;   // 띠가 없는 쪽 — 자르는 기하와 같음
      if (판심 && JSON.stringify(geo.cols) === JSON.stringify(본열.읽기)) continue;     // 뗀 판심 열이 없는 쪽 — 읽는 기하와 같음
      if (!읽기 && !끝띠) 본열.자르기 = geo.cols;
      if (읽기 && !판심) 본열.읽기 = geo.cols;
      let 이전 = null;
      for (const kh of 시도) {
        const 글자들 = 인쇄글자(raw, kh, 빼기);
        if (이전 !== null && 글자들.length === 이전) continue;   // 제목이 없는 쪽 — 같은 것을 두 번 안 함
        이전 = 글자들.length;
        const r = await 맞대기(A, 모델, 읽개, geo, 글자들, 3, 경계);
        r.기하 = 판심 ? "판심" : (끝띠 ? "끝띠" : (읽기 ? "읽기" : "자르기"));
        r.제목 = kh;
        r.큰빼기 = 빼기;
        if (best === null || (r.일치 || -1) > (best[0].일치 || -1)) best = [r, 글자들];
      }
    }
  }
  if (best === null) return [{ 사유: "스캔에서 열을 못 찾았습니다" }, []];
  return best;
}

/**
 * 위키 원문 한 쪽을 그 쪽 스캔(그림 g — `읽기.js` 의 `그림읽기`)과 맞댐.
 * 옵션: 문헌설정 {자간비, 읽기자간비, 단, 판짜임} (없으면 이 쪽 그림으로 자간을 재고 한 단으로 봄 — 파이썬의 '모르는 문헌'),
 *       제목(편·장 제목이 종이에 찍히나 — 없으면 둘 다 해 보고 잘 맞는 쪽), 합의(기본 켬), 밀림(기본 끔).
 * 반환은 서버판(`전사대조/서버.py`)의 답과 같은 꼴 — 후보마다 원문 자리(시작 · 끝, UTF-16)와 앞뒤 글자.
 */
async function 한쪽(모델, g, raw, 옵션) {
  옵션 = 옵션 || {};
  const A = 전역.옛한글읽기;
  const s = 옵션.문헌설정 || null;
  const 합의 = 옵션.합의 !== false, 밀림 = !!옵션.밀림;
  const 기하들 = 옵션.기하들 || [false, true, "끝띠", "판심"];
  const 읽개 = 읽개만들기(모델, g);
  let 쪽자간 = undefined;
  const 보관 = {};
  const 기하얻기 = function (읽기, 끝띠, 판심) {           // `대조.기하` — 가장자리 후보 열 없이(끝띠 = 제본 그림자 띠를 지우고 · 판심 = 판심 걸러내기 끔)
    const 열쇠 = (읽기 ? "읽기" : "자르기") + (끝띠 ? "끝띠" : "") + (판심 ? "판심" : "");
    const 판 = 판심 ? false : undefined;
    if (열쇠 in 보관) return 보관[열쇠];
    let geo;
    if (s) {
      let r = (읽기 && s.읽기자간비) || s.자간비 || null;
      if (!r) {                                          // 판형만 정하고 자간비는 못 잰 파일 — 이 쪽 그림으로
        if (쪽자간 === undefined) 쪽자간 = A.쪽자간비(g, s.단 || 1);
        r = 쪽자간;
      }
      const 표준 = (읽기 && s.판짜임) ? s.판짜임.자간 : null;
      geo = A.쪽기하(g, r, s.단 || 1, 읽기, 표준, false, !!끝띠, 판);
    } else {
      if (쪽자간 === undefined) 쪽자간 = A.쪽자간비(g, 1);
      geo = A.쪽기하(g, 쪽자간, 1, 읽기, null, false, !!끝띠, 판);
    }
    return (보관[열쇠] = geo);
  };
  const 처음 = await 한번(A, 모델, 읽개, 기하얻기, raw, 옵션.제목, false, 기하들, null);
  const r = 처음[0], 글자들 = 처음[1];
  if (r.사유) return r;
  if (!밀림) r.후보 = r.후보.filter(function (c) { return c.갈래 !== "빠짐" && c.갈래 !== "더들어감"; });
  r.합의본 = [];
  const 낱 = r.후보.filter(function (c) { return 낱갈래.indexOf(c.갈래) >= 0; });
  r.후보.forEach(function (c) { c.합의 = 낱갈래.indexOf(c.갈래) < 0 || !합의; });
  // 다르게 한 번 더 잘라서 남는 것만 펼쳐 보임 — B: 배운 경계 검출기를 섞은 자르기, C: 읽는 기하 + 검출기
  for (const 판 of [["B", 기하들], ["C", [true, "판심"]]]) {
    const 남은 = 낱.filter(function (c) { return !c.합의; });
    if (!합의 || !남은.length) break;
    const 다시 = await 한번(A, 모델, 읽개, 기하얻기, raw, r.제목, true, 판[1], r.큰빼기);
    r.합의본.push(판[0]);
    if (다시[0].사유 || 다시[1].length !== 글자들.length) continue;
    남은.forEach(function (c) { c.합의 = 같은후보(c, 다시[0].후보); });
  }
  const 차례 = { "바뀜": 0, "모르는자모": 1, "깨진글자": 1, "빠짐": 2, "더들어감": 2 };
  r.후보.sort(function (a, b) {
    return ((a.합의 ? 0 : 1) - (b.합의 ? 0 : 1)) || (차례[a.갈래] - 차례[b.갈래]) || (b.점수 - a.점수);
  });
  r.후보.forEach(function (c) {
    const 끝k = c.끝번호 !== undefined ? c.끝번호 : c.번호;
    c.시작 = 글자들[c.번호][1]; c.끝 = 글자들[끝k][2];
    c.앞 = 글자들.slice(Math.max(0, c.번호 - 5), c.번호).map(function (x) { return x[0]; }).join("");
    c.뒤 = 글자들.slice(끝k + 1, 끝k + 6).map(function (x) { return x[0]; }).join("");
  });
  r.아는문헌 = !!s;
  return r;
}

전역.옛한글전사대조 = { 한쪽: 한쪽, 인쇄글자: 인쇄글자, _속: { 가르기: 가르기, 표구간: 표구간 } };
const 셈 = 전역.옛한글전사대조;

// ════════════════════════════════════════════════════════════════════
//  화면 — 위키문헌 편집 창 (칠하기 · 목록 · 바꾸기)
// ════════════════════════════════════════════════════════════════════
if (typeof document === "undefined") return;

var 상태, 단추, 판, 깔개 = null, 후보들 = [], 어긋남보기 = false, 끝난것보기 = false;
// 합의 = 다르게 한 번 더 잘라도 남은 것(`한쪽` 의 합의). 안 남은 것은 자르기 실수일 때가 많아 접어 둔다
function 확실(c) { return c.합의 !== false && c.갈래 !== "빠짐" && c.갈래 !== "더들어감"; }
function 보일것(c) { return 어긋남보기 || 확실(c); }
function 바꿀수(c) { return (c.갈래 === "바뀜" || c.갈래 === "모르는자모") && c.스캔; }

var 이름 = { "바뀜": "글자가 다름", "모르는자모": "모르는 자모", "깨진글자": "깨진 글자", "빠짐": "스캔에 글자가 더 있음", "더들어감": "전사문에 글자가 더 있음" };
var 색 = { "바뀜": "rgba(255,80,80,.40)", "모르는자모": "rgba(255,160,0,.40)", "깨진글자": "rgba(170,80,255,.38)", "빠짐": "rgba(80,140,255,.35)", "더들어감": "rgba(80,140,255,.35)" };

function 알림(t) { if (상태) 상태.textContent = t; }

function 지금쪽() {
  var cfg = mw.config.get(["wgCanonicalNamespace", "wgTitle", "wgAction"]);
  if (cfg.wgCanonicalNamespace !== "Page") return null;
  if (cfg.wgAction !== "edit" && cfg.wgAction !== "submit") return null;
  var m = /^(.*)\/(\d+)$/.exec(cfg.wgTitle);
  return m ? { 파일: m[1], 쪽: parseInt(m[2], 10) } : null;
}

function 편집상자() {
  return document.querySelector("#wpTextbox1") || document.querySelector("textarea[name='wpTextbox1']");
}

function 보이나(상자) {
  return 상자.isConnected && 상자.offsetParent !== null && getComputedStyle(상자).visibility !== "hidden";
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
    상자.setSelectionRange(c.시작, Math.max(c.끝, c.시작 + 1));
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
  // 넘기거나 바꾼 곳은 목록에서 빼고 맨 아래 한 줄로 접는다(작업자 요청 — 흐리게만 두면 자리를 먹음)
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
    b.textContent = c.전사;
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

// ── 도구 불러오기 — OCR 소도구와 같은 자료(`window.옛한글OCR자료`). 둘 다 켜 두면 읽기.js · onnxruntime 은 한 번만 받음 ──
var ORT = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.20.1/dist/";
var 자료 = window.옛한글OCR자료 || "";
if (자료 && 자료.charAt(자료.length - 1) !== "/") 자료 += "/";
var 설정 = null, 모델 = null, 준비중 = null;

// Toolforge 서버(`툴포지/app.py`, 2026-10-07) — 있으면 맞대기를 서버에 맡김(파이썬 `대조.한쪽` — 답의 꼴이 `셈.한쪽` 과 같음).
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

function 스크립트(url) {
  return new Promise(function (ok, no) {
    var s = document.createElement("script");
    s.src = url;
    s.onload = ok;
    s.onerror = function () { no(new Error(url + " 를 못 불러왔습니다")); };
    document.head.appendChild(s);
  });
}

function 준비() {
  if (준비중) return 준비중;
  준비중 = (async function () {
    알림("도구를 불러오는 중…");
    if (!window.옛한글읽기) await 스크립트(자료 + "읽기.js");
    if (!window.ort) await 스크립트(ORT + "ort.webgpu.min.js");
    설정 = window.옛한글읽기.설정 || window.옛한글읽기.설정넣기(await (await fetch(자료 + "설정.json")).json());
    알림("모델을 불러오는 중… (처음 한 번만)");
    ort.env.wasm.wasmPaths = ORT;
    ort.env.wasm.numThreads = 1;                        // 위키문헌에는 SharedArrayBuffer 가 없음
    var 세션 = await ort.InferenceSession.create(자료 + "옛한글모델.onnx", { executionProviders: ["wasm"] });
    var 경계세션 = 설정.경계 ? await ort.InferenceSession.create(자료 + "경계검출.onnx", { executionProviders: ["wasm"] }) : null;
    모델 = window.옛한글읽기.모델만들기(설정, 세션, ort, 경계세션);
  })();
  준비중.catch(function () { 준비중 = null; });         // 실패하면 다음에 다시
  return 준비중;
}

// 스캔 — OCR 소도구와 같은 방법(⚠ 여러 쪽 파일은 API 가 너비를 무시함 → 주소를 한 번 받아 `/page{쪽}-1920px-` 만 갈아 끼움)
var 주소틀 = {}, 쪽수 = {};
function 주소틀얻기(파일) {
  var 너비 = (설정 && 설정.스캔너비) || 1920;
  return 주소틀[파일] ? Promise.resolve(주소틀[파일]) : new mw.Api().get({
    action: "query", format: "json", formatversion: 2,
    prop: "imageinfo", titles: "File:" + 파일,
    iiprop: "url|size", iiurlwidth: 500, iiurlparam: "page1-500px",
  }).then(function (r) {
    var p = r.query && r.query.pages && r.query.pages[0];
    var ii = p && p.imageinfo && p.imageinfo[0];
    if (!ii || !ii.thumburl) throw new Error("스캔 주소를 못 받았습니다. 파일 이름이 맞는지 보세요: " + 파일);
    var u = ii.thumburl.split("?")[0];
    if (!/\/page\d+-\d+px-/.test(u)) throw new Error("이 파일은 여러 쪽짜리(PDF·DjVu)가 아닌 것 같습니다: " + 파일);
    쪽수[파일] = ii.pagecount || 0;                    // 판형 살필 쪽 고르기에 씀
    return (주소틀[파일] = u.replace(/\/page\d+-\d+px-/, "/page{N}-" + 너비 + "px-"));
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
          no(new Error("스캔을 " + 너비 + "px 로 달라고 했는데 " + im.naturalWidth + "px 이 왔습니다."));
          return;
        }
        ok(im);
      };
      im.onerror = function () { no(new Error("스캔 그림을 못 읽었습니다: " + url)); };
      im.src = url;
    });
  });
}

// 이 파일의 판형 · 자간비 · 판짜임 — OCR 소도구와 **같은** 셈 · 같은 기억 칸(`읽기.js` 의 `판형살피기`, 2026-10-03).
// 소도구로 먼저 연 파일이면 기억한 값, 처음이면 쪽 몇 장을 받아 정함(처음 한 번 1~3분)
function 판형살피기(파일) {
  if (!window.옛한글읽기.판형살피기) {          // 브라우저가 옛 읽기.js 를 기억하는 중(jsDelivr 최대 7일)
    var 오류 = new Error("읽기.js 가 옛 판입니다 — 편집 창을 Ctrl+Shift+R 로 새로 고쳐 주세요.");
    오류.name = "OldReadJsVersionError";
    return Promise.reject(오류);
  }
  return window.옛한글읽기.판형살피기(파일, {
    쪽수: function () { return 주소틀얻기(파일).then(function () { return 쪽수[파일] || 0; }); },
    받기: function (p) { return 스캔가져오기(파일, p); },
    알림: 알림,
  });
}

/** 상자 i 와 같은 열의 앞뒤 글자까지 오려 빨간 테를 두른 그림(data: 주소) — `대조.조각그림` */
function 조각그림(im, boxes, i, 앞뒤) {
  var b = boxes[i], j0 = i, j1 = i;
  while (j0 > 0 && i - j0 < 앞뒤 && boxes[j0 - 1][0] === b[0]) j0--;
  while (j1 + 1 < boxes.length && j1 - i < 앞뒤 && boxes[j1 + 1][0] === b[0]) j1++;
  var pad = 6;
  var x0 = Math.max(0, b[0] - pad), x1 = Math.min(im.naturalWidth, b[2] + pad);
  var y0 = Math.max(0, boxes[j0][1] - pad), y1 = Math.min(im.naturalHeight, boxes[j1][3] + pad);
  var cv = document.createElement("canvas");
  cv.width = x1 - x0; cv.height = y1 - y0;
  var c = cv.getContext("2d");
  c.drawImage(im, x0, y0, x1 - x0, y1 - y0, 0, 0, x1 - x0, y1 - y0);
  c.strokeStyle = "rgb(220,30,30)"; c.lineWidth = 3;
  c.strokeRect(b[0] - x0 - 1, b[1] - y0, b[2] - b[0] + 1, b[3] - b[1]);
  return cv.toDataURL("image/png");
}

async function 시작() {
  var 쪽 = 지금쪽(), 상자 = 편집상자();
  if (!쪽 || !상자) return;
  단추.disabled = true;
  걷기();
  var t0 = performance.now();
  try {
    var 본문 = 상자.value;
    var 답, im = null;
    if (서버) {                                         // 후보 그림(data: 주소)까지 서버가 붙여 줌
      await 서버살피기(쪽.파일);
      알림("서버에서 문자를 대조하는 중…");
      답 = await 서버로("api/compare", { file: 쪽.파일, page: 쪽.쪽, text: 본문 });
    } else {
      await 준비();
      var 살핀 = await 판형살피기(쪽.파일);
      알림("스캔 파일을 받는 중…");
      im = await 스캔가져오기(쪽.파일, 쪽.쪽);
      알림("문자를 대조하는 중… (화면이 잠깐 멎을 수 있습니다)");
      await new Promise(function (ok) { setTimeout(ok, 30); });   // 알림이 먼저 그려지게
      var g = window.옛한글읽기.그림읽기(im);
      답 = await 셈.한쪽(모델, g, 본문, { 문헌설정: 살핀 });
    }
    if (답.사유) throw new Error(답.사유);
    if (상자.value !== 본문) throw new Error("맞대는 사이에 편집 상자가 바뀌었습니다 — 다시 눌러 주세요.");
    답.초 = ((performance.now() - t0) / 1000).toFixed(1);
    후보들 = 답.후보.map(function (c) {
      c.원문 = 본문.slice(c.시작, c.끝);
      if (im && c.상자번호 >= 0) c.그림 = 조각그림(im, 답.상자, c.상자번호, (c.갈래 === "빠짐" || c.갈래 === "더들어감") ? 2 : 1);
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
    알림(e && e.name === "OldReadJsVersionError" ? 메시지 : "✗ " + 메시지);
  } finally {
    단추.disabled = false;
  }
}

function 세우기() {
  if (!지금쪽() || !편집상자()) return;
  if (document.getElementById("전사대조-줄")) return;
  var 줄 = document.createElement("div");
  줄.id = "전사대조-줄";
  줄.style.cssText = "margin:8px 0;display:flex;gap:10px;align-items:center;flex-wrap:wrap";
  단추 = document.createElement("button");
  단추.type = "button";
  단추.className = "cdx-button";
  단추.textContent = "스캔과 맞대기 (전사대조)";
  단추.title = "지금 편집 상자의 전사문을 이 쪽 스캔과 맞대어 틀렸을 만한 글자를 짚습니다";
  단추.addEventListener("click", 시작);
  상태 = document.createElement("span");
  상태.style.cssText = "font-size:13px;color:#54595d";
  줄.appendChild(단추);
  줄.appendChild(상태);
  var 상자 = 편집상자();
  상자.parentNode.insertBefore(줄, 상자);
}

window.전사대조 = { 시작: 시작, 후보: function () { return 후보들; } };   // 시험용

if (window.mw && mw.loader) {
  mw.loader.using(["mediawiki.api", "mediawiki.util"]).then(function () {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", 세우기);
    else 세우기();
  });
}
})(typeof self !== "undefined" ? self : this);
