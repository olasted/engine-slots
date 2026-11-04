#!/usr/bin/env python3
"""
Engine Slots — local launcher.

Serves the static explorer (index.html) AND proxies Engine's game-launch
endpoint using curl_cffi with a real Chrome TLS fingerprint, so the browser
can embed playable demos that it otherwise can't reach (the /play endpoint
has no CORS and sits behind Cloudflare).

Only games whose studio published a public "share" have a playable demo.
For everything else Engine returns 403 and we report "no demo".

Run:
    pip install curl_cffi
    python server.py            # -> http://localhost:8000
    python server.py 9000       # custom port
"""
import json, sys, time, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path

try:
    from curl_cffi import requests as creq
except ImportError:
    sys.exit("curl_cffi is required:  pip install curl_cffi")

ROOT = Path(__file__).resolve().parent
API = "https://studio.engine.io"
IMPERSONATE = "chrome"               # real Chrome TLS/JA3 fingerprint
SESS = creq.Session()                # reused connection pool

# cache: (team,game) -> (expires_ts, result_dict)
_cache = {}
_lock = threading.Lock()
CACHE_TTL = 55                       # seconds; live sessions are short-lived


def _play(team, game, math, front, device):
    """Call /play. Returns live url on 201, else None. Raises only on network error."""
    r = SESS.get(
        f"{API}/api/teams/{team}/games/{game}/play",
        params={"device": device, "math": math, "front": front},
        impersonate=IMPERSONATE, timeout=25,
    )
    if r.status_code == 201:
        try:
            return r.json().get("url")
        except Exception:
            return None
    return None


def _share_ok(team, game, math, front):
    """True if a public share exists for this math/front combo."""
    try:
        r = SESS.get(f"{API}/api/share/{team}/{game}/{math}/{front}",
                     impersonate=IMPERSONATE, timeout=20)
        return r.status_code == 200
    except Exception:
        return False


def find_demo(team, game, device="desktop", mode="full"):
    """
    mode="fast": only the common combos (1/2, 1/1) — instant yes/no.
    mode="full": fast first, then validate slowly by probing the share grid
                 and launching the first combo that actually exists.
    Returns {"available": bool, "url": str|None, "combo": "m/f"|None, "reason": str}.
    """
    # 1) fast attempt (covers the overwhelmingly common 1/2 and 1/1)
    for m, f in ((1, 2), (1, 1)):
        try:
            url = _play(team, game, m, f, device)
        except Exception as e:
            return {"available": False, "url": None, "reason": f"network error: {e}"}
        if url:
            return {"available": True, "url": url, "combo": f"{m}/{f}", "reason": "ok"}

    if mode == "fast":
        return {"available": False, "url": None, "combo": None,
                "reason": "no quick demo", "canSearch": True}

    # 2) slow validation — scan which shares actually exist, then launch one
    valid = []
    for m in range(0, 4):
        for f in range(0, 4):
            if _share_ok(team, game, m, f):
                valid.append((m, f))
            time.sleep(0.05)
    for m, f in valid:
        try:
            url = _play(team, game, m, f, device)
        except Exception:
            url = None
        if url:
            return {"available": True, "url": url, "combo": f"{m}/{f}", "reason": "ok"}
        time.sleep(0.2)

    return {"available": False, "url": None, "combo": None,
            "reason": "no public demo — the studio hasn't shared this game publicly"}


def cached_demo(team, game, device, mode="full", fresh=False):
    key = (team, game, device, mode)
    now = time.time()
    if not fresh:
        with _lock:
            hit = _cache.get(key)
            if hit and hit[0] > now:
                return hit[1]
    res = find_demo(team, game, device, mode)
    # positive results cache briefly (live session is short); negatives longer
    ttl = CACHE_TTL if res.get("available") else 600
    with _lock:
        _cache[key] = (now + ttl, res)
    return res


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/launch":
            q = parse_qs(u.query)
            team = (q.get("team") or [""])[0].strip()
            game = (q.get("game") or [""])[0].strip()
            device = (q.get("device") or ["desktop"])[0].strip() or "desktop"
            mode = (q.get("mode") or ["full"])[0].strip() or "full"
            fresh = (q.get("fresh") or ["0"])[0] in ("1", "true")
            if not team or not game:
                return self._send(400, json.dumps({"error": "team and game required"}))
            try:
                res = cached_demo(team, game, device, mode, fresh)
            except Exception as e:
                return self._send(502, json.dumps({"available": False, "reason": str(e)}))
            return self._send(200, json.dumps(res))
        if u.path == "/health":
            return self._send(200, json.dumps({"ok": True, "impersonate": IMPERSONATE}))
        # static files
        return self._serve_static(u.path)

    do_HEAD = do_GET

    def _serve_static(self, path):
        rel = path.lstrip("/") or "index.html"
        fp = (ROOT / rel).resolve()
        if ROOT not in fp.parents and fp != ROOT and not str(fp).startswith(str(ROOT)):
            return self._send(403, "forbidden", "text/plain")
        if fp.is_dir():
            fp = fp / "index.html"
        if not fp.is_file():
            return self._send(404, "not found", "text/plain")
        ctypes = {".html": "text/html; charset=utf-8", ".js": "text/javascript",
                  ".css": "text/css", ".md": "text/markdown", ".json": "application/json",
                  ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}
        self._send(200, fp.read_bytes(), ctypes.get(fp.suffix, "application/octet-stream"))

    def log_message(self, fmt, *args):
        if "/launch" in (self.path or ""):
            sys.stderr.write("  launch: %s\n" % (self.path,))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Engine Slots launcher  ->  http://localhost:{port}")
    print(f"  curl_cffi impersonate = {IMPERSONATE}  (Chrome TLS)")
    print("  demos play only for studio-shared games; others report 'no demo'.")
    print("  Ctrl+C to stop.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
