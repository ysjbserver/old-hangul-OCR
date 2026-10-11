"""실제 WSGI 좌표 검증. 극단 입력은 모의 모델로 검사하고 정상 입력은 실제 ONNX와 비교.
python -B tests/test_area_coordinates.py [--bundle 폴더]
"""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parents[1]
DEFAULT = HERE if (HERE / "부품").is_dir() else HERE.parents[1] / "old-hangul-ocr-toolforge"
parser = argparse.ArgumentParser()
parser.add_argument("--bundle", type=Path, default=DEFAULT)
args, remaining = parser.parse_known_args()
BUNDLE = args.bundle.resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(BUNDLE))
CACHE = tempfile.TemporaryDirectory(prefix="ocr-coordinates-test-")
os.environ["OCR_CACHE"] = CACHE.name
spec = importlib.util.spec_from_file_location("ocr_coordinates_test_app", BUNDLE / "app.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class CoordinateTest(unittest.TestCase):
    requests = 0

    def setUp(self):
        self.g = np.full((3000, 1920), 255, dtype=np.uint8)
        self.im = Image.fromarray(self.g)
        self.reader = Mock()
        self.reader.read.side_effect = lambda im, boxes: (np.zeros(len(boxes), dtype=int),) * 3 + (np.ones(len(boxes)),)
        self.detector = Mock(return_value=np.zeros(3000))
        self.image = Mock(return_value=(self.im, self.g))
        self.patches = [patch.object(server, "그림", self.image),
                        patch.object(server, "모델얻기", return_value=self.reader),
                        patch.object(server.align._검출기, "경계확률", self.detector),
                        patch.object(server, "살핀값", side_effect=AssertionError("판형 검사 호출")),
                        patch.object(server, "스캔", side_effect=AssertionError("스캔 캐시 접근"))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def request(self, path, body):
        raw = json.dumps(body).encode("utf-8")
        env = {"REQUEST_METHOD": "POST", "PATH_INFO": path, "CONTENT_LENGTH": str(len(raw)),
               "wsgi.input": io.BytesIO(raw), "wsgi.url_scheme": "http"}
        responses = []
        result = b"".join(server.app(env, lambda s, hs: responses.append((s, dict(hs)))))
        type(self).requests += 1
        self.assertEqual(len(responses), 1)
        status, hs = responses[0]
        self.assertEqual(int(hs["Content-Length"]), len(result))
        self.assertEqual(hs["Cache-Control"], "no-store")
        self.assertTrue(hs["Content-Type"].startswith("application/json"))
        return status, json.loads(result)

    def bad(self, path, fields, early=False):
        self.image.reset_mock()
        self.reader.read.reset_mock()
        self.detector.reset_mock()
        body = dict(file="mock.pdf", page=1, **fields)
        status, result = self.request(path, body)
        self.assertEqual(status, "400 Bad Request", result)
        self.assertTrue(result.get("오류"))
        self.reader.read.assert_not_called()
        self.detector.assert_not_called()
        if early:
            self.image.assert_not_called()

    def test_box_shape_and_numbers(self):
        invalid = [None, {}, "box", 1, True, [None], [[0, 0, 1]], [[0, 0, 1, 1, 1]],
                   ["0123"], [{"x0": 0}], [[False, 0, 10, 10]], [["0", 0, 10, 10]],
                   [[0.5, 0, 10, 10]], [[None, 0, 10, 10]], [[[], 0, 10, 10]],
                   [[float("nan"), 0, 10, 10]], [[0, 0, float("inf"), 10]],
                   [[0, 0, 10, -float("inf")]], [[-1, 0, 10, 10]], [[0, -1, 10, 10]],
                   [[10, 0, 10, 10]], [[11, 0, 10, 10]], [[0, 10, 10, 10]], [[0, 11, 10, 10]]]
        for boxes in invalid:
            with self.subTest(boxes=boxes):
                self.bad("/api/boxes", dict(boxes=boxes), early=True)

    def test_box_bounds_and_limits(self):
        for box in ([1910, 0, 1921, 10], [0, 2990, 10, 3001]):
            with self.subTest(box=box):
                self.bad("/api/boxes", dict(boxes=[box]))
        for boxes in ([[0, 0, 10**100, 10**100]], [[0, 0, 1017, 1016]],
                      [[0, 0, 1016, 1016]] * 17, [[0, 0, 1, 1]] * 20001):
            with self.subTest(count=len(boxes), first=boxes[0]):
                self.bad("/api/boxes", dict(boxes=boxes), early=True)
        # 자를 때의 4px 여백을 포함한 개별 상한과 합계 상한의 경계.
        boxes = [[0, 0, 1016, 1016]] * 16
        status, _ = self.request("/api/boxes", dict(file="mock.pdf", boxes=boxes))
        self.assertEqual(status, "200 OK")
        self.reader.read.assert_called_once_with(self.im, boxes)

    def test_normal_boxes_and_edges(self):
        boxes = [[0, 0, 1, 1], [1919, 2999, 1920, 3000], [30.0, 40.0, 90.0, 100.0]]
        for model in ("hangul", "hanmun"):
            status, result = self.request("/api/boxes", dict(file="mock.pdf", boxes=boxes, model=model))
            self.assertEqual(status, "200 OK")
            self.assertEqual(result, dict(초=[0]*3, 중=[0]*3, 종=[0]*3, 확신=[1.0]*3))
            self.assertEqual(self.reader.read.call_args.args[1], [[int(v) for v in b] for b in boxes])
        for fields in (dict(boxes=[]), {}):
            status, result = self.request("/api/boxes", dict(file="mock.pdf", **fields))
            self.assertEqual(status, "200 OK")
            self.assertEqual(result, dict(초=[], 중=[], 종=[], 확신=[]))
        for x0, x1 in ((0, 32), (1888, 1920), (0.0, 1920.0), (0, 12)):
            status, result = self.request("/api/edge", dict(file="mock.pdf", x0=x0, x1=x1))
            self.assertEqual(status, "200 OK")
            self.assertEqual(result, dict(확률=[0.0]*3000, 높이=3000))

    def test_edge_numbers_order_and_bounds(self):
        for fields in ({}, dict(x0=0), dict(x1=32), dict(x0=None, x1=32), dict(x0=True, x1=32),
                       dict(x0="0", x1=32), dict(x0=0.1, x1=32), dict(x0=float("nan"), x1=32),
                       dict(x0=0, x1=float("inf")), dict(x0=-1, x1=32), dict(x0=32, x1=32),
                       dict(x0=33, x1=32), dict(x0=0, x1=1), dict(x0=0, x1=7)):
            with self.subTest(fields=fields):
                self.bad("/api/edge", fields, early=True)
        for x0, x1 in ((0, 1921), (1920, 1952), (0, 10**100)):
            with self.subTest(x0=x0, x1=x1):
                self.bad("/api/edge", dict(x0=x0, x1=x1))

    def test_edge_resize_limit_without_large_allocation(self):
        self.image.return_value = (SimpleNamespace(width=100, height=2048), SimpleNamespace(shape=(2048, 100)))
        self.detector.return_value = np.zeros(2048)
        status, _ = self.request("/api/edge", dict(file="mock.pdf", x0=0, x1=8))
        self.assertEqual(status, "200 OK")  # 4배, 8192px 경계
        for height in (2049, 10**9):
            self.image.return_value = (None, SimpleNamespace(shape=(height, 100)))
            self.bad("/api/edge", dict(x0=0, x1=8))

    def test_request_must_be_object(self):
        for path in ("/api/boxes", "/api/edge"):
            for body in ([], None, 1, "body"):
                status, result = self.request(path, body)
                self.assertEqual(status, "400 Bad Request", result)

    @classmethod
    def tearDownClass(cls):
        print(f"Mock WSGI coordinate requests: {cls.requests}")


class ActualModelTest(unittest.TestCase):
    def test_unchanged_normal_inference(self):
        # 우회/상한 검사 외의 정상 경로는 기존 ONNX 함수를 직접 부른 결과와 정확히 같아야 함.
        g = np.full((300, 200), 255, dtype=np.uint8)
        g[20:70, 15:55] = 20
        g[100:180, 80:120] = 0
        im = Image.fromarray(g)
        network = patch.object(server, "그림", return_value=(im, g))
        with network:
            request = CoordinateTest.request
            for model in ("hangul", "hanmun"):
                if model == "hanmun" and not (BUNDLE / "모델/근대 국한문/국한문모델.onnx").exists():
                    continue
                boxes = [[0, 0, 50, 80], [80, 100, 120, 180], [199, 299, 200, 300]]
                l, v, t, cf = server.모델얻기(model).read(im, boxes)
                status, result = request(self, "/api/boxes", dict(file="local.pdf", boxes=boxes, model=model))
                self.assertEqual(status, "200 OK")
                self.assertEqual(result, dict(초=l.tolist(), 중=v.tolist(), 종=t.tolist(), 확신=cf.tolist()))
            for x0, x1 in ((0, 32), (80, 120), (192, 200)):
                expected = server.align._검출기.경계확률(g, x0, x1).tolist()
                status, result = request(self, "/api/edge", dict(file="local.pdf", x0=x0, x1=x1))
                self.assertEqual(status, "200 OK")
                self.assertEqual(result, dict(확률=expected, 높이=300))

    requests = 0

    @classmethod
    def tearDownClass(cls):
        print(f"Actual ONNX WSGI parity requests: {cls.requests}")


if __name__ == "__main__":
    try:
        unittest.main(argv=[sys.argv[0]] + remaining)
    finally:
        CACHE.cleanup()
