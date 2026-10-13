import json
import threading
import unittest
import urllib.error
import urllib.request

from lld_practice.server import serve
from tests.helpers import example, make_service


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = serve(make_service(), "127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, method, path, body=None, learner="api-user", raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "X-Learner-Id": learner})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_end_to_end(self):
        code, problems = self.call("GET", "/api/problems")
        self.assertEqual(code, 200)
        self.assertGreaterEqual(len(problems), 4)
        code, a = self.call("POST", "/api/attempts", {"problem_id": "parking-lot"})
        self.assertEqual(code, 201)
        code, _ = self.call("PUT", f"/api/attempts/{a['id']}", {"content": example("parking_lot_good.py"), "format": "python"})
        self.assertEqual(code, 200)
        code, sub = self.call("POST", f"/api/attempts/{a['id']}/submit")
        self.assertEqual(code, 202)
        code, got = self.call("GET", f"/api/attempts/{a['id']}")
        self.assertEqual(got["status"], "COMPLETED")
        self.assertGreater(got["feedback"]["overall"], 80)
        code, hist = self.call("GET", "/api/attempts")
        self.assertEqual(hist[0]["id"], a["id"])

    def test_error_codes(self):
        self.assertEqual(self.call("GET", "/api/problems/nope")[0], 404)
        self.assertEqual(self.call("GET", "/api/nothing")[0], 404)
        self.assertEqual(self.call("POST", "/api/attempts", {"problem_id": "nope"})[0], 404)
        self.assertEqual(self.call("POST", "/api/attempts", raw=b"{not json")[0], 422)
        _, a = self.call("POST", "/api/attempts", {"problem_id": "elevator"}, learner="e")
        self.call("PUT", f"/api/attempts/{a['id']}", {"content": "class X(:\n  bad syntax here for sure!!", "format": "python"}, learner="e")
        code, err = self.call("POST", f"/api/attempts/{a['id']}/submit", learner="e")
        self.assertEqual(code, 422)
        self.assertIn("syntax", err["error"])
        self.call("PUT", f"/api/attempts/{a['id']}", {"content": example("parking_lot_good.py"), "format": "python"}, learner="e")
        self.assertEqual(self.call("POST", f"/api/attempts/{a['id']}/submit", learner="e")[0], 202)
        self.assertEqual(self.call("POST", f"/api/attempts/{a['id']}/submit", learner="e")[0], 409)

    def test_serves_ui_and_blocks_path_traversal(self):
        with urllib.request.urlopen(self.base + "/") as r:
            self.assertIn(b"LLD Practice", r.read())
        try:
            urllib.request.urlopen(self.base + "/../domain.py")
            self.fail("should 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)
