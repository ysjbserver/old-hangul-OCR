# -*- coding: utf-8 -*-
"""
ONNX 로 읽는 모델 — torch 없이 도는 곳(Toolforge 서버, `툴포지/`)에서 `ocr.Model` · `경계검출.검출기` 대신 씀 (2026-10-07)

모델 파일은 브라우저판과 **같은 것**(`제작/만들기/내보내기.py` 가 뽑는 `옛한글모델.onnx` · `경계검출.onnx` · `설정.json`).
겉모습(메서드 이름 · 돌려주는 값)은 둘과 같게 — `align` · `근원/부품/대조.py` 가 그대로 받음:
  · `모델.read(im, boxes)` → (초성번호, 중성번호, 종성번호, 확신) — `ocr.Model.read` 와 같음(확신 = 세 머리 최댓값의 최솟값)
  · `모델.확률(im, boxes)` → 세 머리 확률 — `대조.확률읽기` 와 같음
  · `모델.letter` · `모델.codes` · `모델.Ls/Vs/Ts` · `모델.size`
  · `검출기.경계확률(g, x0, x1)` — `경계검출.검출기` 와 같음
⚠ 그림 오리기는 `ocr.Model.crops` · `경계검출.띠` 와 **같은 PIL 셈**이어야 함(고치면 셋 다). torch(CPU FP32)와 차이는 1e-5 언저리.
⚠ `enable_cpu_mem_arena=False` — 켜 두면 뭉치 256 에서 메모리가 600MB 를 넘음(Toolforge 기본 512MB). 끄면 70MB, 속도 같음.
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
        # 뭉치는 self.뭉치 를 넘지 않게 — `대조.확률읽기` 가 512 를 넘기면 ORT 중간값이 한꺼번에 올라 400MB 넘게 씀
        # (Toolforge 512MB 에서 전사대조 도중 프로세스가 죽음, 2026-10-07). 뭉치 크기는 결과를 바꾸지 않음.
        batch = min(batch, self.뭉치)
        # 같은 상자는 한 번만 — 칸수를 est±3 으로 일곱 번 잘라 보면 같은 상자가 되풀이됨(서로 다른 것 22~25%, 브라우저판 `모델.읽기` 와 같은 꾀).
        # 부름 사이에도 기억함(2026-10-07): 전사대조 한 쪽은 기하 · 합의(B · C)마다 같은 그림을 다시 잘라 읽어, 부름을 넘는 중복을 빼면
        # 모델 셈이 32~68% 줄어듦. 결과는 그대로(같은 상자 → 같은 오린 그림 → 같은 답). 그림 내용으로 열쇠를 삼고 마지막 그림 하나만 둠.
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
    """글자 모델을 돌려주고, `align` 의 경계 검출기도 ONNX 것으로 끼움(torch 를 부르지 않게)."""
    import align
    align._검출기 = 검출기(폴더, 스레드)
    return 모델(폴더, 스레드)
