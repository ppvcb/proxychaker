# -*- coding: utf-8 -*-
"""
=========================================================
  Standalone Proxy Checker Service
  Railway / any web-hosting ready
=========================================================
A self-contained, deployable proxy checker that runs on its own
host/machine (Railway, Render, DigitalOcean, cPanel…) independent
of the main shop bot. It exposes:

  • A web control panel (Mini-App style) at  /
  • A REST API for external tools at  /api/*
  • API-key protection for every /api/* route

The engine is a self-contained clone of the shop's proxy_checker
core (parse_proxy / test_proxy / bulk_check) so the service runs
with zero dependency on the main project.
"""

from __future__ import annotations
import concurrent.futures
import hmac
import os
import re
import secrets
import time
import json
from urllib.parse import quote

import requests  # required
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

from flask import Flask, jsonify, request, send_from_directory

# ---------------------------------------------------------------
# Config (env vars / Railway variables)
# ---------------------------------------------------------------
# API key resolution order: env PROXY_API_KEY → persisted auto-generated key.
# If neither exists, one is generated on first start and stored in
# data/api_key.txt so it survives restarts. This lets the control panel
# show a ready-to-copy key with zero setup from the user.
API_KEY = os.environ.get("PROXY_API_KEY", "").strip()
_IDENTITY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "api_key.txt")
if not API_KEY:
    try:
        with open(_IDENTITY_FILE, encoding="utf-8") as _fh:
            API_KEY = _fh.read().strip()
    except Exception:
        API_KEY = ""
if not API_KEY:
    API_KEY = secrets.token_hex(16)
    try:
        os.makedirs(os.path.dirname(_IDENTITY_FILE), exist_ok=True)
        with open(_IDENTITY_FILE, "w", encoding="utf-8") as _fh:
            _fh.write(API_KEY)
    except Exception:
        pass

PORT = int(os.environ.get("PORT", "8080"))

app = Flask(__name__, static_folder="static")

# ---------------------------------------------------------------
# Core engine (cloned from proxy_checker.py)
# ---------------------------------------------------------------
_SCHEMES = ("http", "https", "socks5", "socks5h", "socks4")
_HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9\-\._]*[A-Za-z0-9])?|\[[0-9A-Fa-f:.]+\]")

_GEO_URLS = (
    "https://ipwho.is/",
    "https://ip-api.com/json",
    "https://ipinfo.io/json",
    "https://freeipapi.com/api/json",
    "https://api.ipify.org?format=json",
    "https://api.my-ip.io/v2/ip.json",
    "https://httpbin.org/ip",
    "http://ip-api.com/json",
    "http://ipwho.is/",
    "http://api.myip.com",
    "http://checkip.amazonaws.com",
    "http://api.ipify.org?format=json",
    "http://ifconfig.me/ip",
    "http://icanhazip.com",
)


