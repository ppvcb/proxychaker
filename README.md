# Standalone Proxy Checker Service

A self-contained proxy checker that runs independently on any hosting
(Railway, Render, DigitalOcean, cPanel...) — separate from the shop bot.

## Features
- Multi-protocol check: HTTP / HTTPS / SOCKS4 / SOCKS5 / SOCKS5H
- Parallel high-speed bulk checking (ThreadPoolExecutor)
- Geo location: IP, country (+flag), city, ISP, ping
- Control panel (Mini-App style) to add/run proxies and see live/dead
- Saved proxy groups (JSON, survives restarts)
- API-key protected REST API for external tools

## Deploy on Railway
1. Push this `proxychecker_service/` folder to a new GitHub repo.
2. On Railway, create a New Project → Deploy from GitHub repo → select that repo.
3. Railway auto-detects `Dockerfile` (and `railway.json`).
4. Add a variable (optional, but recommended):
   - `PROXY_API_KEY` → your secret API key (leave empty = no auth)
5. Railway gives you a public HTTPS URL, e.g. `https://proxychecker-production.up.railway.app`.

## Run locally
```
pip install -r requirements.txt
export PROXY_API_KEY=mysecret   # optional
python server.py                 # serves on :8080
```
Open http://localhost:8080

## API
### Health
```
GET /api/health
```
### Check proxies
```
POST /api/check
Header: X-Api-Key: <key>
Body:   {"proxies":["host:port:user:pass","host:port"],"timeout":8}
```
Response: `{ok, total, live, dead, results[], dead_list[]}`

### Save / list groups
```
POST /api/groups/<name>   {"proxies":[...]}   # save/overwrite
GET  /api/groups                               # list all
DELETE /api/groups/<name>                      # delete
```

## Integrate from the shop
In the shop admin Settings → "Proxy Checker" tab:
- set **Base URL** to `https://your-service.up.railway.app`
- set **API Key** to your `PROXY_API_KEY`

When a base URL is set, the shop's proxy checks route to this remote
service; when you clear it, checks fall back to local execution.
