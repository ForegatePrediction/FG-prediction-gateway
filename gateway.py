#!/usr/bin/env python3
"""ForeGate 预测统一网关 · Unified prediction gateway.

一个对外入口,按 `type`(足球/篮球/电竞)分发到三套预测引擎。零依赖(仅标准库)。
One public entry; dispatches by `type` (football / basketball / esports) to three engines.

做法:启动时把三个引擎各自的 server.py 作为子进程拉起在内部端口(127.0.0.1:8101/8102/8103),
本网关监听 $PORT,收到请求后按 type 去掉该参数、把原路径+其余查询串转发给对应引擎,原样回传。
引擎代码零改动;各自的 markets / platform_markets 原样透传。

  GET /health                         聚合三引擎健康
  GET /predict?type=football&categoryId=30118&a=..&b=..
  GET /predict?type=basketball&categoryId=30163&a=..&b=..
  GET /predict?type=esports&game=lol&a=..&b=..&bo=5
  其余路径(/competitions /teams /games /stats ...)按 type 透传到对应引擎。
"""
import os, sys, time, subprocess, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, urlencode

ROOT = os.path.dirname(os.path.abspath(__file__))
ENGINES = {
    "football":   {"dir": "engines/football",   "port": 8101},
    "basketball": {"dir": "engines/basketball", "port": 8102},
    "esports":    {"dir": "engines/esports",    "port": 8103},
}
ALIASES = {  # 常见别名 -> 标准 type
    "soccer": "football", "fussball": "football", "fb": "football",
    "bball": "basketball", "nba": "basketball", "basket": "basketball",
    "esport": "esports", "e-sports": "esports", "eg": "esports",
}
CORS = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "*", "Access-Control-Max-Age": "86400"}
_procs = {}


def _launch():
    # 仅拉起子进程,不阻塞等待——父进程立即开始监听,子进程在后台启动。
    # 这样 Render 从休眠唤醒后毫秒级即可响应 /ping,避免保活探测超时被误判 down。
    for name, e in ENGINES.items():
        env = dict(os.environ, PORT=str(e["port"]))
        p = subprocess.Popen([sys.executable, "server.py"],
                             cwd=os.path.join(ROOT, e["dir"]), env=env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        _procs[name] = p


def _norm_type(t):
    t = (t or "").strip().lower()
    return ALIASES.get(t, t)


def _forward(engine_port, path, query_pairs):
    qs = urlencode(query_pairs)
    url = f"http://127.0.0.1:{engine_port}{path}"
    if qs:
        url += "?" + qs
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as ex:
        return ex.code, ex.read()
    except Exception as ex:
        return 502, ('{"error":"engine unreachable: %s"}' % str(ex)[:120]).encode()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, raw=False):
        if not raw:
            import json
            body = json.dumps(body, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        for k, v in CORS.items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in CORS.items(): self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path.rstrip("/") or "/"
        q = parse_qs(u.query)

        if path == "/ping":
            # 超轻保活探测:父进程一起就立即 200,不探子进程 → 唤醒瞬间可响应
            return self._send(200, {"status": "ok"})

        if path in ("/", "/health"):
            import json
            out = {"status": "ok", "service": "foregate-prediction-gateway", "engines": {}}
            for name, e in ENGINES.items():
                try:
                    r = urllib.request.urlopen(f"http://127.0.0.1:{e['port']}/health", timeout=3)
                    out["engines"][name] = json.loads(r.read())
                except Exception as ex:
                    out["engines"][name] = {"status": "down", "error": str(ex)[:80]}
            return self._send(200, out)

        # 取 type(兼容 sport 字段),去掉后转发其余参数
        t = _norm_type((q.pop("type", None) or q.pop("sport", None) or [None])[0])
        if t not in ENGINES:
            return self._send(400, {"error": "缺少或未知 type,需 football / basketball / esports",
                                    "got": t, "endpoints": ["/health", "/predict", "/competitions", "/teams", "/games", "/stats"]})
        pairs = [(k, v) for k, vs in q.items() for v in vs]
        code, body = _forward(ENGINES[t]["port"], path, pairs)
        return self._send(code, body, raw=True)


if __name__ == "__main__":
    _launch()
    port = int(os.environ.get("PORT", 8000))
    print(f"ForeGate prediction gateway on :{port}  (engines: {', '.join(ENGINES)})")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
