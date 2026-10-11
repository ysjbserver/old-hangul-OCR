"""실제 묶음의 WSGI 회귀 검사. python -B tests/test_base_url.py [--bundle 폴더]

원본 폴더에서 실행하면 프로젝트의 생성 묶음을 검사한다. Node.js로 응답 전체의
JS 구문과 주소 설정문 실행을 검사하며, 스캔 다운로드/OCR 추론/위키 저장은 하지 않는다.
"""
import argparse
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
DEFAULT = HERE if (HERE / "부품").is_dir() else HERE.parents[1] / "old-hangul-ocr-toolforge"
parser = argparse.ArgumentParser()
parser.add_argument("--bundle", type=Path, default=DEFAULT)
args, remaining = parser.parse_known_args()
BUNDLE = args.bundle.resolve()
NODE = shutil.which("node")
if not NODE:
    raise SystemExit("JavaScript 실행 검증에는 Node.js가 필요합니다")
sys.dont_write_bytecode = True
sys.path.insert(0, str(BUNDLE))
CACHE = tempfile.TemporaryDirectory(prefix="ocr-base-test-")
os.environ["OCR_CACHE"] = CACHE.name
spec = importlib.util.spec_from_file_location("ocr_base_test_app", BUNDLE / "app.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

PUBLIC = "old-hangul-ocr.toolforge.org"
PATHS = ("/ocr.js", "/compare.js", "/area/서버.js", "/소도구.js", "/전사대조.js", "/영역지정/서버.js")
JS_CHECK = r"""
const vm = require('node:vm');
const rows = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
for (const row of rows) {
  new vm.Script(row.body); // 소도구 전체도 문법이 유효해야 함
  const context = {window: {옛한글OCR서버: row.before}};
  vm.runInNewContext(row.prefix, context, {timeout: 1000});
  if (context.window.옛한글OCR서버 !== row.expected || context.pwned !== undefined)
    throw new Error('주소 또는 실행 흐름 변경');
}
"""


class BaseURLTest(unittest.TestCase):
    js_rows = []
    requests = 0

    def request(self, path, headers=None, base=None):
        env = {"REQUEST_METHOD": "GET", "PATH_INFO": path.encode("utf-8").decode("latin-1"),
               "wsgi.url_scheme": "http", "wsgi.input": io.BytesIO(), "HTTP_HOST": PUBLIC}
        env.update(headers or {})
        response = []
        with patch.dict(os.environ):
            os.environ.pop("OCR_BASE", None)
            if base is not None:
                os.environ["OCR_BASE"] = base
            body = b"".join(server.app(env, lambda status, hs: response.append((status, dict(hs)))))
        type(self).requests += 1
        self.assertEqual(len(response), 1)
        status, hs = response[0]
        self.assertEqual(int(hs["Content-Length"]), len(body))
        return status, hs, body.decode("utf-8")

    def good(self, headers, expected, base=None):
        for path in PATHS:
            with self.subTest(path=path, headers=headers, base=base):
                status, hs, body = self.request(path, headers, base)
                self.assertEqual(status, "200 OK")
                self.assertTrue(hs["Content-Type"].startswith("text/javascript"))
                prefix, tail = body.split("\n", 1)
                keep = path in server.소도구들
                lead = "window.옛한글OCR서버 = " + ("window.옛한글OCR서버 || " if keep else "")
                self.assertTrue(prefix.startswith(lead))
                self.assertEqual(json.loads(prefix[len(lead):-1]), expected)
                if keep:
                    self.assertEqual(tail.encode("utf-8"), (BUNDLE / "정적" / server.소도구들[path]).read_bytes())
                for before in (None, "https://chosen.example/"):
                    self.js_rows.append(dict(body=body, prefix=prefix, before=before,
                                             expected=before if keep and before else expected))

    def bad(self, headers, base=None, code="400 Bad Request"):
        for path in PATHS:
            with self.subTest(path=path, headers=headers, base=base):
                status, hs, body = self.request(path, headers, base)
                self.assertEqual(status, code)
                self.assertTrue(hs["Content-Type"].startswith("application/json"))
                self.assertEqual(hs["Cache-Control"], "no-store")
                self.assertIn("오류", json.loads(body))
                self.assertNotIn("pwned", body)

    def test_normal_addresses(self):
        for headers, expected in [
            ({}, f"https://{PUBLIC}/"),
            ({"HTTP_HOST": PUBLIC.upper() + ":443"}, f"https://{PUBLIC}:443/"),
            ({"HTTP_HOST": "internal:8000", "HTTP_X_FORWARDED_HOST": PUBLIC,
              "HTTP_X_FORWARDED_PROTO": "https"}, f"https://{PUBLIC}/"),
            ({"HTTP_X_FORWARDED_PROTO": "http"}, f"https://{PUBLIC}/"),
            ({"HTTP_HOST": 'x";globalThis.pwned=1;//', "HTTP_X_FORWARDED_HOST": PUBLIC}, f"https://{PUBLIC}/"),
            ({"HTTP_HOST": "localhost:8761"}, "http://localhost:8761/"),
            ({"HTTP_HOST": "127.0.0.1:8761"}, "http://127.0.0.1:8761/"),
            ({"HTTP_HOST": "[::1]:8761"}, "http://[::1]:8761/"),
            ({"HTTP_HOST": "localhost", "HTTP_X_FORWARDED_PROTO": "https"}, "https://localhost/"),
            ({"HTTP_HOST": ""}, "http://localhost/"),
        ]:
            self.good(headers, expected)

    def test_host_and_forwarded_host_attacks(self):
        attacks = [
            'x";globalThis.pwned=1;//', "x';globalThis.pwned=1;//", "x\\evil", "x\r\nInjected:1",
            "x\t", "x\x00", "x\u2028", "x\u2029", PUBLIC + ",evil.example", PUBLIC + "/path",
            PUBLIC + "?x", PUBLIC + "#x", PUBLIC + "@evil.example", "evil.example",
            PUBLIC + ".evil.example", "evil" + PUBLIC, "another.toolforge.org", PUBLIC + ".",
            PUBLIC + ":0", PUBLIC + ":65536", PUBLIC + ":abc", PUBLIC + ":", PUBLIC + ":80",
            "[::1", "localhost%22", " localhost", "localhost ", "http://localhost",
        ]
        for key in ("HTTP_HOST", "HTTP_X_FORWARDED_HOST"):
            for value in attacks:
                self.bad({key: value})

    def test_protocol_attacks(self):
        for key in ("HTTP_X_FORWARDED_PROTO", "wsgi.url_scheme"):
            for value in ('https";globalThis.pwned=1;//', "javascript", "ftp", "https,http", "https\n", "HTTPS", " https"):
                self.bad({key: value})

    def test_operator_base_overrides_all_headers(self):
        headers = {"HTTP_HOST": 'x";globalThis.pwned=1;//', "HTTP_X_FORWARDED_HOST": "evil.example",
                   "HTTP_X_FORWARDED_PROTO": "javascript"}
        for base in (f"https://{PUBLIC}", "https://ocr.example:8443/proxy/ocr/", "http://localhost:8761"):
            self.good(headers, base.rstrip("/") + "/", base)

    def test_invalid_operator_base(self):
        for base in ('https://x/";globalThis.pwned=1;//', "https://x/\\", "https://x/\n", "//x", "ftp://x",
                     "https://user:pass@x/", "https://x/?q=1", "https://x/#frag", "https://x:0/", "https://x:65536/"):
            self.bad({}, base, "500 Internal Server Error")

    def test_encoding_defense_in_depth(self):
        # 검증기가 미래에 완화되더라도 문자열이 코드가 되지 않는지 별도로 확인.
        value = 'https://example/";globalThis.pwned=1;//\\\r\n\u2028\u2029'
        with patch.object(server, "_바탕주소", return_value=value):
            for path in PATHS:
                status, _, body = self.request(path)
                self.assertEqual(status, "200 OK")
                prefix = body.split("\n", 1)[0]
                self.js_rows.append(dict(body=body, prefix=prefix, before=None, expected=value))
                self.assertNotIn("\u2028", prefix)
                self.assertNotIn("\u2029", prefix)

    @classmethod
    def tearDownClass(cls):
        result = subprocess.run([NODE, "-e", JS_CHECK], input=json.dumps(cls.js_rows),
                                text=True, capture_output=True, encoding="utf-8")
        if result.returncode:
            raise AssertionError(result.stderr)
        print(f"WSGI requests: {cls.requests}; JS syntax/execution checks: {len(cls.js_rows)}")


if __name__ == "__main__":
    try:
        unittest.main(argv=[sys.argv[0]] + remaining)
    finally:
        CACHE.cleanup()
