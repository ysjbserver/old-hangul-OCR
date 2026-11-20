# -*- coding: utf-8 -*-
"""
곁글지움 — 곁글 검출기(ONNX)로 쪽의 곁글 자리를 종이 색으로 지움. torch 없이(Toolforge).
  쓰는 곳: Toolforge `app._곁글살피기` · `곁글적용`. ⚠ 영역 지정(JS) 짝은 아직 없음.

검출기: `제작/도구/곁글검출.py`(학습 `실험59`) → `곁글검출.onnx`(`제작/읽은결과/밤결과_20261117/곁글onnx.py` 가 내보내고 torch 와 맞댐).
  · `검출기(경로).지도(g)` — 쪽 그림(uint8 H×W) → 곁글 확률(H×W float32). `곁글검출.곁글지도` 와 같은 셈(PIL 줄이기 · 늘리기 같음)
  · `지운그림(g, p)` — 확률 > 문턱 자리를 5px 넓혀 종이 색(90 백분위)으로 → (지운 그림, 지운 넓이 몫)
"""
import os
import numpy as np
from PIL import Image, ImageFilter

폭 = 768              # `곁글검출.폭` 과 같음
문턱 = 0.5            # 화소 곁글 확률
넓힘 = 5              # MaxFilter 크기
곁글문턱 = 0.04       # 쪽 지운 넓이 몫이 이보다 크면 곁글 책(곁글몫.tsv 로 정함)


def 넣기(g):
    """`곁글검출.넣기` 와 같은 셈 → (1×1×H'×폭 float32, 배율, 줄인 높이)"""
    H, W = g.shape
    s = 폭 / W
    h = int(round(H * s))
    a = np.asarray(Image.fromarray(g).resize((폭, h), Image.LANCZOS), np.float32) / 255.0
    h8 = (h + 7) // 8 * 8
    if h8 != h:
        a = np.concatenate([a, np.full((h8 - h, 폭), float(np.median(a)), np.float32)], 0)
    return ((a - 0.5) / 0.5)[None, None].astype(np.float32), s, h


class 검출기:
    def __init__(self, 경로, 스레드=1):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = 스레드
        so.inter_op_num_threads = 1
        so.enable_cpu_mem_arena = False
        self.세션 = ort.InferenceSession(경로, so, providers=["CPUExecutionProvider"])

    def 지도(self, g):
        x, s, h = 넣기(g)
        z = self.세션.run(None, {"x": x})[0][0].astype(np.float32)        # (3, H'/4, W'/4)
        e = np.exp(z - z.max(axis=0, keepdims=True))
        p = (e / e.sum(axis=0, keepdims=True))[2]
        p = p[: (h + 3) // 4]
        return np.asarray(Image.fromarray(p).resize((g.shape[1], g.shape[0]), Image.BILINEAR), np.float32)


def 곁글자간(쪽별, 모임=1.25, 적어도=3, 배=1.6):
    """곁글 지운 쪽들에서 잰 쪽별 자간(`scan.page_ratio`, None 은 뺌) → 책 자간.
    곁글이 남은 쪽은 두 배로 재지므로(쳥루지열녀: 0.49 셋 · 1.0 넷) 가장 작은 값의 `모임` 배 안에 `적어도` 쪽이 모이고
    전체 중앙값이 그 무리의 `배` 배를 넘으면 낮은 무리의 중앙값. 아니면 전체 중앙값. 못 재면 None."""
    r = sorted(x for x in 쪽별 if x)
    if not r:
        return None
    낮은 = [x for x in r if x <= r[0] * 모임]
    가운데 = float(np.median(r))
    if len(낮은) >= 적어도 and 가운데 >= 배 * float(np.median(낮은)):
        return float(np.median(낮은))
    return 가운데


def 지운그림(g, p, 문턱=문턱):
    """확률 지도 p > 문턱 자리를 넓혀 종이 색으로 → (지운 그림, 지운 넓이 몫). `검출지우기.지운그림` 과 같음."""
    m = Image.fromarray(((p > 문턱) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(넓힘))
    m = np.asarray(m) > 0
    out = g.copy()
    out[m] = int(np.percentile(g, 90))
    return out, float(m.mean())


def 지운자리(ip):
    """스캔 경로 → 지운 그림을 둘 자리(같은 폴더 `<이름>_곁글.png`)."""
    return os.path.splitext(ip)[0] + "_곁글.png"


def 지우기(det, ip):
    """스캔 그림을 지워 `지운자리` 에 남김 → (지운 그림 경로, 지운 넓이 몫). 다 쓴 뒤 옮김(반쯤 쓴 그림을 읽지 않게)."""
    with Image.open(ip) as im:
        g = np.asarray(im.convert("L"))
    g2, 몫 = 지운그림(g, det.지도(g))
    q = 지운자리(ip)
    Image.fromarray(g2).save(q + ".part", "PNG")
    os.replace(q + ".part", q)
    return q, 몫
