# Engine (engine.io) — Slots API analysis

Source: `hars/sift-2026-11-04-161613.har` (Sift HAR), captured from the Engine studio
dashboard (`studio.engine.io`) + a game launch of *Toxic Mess* by Squiffy Slots.

Engine is a **slot-game studio + marketplace / RGS platform**. Three hosts:

| Host | Role |
|------|------|
| `studio.engine.io` | Studio dashboard + **public insights/marketplace API** |
| `<team>.live.engine.io` | The playable game bundle (JS/CSS/GLB/audio), e.g. `squiffy-slots.live.engine.io/toxic-mess/v2/` |
| `rgsd.engine.io` | RGS wallet / spin backend (`/wallet/authenticate`, etc.) |

## How a slot is identified
A game is `{teamSlug}/{gameSlug}` — e.g. `squiffy-slots/toxic-mess`.
`team` = the publisher/studio. Assets are referenced by UUID asset id, fetched via
`/api/asset/image/{assetId}`.

## Discovering ALL slots — the key endpoints (all PUBLIC, `Access-Control-Allow-Origin: *`)

| Endpoint | Returns |
|----------|---------|
| `GET /api/insights/directory` | **The master list.** `{games:[{game:{name,slug,image,blurhash}, team:{name,slug,image}, rank}], publishers:[...]}` — ~6,900 games, ~1,890 providers, in one ~2 MB response. **This is how you enumerate every slot.** |
| `GET /api/insights/rankings?category=<c>&page=<n>&range=<r>` | Leaderboard, 100/page (`pageSize` fixed at 100). Adds `turnoverUsd, bets, players, averageBetUsd, trend[], previousRank`. `total` = game count. Categories: `turnover, bets, players, average-bet, climbing`. **`range`** window (default `30d`): valid values `1d, 3d, 7d, 30d, 90d, all` — `1d` ≈ today/last-24h (players/turnover/bets all scale to that window). The detail endpoint takes the same `range` (and returns hourly `series` for `1d`). |
| `GET /api/insights/leaderboards` | Top-N per category in one call. |
| `GET /api/insights/games/{team}/{game}` | **Per-game detail:** 30-day `series[]`, `totals`, `previous`, `ranks[]` per category, `from/to`. |
| `GET /api/insights/publishers/{team}` | A publisher's games. |
| `GET /api/insights/summary`, `/breakdown`, `/pulse` | Aggregate market stats. |
| `GET /api/asset/image/{assetId}` | PNG art for a game/team image id. |

Requires auth (401 without session cookie): `/api/insights/operators`, `/api/orgs`,
`/api/operators`, and everything under `/api/teams/{team}/...` and `/api/admin/...`.

## How a game is launched (needs a logged-in studio session)
1. `GET /api/teams/{team}/games/{game}/play?device=mobile&math=1&front=2`
   → `{url:"https://<team>.live.engine.io/<game>/v<front>/?sessionID=...&rgs_url=rgsd.engine.io&...&demo=true", session}`
2. Browser loads that live URL (the game bundle).
3. `POST https://rgsd.engine.io/wallet/authenticate` `{sessionID, language}`
   → `{balance, config:{minBet,maxBet,betLevels[],gameModes[...costMultiplier]}, user, jurisdiction}`.
   (*Toxic Mess* modes: base, bonus ×100, super_bonus ×200, mystery_bonus ×150,
   super_spin ×5/×20/×50, toxic_spins ×3.)

A public, no-login **share** page exists at `/share/{team}/{game}/{math}/{front}` and its
data at `/api/share/{team}/{game}/{math}/{front}` — but only for games whose creator
published a share link (most 404).

## Full `/api/*` surface seen in the bundle
`/api/users`, `/api/invites/*`, `/api/operators`, `/api/orgs`,
`/api/teams`, `/api/teams/{team}` (+ `/users /games /payments /balance /wallets /graph
/stats /teamStats /locationStats /organisations /profile /support /approvals/... /invites`),
`/api/teams/{team}/games/{game}` (+ `/play /versions /publicVersions /shares /stats /graph
/data/summary /data/distribution /verification /replay`),
`/api/asset/*`, `/api/file/*` (upload/publish math+front), `/api/ai/{models,images}`,
`/api/contracts/*`, `/api/guidelines`, `/api/liveGames`, and a large `/api/admin/*` tree
(betlevels, payments, bans, reviews, support…). Auth: `/auth/permissions/...`, `/auth/logout`,
`/auth/revoke/{github,google,discord}/{id}`. Session via cookies (`logged_in`, `__cf_bm`,
`auth_provider`). GitHub OAuth was the login here.

## The local site
`index.html` calls `/api/insights/directory` directly from the browser (CORS is open),
caches it 6h in localStorage, and offers search (name + provider), sort (rank/name/provider),
and a provider filter. Clicking a slot fetches `/api/insights/games/{team}/{game}` for live
30-day stats, a turnover sparkline, and per-category ranks.