def _is_host(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    parts = s.split(".")
    if len(parts) == 4:
        try:
            return all(0 <= int(p) <= 255 for p in parts)
        except ValueError:
            pass
    return _HOST_RE.fullmatch(s) is not None


def _is_port(s: str) -> bool:
    try:
        return 1 <= int(s.strip()) <= 65535
    except (ValueError, TypeError):
        return False


def parse_proxy(proxy_str: str):
    raw = str(proxy_str or "").strip()
    if not raw:
        return None
    cleaned = re.sub(r'^[^\x00-\x7F\[]+', '', raw).strip()
    if not cleaned:
        return None
    cleaned = re.sub(r'[^\x00-\x7F\]]+$', '', cleaned).strip()
    if not cleaned:
        return None
    scheme = "http"
    body = cleaned
    if "://" in body:
        head, body = body.split("://", 1)
        if head.lower() in _SCHEMES:
            scheme = head.lower()
    elif re.match(r"^(socks5h?|socks4|https?):", body, re.I):
        head, body = body.split(":", 1)
        scheme = head.lower()
        if scheme not in _SCHEMES:
            scheme = "http"
    body = body.strip().strip("/").strip()
    user = pwd = ""
    if "@" in body:
        left, right = body.rsplit("@", 1)
        right_parts = right.split(":")
        left_parts = left.split(":")
        if len(right_parts) == 2 and _is_host(right_parts[0]) and _is_port(right_parts[1]):
            body = right
            if ":" in left:
                user, pwd = left.split(":", 1)
            else:
                user = left
        elif len(left_parts) == 2 and _is_host(left_parts[0]) and _is_port(left_parts[1]):
            body = left
            if ":" in right:
                user, pwd = right.split(":", 1)
            else:
                user = right
        else:
            body = right
            if ":" in left:
                user, pwd = left.split(":", 1)
            else:
                user = left
    elif ":" in body:
        parts = body.split(":")
        if len(parts) == 2:
            pass
        elif len(parts) == 3:
            if _is_host(parts[0]) and _is_port(parts[1]):
                user = parts[2]
                body = ":".join(parts[:2])
            else:
                user, pwd = parts[0], parts[1]
                body = parts[2]
        elif len(parts) == 4:
            p0, p1, p2, p3 = _is_host(parts[0]), _is_port(parts[1]), _is_host(parts[2]), _is_port(parts[3])
            if p0 and p1 and not p3:
                user, pwd = parts[2], parts[3]
                body = ":".join(parts[:2])
            elif p2 and p3 and not p1:
                user, pwd = parts[0], parts[1]
                body = ":".join(parts[2:4])
            elif p0 and p1:
                user, pwd = parts[2], parts[3]
                body = ":".join(parts[:2])
            elif p2 and p3:
                user, pwd = parts[0], parts[1]
                body = ":".join(parts[2:4])
            else:
                body = ":".join(parts[:2])
                user, pwd = parts[2], parts[3]
        elif len(parts) >= 5:
            if _is_port(parts[-1]) and _is_host(parts[-2]):
                host_part = ":".join(parts[-2:])
                cred_part = ":".join(parts[:-2])
                cred_parts = cred_part.split(":", 1)
                user = cred_parts[0]
                pwd = cred_parts[1] if len(cred_parts) > 1 else ""
                body = host_part
            elif _is_host(parts[0]) and _is_port(parts[1]):
                user = parts[2]
                pwd = ":".join(parts[3:])
                body = ":".join(parts[:2])
            else:
                return None
    if ":" not in body:
        return None
    host, port_s = body.rsplit(":", 1)
    host = host.strip().strip("[]")
    try:
        port = int(port_s.strip())
    except (TypeError, ValueError):
        return None
    if not host or not (0 < port < 65536):
        return None
    if not _HOST_RE.fullmatch(host):
        return None
    return {"scheme": scheme, "host": host, "port": port,
            "user": user.strip(), "pass": pwd.strip(), "raw": raw}


def _geo_from(resp, fallback_ip: str, ping: float, headers=None):
    data = None
    try:
        data = resp.json()
    except Exception:
        data = None
    result = None
    if isinstance(data, dict):
        if "origin" in data and not data.get("ip"):
            ip = str(data["origin"]).split(",")[0].strip()
            result = {"ip": ip or fallback_ip, "country": "Unknown", "country_code": "",
                      "city": "Unknown", "isp": "Unknown", "ping": ping}
        elif "connection" in data and isinstance(data["connection"], dict):
            conn = data["connection"]
            result = {"ip": data.get("ip") or fallback_ip,
                      "country": data.get("country") or "Unknown",
                      "country_code": (data.get("country_code") or "").upper(),
                      "city": data.get("city") or "Unknown",
                      "isp": conn.get("isp") or conn.get("org") or "Unknown",
                      "ping": ping}
        elif "org" in data and not data.get("isp"):
            org_raw = data.get("org", "")
            isp_clean = re.sub(r'^AS\d+\s*', '', org_raw).strip() or org_raw or "Unknown"
            result = {"ip": data.get("ip") or fallback_ip,
                      "country": data.get("country") or "Unknown",
                      "country_code": (data.get("country") or "").upper()[:2],
                      "city": data.get("city") or "Unknown",
                      "isp": isp_clean, "ping": ping}
        else:
            country = data.get("country") or data.get("country_name") or ""
            code = data.get("countryCode") or data.get("country_code") or ""
            isp = (data.get("isp") or data.get("org") or data.get("as") or
                   data.get("asname") or "Unknown")
            isp = re.sub(r'^AS\d+\s*', '', str(isp)).strip() or isp
            result = {"ip": data.get("query") or data.get("ip") or fallback_ip,
                      "country": country or "Unknown",
                      "country_code": (code or "").upper(),
                      "city": data.get("city") or "Unknown",
                      "isp": isp, "ping": ping}
    if result is None:
        try:
            ip = resp.text.strip()
        except Exception:
            ip = ""
        if re.fullmatch(r"[0-9A-Fa-f.:]{3,45}", ip or ""):
            result = {"ip": ip, "country": "Unknown", "country_code": "",
                      "city": "Unknown", "isp": "Unknown", "ping": ping}
    return result


def _socks_available():
    try:
        import socks  # noqa
        return True
    except Exception:
        return False


def test_proxy(proxy_str: str, timeout: int = 30):
    parsed = parse_proxy(proxy_str)
    if not parsed:
        return False, "invalid format"
    auth = ""
    if parsed["user"]:
        auth = f"{quote(parsed['user'], safe='')}:{quote(parsed['pass'], safe='')}@"
    hostport = f"{parsed['host']}:{parsed['port']}"
    schemes = []
    specified = parsed["scheme"].lower()
    has_socks = _socks_available()
    if specified in ("socks5", "socks5h"):
        if has_socks:
            schemes += ["socks5h", "socks5"]
        schemes += ["http", "https"]
    elif specified == "socks4":
        if has_socks:
            schemes += ["socks4"]
        schemes += ["http", "https"]
    elif specified == "https":
        schemes += ["https", "http"]
        if has_socks:
            schemes += ["socks5h"]
    else:
        schemes += ["http", "https"]
        if has_socks:
            schemes += ["socks5h", "socks5"]
    seen = set()
    schemes = [s for s in schemes if not (s in seen or seen.add(s))]
    deadline = time.time() + 45
    last_err = "dead"
    found_ip = ""
    for scheme in schemes:
        if time.time() > deadline:
            break
        proxy_url = f"{scheme}://{auth}{hostport}"
        proxies = {"http": proxy_url, "https": proxy_url}
        for url in _GEO_URLS:
            left = deadline - time.time()
            if left <= 1.5:
                break
            per_timeout = min(timeout, max(5, int(left * 0.7)))
            t0 = time.time()
            try:
                resp = requests.get(url, proxies=proxies, timeout=per_timeout,
                                    verify=False, allow_redirects=True,
                                    headers={"User-Agent": "Mozilla/5.0"})
                ping = round((time.time() - t0) * 1000, 1)
                if resp.status_code == 200:
                    geo = _geo_from(resp, parsed["host"], ping, resp.headers)
                    if geo:
                        proto = scheme.upper()
                        if proto == "SOCKS5H":
                            proto = "SOCKS5"
                        geo["protocol"] = proto
                        if geo.get("country") == "Unknown" and geo.get("ip") and geo["ip"] != parsed["host"]:
                            found_ip = geo["ip"]
                        return True, geo
                elif resp.status_code in (407, 401):
                    last_err = "auth"
                    break
            except requests.exceptions.ProxyError:
                last_err = "proxy_error"
            except requests.exceptions.ConnectTimeout:
                last_err = "timeout"
            except requests.exceptions.ReadTimeout:
                last_err = "timeout"
            except requests.exceptions.Timeout:
                last_err = "timeout"
            except requests.exceptions.SSLError:
                continue
            except requests.exceptions.ConnectionError:
                last_err = "conn_error"
            except requests.exceptions.InvalidSchema:
                break
            except Exception:
                continue
    if found_ip:
        return True, {"ip": found_ip, "country": "Unknown", "country_code": "",
                      "city": "Unknown", "isp": "Unknown", "ping": 999, "protocol": "HTTP"}
    return False, last_err


def bulk_check(proxy_list, timeout=8, max_workers=10):
    clean = [p.strip() for p in proxy_list if p.strip()]
    if not clean:
        return [], 0
    live = []
    dead = 0
    workers = min(max_workers, max(1, len(clean)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(test_proxy, p, timeout): p for p in clean}
        for fut in concurrent.futures.as_completed(futs):
            p = futs[fut]
            try:
                ok, data = fut.result()
                if ok and isinstance(data, dict):
                    live.append((p, data))
                else:
                    dead += 1
            except Exception:
                dead += 1
    order = {p: i for i, p in enumerate(clean)}
    live.sort(key=lambda it: order.get(it[0], 999999))
    return live, dead


# ---------------------------------------------------------------
# Auth
# ---------------------------------------------------------------
def key_ok():
    if not API_KEY:
        return True
    supplied = (request.headers.get("X-Api-Key") or "").strip()
    if not supplied:
        auth_header = (request.headers.get("Authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            supplied = auth_header[7:].strip()
    if not supplied:
        return False
    return hmac.compare_digest(supplied, API_KEY)


def require_key(f):
    def wrapper(*a, **kw):
        if not key_ok():
            return jsonify({"ok": False, "error": "Unauthorized"}), 401
        return f(*a, **kw)
    wrapper.__name__ = f.__name__
    return wrapper


# ---------------------------------------------------------------
# Storage for saved proxy lists (simple JSON, survives restarts)
# ---------------------------------------------------------------
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "proxies.json")


def _load_data():
    try:
        with open(DATA_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"groups": {}, "last_result": None}


def _save_data(data):
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ---------------------------------------------------------------
# Control panel
# ---------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---------------------------------------------------------------
# API
# ---------------------------------------------------------------
@app.route("/api/health")
def health():
    return jsonify({"ok": True, "service": "proxy-checker", "api_key_set": bool(API_KEY)})


@app.route("/api/key")
def get_key():
    """Return the current API key (for the control panel's copy box)."""
    return jsonify({"ok": True, "key": API_KEY})


@app.route("/api/check", methods=["POST"])
@require_key
def api_check():
    """Check proxies. Body: {"proxies": [...] , "timeout": 8}"""
    body = request.get_json(force=True, silent=True) or {}
    raw = body.get("proxies") or []
    if isinstance(raw, str):
        raw = [l for l in raw.splitlines() if l.strip()]
    if not isinstance(raw, list) or not raw:
        return jsonify({"ok": False, "error": "proxies must be a non-empty list"}), 400
    proxies = [str(p).strip() for p in raw if str(p).strip()]
    if not proxies:
        return jsonify({"ok": False, "error": "No proxies provided"}), 400
    proxies = proxies[:500]
    timeout = max(3, min(20, int(body.get("timeout") or 8)))
    live, dead = bulk_check(proxies, timeout=timeout, max_workers=12)
    order = {p: i for i, p in enumerate(proxies)}
    results = []
    for p, geo in sorted(live, key=lambda it: order.get(it[0], 999999)):
        results.append({"proxy": p, "alive": True,
                        "ip": geo.get("ip"), "country": geo.get("country"),
                        "country_code": geo.get("country_code"),
                        "city": geo.get("city"), "isp": geo.get("isp"),
                        "ping_ms": geo.get("ping"), "protocol": geo.get("protocol")})
    live_set = {r["proxy"] for r in results}
    dead_list = [p for p in proxies if p not in live_set]
    data = _load_data()
    data["last_result"] = {"total": len(proxies), "live": len(results),
                           "dead": len(dead_list), "time": time.time()}
    _save_data(data)
    return jsonify({"ok": True, "total": len(proxies), "live": len(results),
                    "dead": len(dead_list), "results": results, "dead_list": dead_list})


@app.route("/api/groups", methods=["GET"])
@require_key
def api_groups():
    data = _load_data()
    groups = data.get("groups") or {}
    return jsonify({"ok": True, "groups": groups})


@app.route("/api/groups/<name>", methods=["POST"])
@require_key
def api_save_group(name):
    body = request.get_json(force=True, silent=True) or {}
    proxies = body.get("proxies") or []
    if isinstance(proxies, str):
        proxies = [l for l in proxies.splitlines() if l.strip()]
    data = _load_data()
    data.setdefault("groups", {})[name] = [str(p).strip() for p in proxies if str(p).strip()]
    _save_data(data)
    return jsonify({"ok": True, "saved": name})


@app.route("/api/groups/<name>", methods=["DELETE"])
@require_key
def api_delete_group(name):
    data = _load_data()
    data.setdefault("groups", {}).pop(name, None)
    _save_data(data)
    return jsonify({"ok": True})


# ---------------------------------------------------------------
# Run
# ---------------------------------------------------------------
if __name__ == "__main__":
    from werkzeug.serving import run_simple
    run_simple("0.0.0.0", PORT, app, use_reloader=False, threaded=True)
