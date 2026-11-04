# Engine Slots Explorer

Search and browse every live slot on **Engine** (`studio.engine.io`), ranked by
players and turnover, with a per-game stats panel (RTP, max win, volatility,
30-day turnover trend) and — when run locally — an **embedded playable demo**.

Live (browse only): **https://olasted.github.io/engine-slots/**

## Browsing
Just open the live link, or any static host. It reads Engine's public insights
API directly from the browser (open CORS, no login). No backend needed to browse.

## Playing demos (local launcher)
Demos can't run on the static site: Engine's launch endpoint (`/api/teams/.../play`)
has **no CORS** and sits behind Cloudflare, so the browser can't call it. The
included launcher fixes that using **`curl_cffi`** with a real **Chrome TLS
fingerprint**, which also gets past Cloudflare's bot checks.

```bash
pip install curl_cffi
python server.py            # -> http://localhost:8000   (python server.py 9000 for another port)
```

Then open **http://localhost:8000**, click any slot, and the **Demo** panel
at the top of the card does:

1. **Fast check** — tries the common share version instantly.
2. If nothing, a **"Search harder"** button scans every share version slowly
   (probing the share grid with the Chrome-impersonated client), then launches
   the first that exists.
3. If a demo exists, the live game is embedded in an iframe (the live host sends
   `frame-ancestors *`, so it's embeddable). **"Fresh session"** relaunches.

### Important reality check
A demo only exists for games whose **studio published a public share link**.
The ~6,700 live games on operators mostly have **none** — Engine returns `403`
and the panel says *"no public demo."* The launcher will play your own shared
games (e.g. `squiffy-slots/toxic-mess`) and any others that were shared publicly.
This is a platform limitation, not a bug in the tool.

## Files
- `index.html` — the single-page app (browse + demo UI).
- `server.py` — local launcher: static server + `/launch` proxy (curl_cffi, Chrome TLS).
- `API_NOTES.md` — full analysis of Engine's API.
