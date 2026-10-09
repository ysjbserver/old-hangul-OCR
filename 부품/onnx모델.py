# -*- coding: utf-8 -*-
"""
ONNX 로 읽는 모델 — torch 없이 도는 곳(Toolforge 서버)에서 `ocr.Model` · `경계검출.검출기` 대신 씀.

모델 파일은 브라우저판과 같은 `옛한글모델.onnx` · `경계검출.onnx` · `설정.json`.
겉모습(메서드 이름 · 돌려주는 값)은 둘과 같게 — `align` · `대조.py` 가 그대로 받음:
  · `모델.read(im, boxes)` → (초성번호, 중성번호, 종성번호, 확신) — `ocr.Model.read` 와 같음(확신 = 세 머리 최댓값의 최솟값)
  · `모델.확률(im, boxes)` → 세 머리 확률 — `대조.확률읽기` 와 같음
  · `모델.letter` · `모델.codes` · `모델.Ls/Vs/Ts` · `모델.size`
  · `검출기.경계확률(g, x0, x1)` — `경계검출.검출기` 와 같음
⚠ 그림 오리기는 `ocr.Model.crops` · `경계검출.띠` 와 같은 PIL 셈이어야 함(고치면 셋 다).
⚠ `enable_cpu_mem_arena=False` — 켜면 메모리가 크게 늚(Toolforge 기본 512MB).
"""
import hashlib
import json
import os

import numpy as np
from PIL import Image
import onnxruntime as ort

from wikitext import 특수표시

경계폭 = 32           # `경계검출.폭` 과 같음


def _세션(경로, 스레드):
    so = ort.SessionOptions()
    so.intra_op_num_threads = 스레드
    so.inter_op_num_threads = 1
    so.enable_cpu_mem_arena = False
    return ort.InferenceSession(경로, so, providers=["CPUExecutionProvider"])


def _펴기(z):
    """소프트맥스(float32 — torch 와 같게)"""
    z = z.astype(np.float32)
    e = np.exp(z - z.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


class 모델:
    def __init__(self, 폴더, 스레드=1, 뭉치=64):
        with open(os.path.join(폴더, "설정.json"), encoding="utf-8") as f:
            v = json.load(f)
        self.설정 = v
        self.Ls, self.Vs, self.Ts = v["초성"], v["중성"], v["종성"]
        self.size = v["그림크기"]
        self.iL = {c: i for i, c in enumerate(self.Ls)}
        self.iV = {c: i for i, c in enumerate(self.Vs)}
        self.iT = {c: i for i, c in enumerate(self.Ts)}
        self.뭉치 = v.get("뭉치", 뭉치)          # 설정.json '뭉치' — 브라우저판 `읽기.js` 와 같은 값
        self.세션 = _세션(os.path.join(폴더, "옛한글모델.onnx"), 스레드)
        self.폴더 = 폴더
        self.dev = "onnx"
        self._기억 = (None, {})               # (그림 열쇠, {상자: (초, 중, 종 확률)}) — 마지막 그림 하나만

    def crops(self, im, boxes):
        """`ocr.Model.crops` 와 같은 셈 — numpy (n, 1, size, size) float32"""
        X = np.zeros((len(boxes), 1, self.size, self.size), dtype=np.float32)
        for k, b in enumerate(boxes):
            X[k, 0] = np.asarray(im.crop((b[0]-4, b[1]-4, b[2]+4, b[3]+4))
                                 .resize((self.size, self.size)), dtype=np.float32)
        return (X / 255 - 0.5) / 0.5

    def _머리들(self, im, boxes, batch):
        # 뭉치는 self.뭉치 를 넘지 않게 — 크면 ORT 중간값 메모리가 커짐. 결과는 안 바뀜.
        batch = min(batch, self.뭉치)
        # 같은 상자는 한 번만 읽음 — 부름 사이에도 기억(그림 내용이 열쇠, 마지막 그림 하나만). 결과는 그대로.
        열쇠그림 = (im.size, im.mode, hashlib.blake2b(im.tobytes(), digest_size=16).digest())
        if self._기억[0] != 열쇠그림:
            self._기억 = (열쇠그림, {})
        기억 = self._기억[1]
        열쇠들 = [tuple(int(v) for v in b) for b in boxes]
        새것 = list(dict.fromkeys(k for k in 열쇠들 if k not in 기억))
        for i in range(0, len(새것), batch):
            덩이 = 새것[i:i + batch]
            x = self.crops(im, 덩이)
            sL, sV, sT = (_펴기(z) for z in self.세션.run(None, {"x": x}))
            for j, k in enumerate(덩이):
                기억[k] = (sL[j], sV[j], sT[j])
        return [np.stack([기억[k][m] for k in 열쇠들]) for m in range(3)]

    def read(self, im, boxes, batch=None):
        if not boxes:
            z = np.zeros(0, dtype=np.int64)
            return z, z, z, np.zeros(0)
        sL, sV, sT = self._머리들(im, list(boxes), batch or self.뭉치)
        cf = np.minimum(np.minimum(sL.max(1), sV.max(1)), sT.max(1))
        return sL.argmax(1), sV.argmax(1), sT.argmax(1), cf

    def 확률(self, im, boxes, batch=None):
        if not boxes:
            z = np.zeros((0, 1))
            return z, z, z
        return tuple(s.astype(np.float64) for s in self._머리들(im, list(boxes), batch or self.뭉치))

    def letter(self, l, v, t):
        s = self.Ls[l] + self.Vs[v] + self.Ts[t]
        return 특수표시.get(s, s)

    def codes(self, letters, decompose):
        rL, rV, rT = [], [], []
        for c in letters:
            L, V, T = decompose(c)
            rL.append(self.iL.get(L, -1))
            rV.append(self.iV.get(V, -1))
            rT.append(self.iT.get(T, -1))
        return np.array(rL), np.array(rV), np.array(rT)


def _한자인가(c):
    if len(c) != 1:
        return False
    o = ord(c)
    return 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF or 0x20000 <= o <= 0x3134F


class 혼용모델(모델):
    """'근대 국한문' — `제작/도구/ocr혼용.혼용Model` 과 같은 모양을 ONNX 로 읽음(머리 다섯: 갈래 K · 초 L · 중 V · 종 T · 한자 H).

    폴더: `국한문모델.onnx` + `글자표.json`(`제작/만들기/내보내기_국한문.py`). 한자는 초성 표 **뒤에 이어 붙인 자리**(`Ls[nL + k]`)로,
    중성 · 종성은 빈 자리('')로 실어 보냄 — `Ls[l] + Vs[v] + Ts[t]` 가 곧 그 한자라 `align` · `page` · `대조` 가 고침 없이 돎.
    확신 = 한글이면 min(갈래, 초, 중, 종), 한자면 min(갈래, 한자). ⚠ 결과는 파이토치 `ocr혼용` 과 같아야 함(고치면 둘 다).
    """

    def __init__(self, 폴더, 설정, 스레드=1):
        with open(os.path.join(폴더, "글자표.json"), encoding="utf-8") as f:
            v = json.load(f)
        self.설정 = 설정                                    # 스캔너비 · 뭉치 — 옛한글 모델 설정과 같은 값
        self.뭉치 = 설정.get("뭉치", 64)
        Ls, Vs, Ts, Hs = v["초성"], v["중성"], v["종성"], v["한자"]
        self.Hs, self.nL = Hs, len(Ls)
        self.Ls = list(Ls) + list(Hs)
        self.Vs = list(Vs) + ([""] if "" not in Vs else [])
        self.Ts = list(Ts) + ([""] if "" not in Ts else [])
        self.v빈, self.t빈 = self.Vs.index(""), self.Ts.index("")
        self.iL = {c: i for i, c in enumerate(Ls)}
        self.iV = {c: i for i, c in enumerate(Vs)}
        self.iT = {c: i for i, c in enumerate(Ts)}
        self.iH = {c: i for i, c in enumerate(Hs)}
        self.size = v["그림크기"]
        self.세션 = _세션(os.path.join(폴더, "국한문모델.onnx"), 스레드)
        self.폴더 = 폴더
        self.dev = "onnx"
        self._기억 = (None, {})

    def _머리들(self, im, boxes, batch):
        # 마지막 그림 하나의 (갈래 · 초 · 중 · 종 · 한자) 확률을 상자별로 기억 — 부름 사이에도(옛한글 모델과 같은 까닭)
        batch = min(batch, self.뭉치)
        열쇠그림 = (im.size, im.mode, hashlib.blake2b(im.tobytes(), digest_size=16).digest())
        if self._기억[0] != 열쇠그림:
            self._기억 = (열쇠그림, {})
        기억 = self._기억[1]
        열쇠들 = [tuple(int(v) for v in b) for b in boxes]
        새것 = list(dict.fromkeys(k for k in 열쇠들 if k not in 기억))
        for i in range(0, len(새것), batch):
            덩이 = 새것[i:i + batch]
            x = self.crops(im, 덩이)
            p = [_펴기(z) for z in self.세션.run(None, {"x": x})]
            for j, k in enumerate(덩이):
                기억[k] = tuple(a[j] for a in p)
        return [np.stack([기억[k][m] for k in 열쇠들]) for m in range(5)]

    def read(self, im, boxes, batch=None):
        if not boxes:
            z = np.zeros(0, dtype=np.int64)
            return z, z, z, np.zeros(0)
        sK, sL, sV, sT, sH = self._머리들(im, list(boxes), batch or self.뭉치)
        한 = sK[:, 1] > sK[:, 0]
        l = np.where(한, sH.argmax(1) + self.nL, sL.argmax(1))
        v = np.where(한, self.v빈, sV.argmax(1))
        t = np.where(한, self.t빈, sT.argmax(1))
        c = np.where(한, np.minimum(sK[:, 1], sH.max(1)),
                     np.minimum(np.minimum(sK[:, 0], sL.max(1)), np.minimum(sV.max(1), sT.max(1))))
        return l, v, t, c

    def 확률(self, im, boxes, batch=None):
        """`대조.확률읽기` 용 — 세 머리 꼴(초 · 중 · 종)로. 갈래로 한글 · 한자를 가르고(`read` 와 같은 쪽), 그쪽 머리 확률에 갈래 확률을 곱함.
        한글: 초 [갈래0 × 초, 0…] · 중 [중, 0] · 종 [종, 0] / 한자: 초 [0…, 갈래1 × 한자] · 중 · 종은 빈 자리 하나만 1 →
        '초 × 중 × 종' 이 곧 그 글자의 확률이고 1순위가 `read` 와 같음."""
        if not boxes:
            z = np.zeros((0, 1))
            return z, z, z
        sK, sL, sV, sT, sH = (a.astype(np.float64) for a in self._머리들(im, list(boxes), batch or self.뭉치))
        n, nH = len(sK), sH.shape[1]
        한 = (sK[:, 1] > sK[:, 0])[:, None]
        L = np.zeros((n, self.nL + nH)); V = np.zeros((n, len(self.Vs))); T = np.zeros((n, len(self.Ts)))
        L[:, :self.nL] = np.where(한, 0.0, sL * sK[:, :1])
        L[:, self.nL:] = np.where(한, sH * sK[:, 1:], 0.0)
        V[:, :sV.shape[1]] = np.where(한, 0.0, sV)
        T[:, :sT.shape[1]] = np.where(한, 0.0, sT)
        V[:, self.v빈] = np.where(한[:, 0], 1.0, V[:, self.v빈])
        T[:, self.t빈] = np.where(한[:, 0], 1.0, T[:, self.t빈])
        return L, V, T

    def codes(self, letters, decompose):
        rL, rV, rT = [], [], []
        for c in letters:
            if _한자인가(c):
                h = self.iH.get(c, -1)
                rL.append(h + self.nL if h >= 0 else -1); rV.append(self.v빈); rT.append(self.t빈)
                continue
            L, V, T = decompose(c)
            rL.append(self.iL.get(L, -1)); rV.append(self.iV.get(V, -1)); rT.append(self.iT.get(T, -1))
        return np.array(rL), np.array(rV), np.array(rT)


def 띠(g, x0, x1):
    """`경계검출.띠` 와 같은 셈 — 쪽 그림(np.uint8 H×W)의 열 [x0, x1) → (띠, 배율)"""
    x0, x1 = max(0, int(x0)), min(g.shape[1], int(x1))
    s = 경계폭 / max(1, x1 - x0)
    h = max(8, int(round(g.shape[0] * s)))
    im = Image.fromarray(g[:, x0:x1]).resize((경계폭, h), Image.BICUBIC)
    return (np.asarray(im, dtype=np.float32) / 255.0 - 0.5) / 0.5, s


class 검출기:
    def __init__(self, 폴더, 스레드=1):
        self.세션 = _세션(os.path.join(폴더, "경계검출.onnx"), 스레드)

    def 경계확률(self, g, x0, x1):
        b, s = 띠(g, x0, x1)
        z = self.세션.run(None, {"x": b[None, None]})[0][0]
        p = 1.0 / (1.0 + np.exp(-z.astype(np.float64)))      # float64 — `경계검출.검출기` 와 같은 까닭
        ys = np.arange(g.shape[0]) * s
        return np.interp(ys, np.arange(len(p)), p)


def 끼우기(폴더, 스레드=1):
    """`폴더`(= 묶음의 `모델/`)에서 근대 순한글 모델을 돌려주고, `align` 의 경계 검출기도 ONNX 것으로 끼움(torch 를 부르지 않게).
    폴더 짜임: `근대 순한글/`(옛한글모델.onnx · 설정.json) · `근대 국한문/` · (앞으로 중세 …) · `공용/`(경계검출.onnx — 모델마다 같이 씀)"""
    import align
    align._검출기 = 검출기(os.path.join(폴더, "공용"), 스레드)
    return 모델(os.path.join(폴더, "근대 순한글"), 스레드)
