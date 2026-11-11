# 🤖 Bot Hosting Panel

Python / Node.js / Bash বট হোস্ট করার জন্য সম্পূর্ণ প্যানেল।  
Web UI + REST API — দুটো দিয়েই সব কিছু করা যায়।

---

## 🚀 Quick Start

### ১. Deploy করুন (প্রথমবার)

```bash
curl -X POST https://YOUR_DOMAIN/api/deploy \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@bot.py" \
  -F "name=My Bot"
```

**Response:**
```json
{
  "ok": true,
  "botId": "abc123-...",
  "apiKey": "YOUR_API_KEY",
  "bot": { "id": "abc123-...", "name": "My Bot", "status": "running", ... },
  "endpoints": {
    "start":   { "method": "POST",   "url": "https://YOUR_DOMAIN/api/bots/abc123-.../start" },
    "stop":    { "method": "POST",   "url": "https://YOUR_DOMAIN/api/bots/abc123-.../stop" },
    "restart": { "method": "POST",   "url": "https://YOUR_DOMAIN/api/bots/abc123-.../restart" },
    "logs":    { "method": "GET",    "url": "https://YOUR_DOMAIN/api/bots/abc123-.../logs" },
    "delete":  { "method": "DELETE", "url": "https://YOUR_DOMAIN/api/bots/abc123-..." }
  }
}
```

> **Deploy করলেই `botId` পাবেন** — এই ID দিয়ে নিচের সব API call করুন।

---

## 🔑 Authentication

সব API call-এ এই দুটোর যেকোনো একটা দিন:

| পদ্ধতি | Header |
|--------|--------|
| API Key | `X-API-Key: YOUR_API_KEY` |
| JWT Token | `Authorization: Bearer YOUR_JWT_TOKEN` |

API Key পাবেন → Web Panel → Dashboard → "আপনার API Key" সেকশনে।

---

## 📡 সব API Endpoint

**Base URL:** `https://YOUR_DOMAIN`

### Auth

| Method | Endpoint | কাজ |
|--------|----------|-----|
| `POST` | `/api/auth/register` | নতুন একাউন্ট |
| `POST` | `/api/auth/login` | লগইন → JWT token |
| `GET`  | `/api/auth/me` | নিজের তথ্য |
| `POST` | `/api/auth/regenerate-key` | নতুন API Key |

---

### Stats (সার্ভার রিসোর্স)

| Method | Endpoint | কাজ |
|--------|----------|-----|
| `GET` | `/api/stats` | CPU, RAM, uptime, চলমান বটের memory |

**Response উদাহরণ:**
```json
{
  "server": {
    "cpuCores": 4,
    "cpuPercent": 23.5,
    "mem": { "totalFmt": "8.00 GB", "usedFmt": "5.2 GB", "percent": 65.0 },
    "panelMem": { "rssFmt": "45.2 MB" },
    "uptimeFmt": "2h 30m"
  },
  "bots": {
    "total": 3, "running": 2, "totalMemMB": 120.5,
    "list": [{ "name": "My Bot", "pid": 1234, "memMB": 85.2, "uptimeSec": 3600 }]
  }
}
```

---

### Deploy

| Method | Endpoint | কাজ |
|--------|----------|-----|
| `POST` | `/api/deploy` | বট আপলোড + চালু (botId পাবেন) |
| `POST` | `/api/deploy/:botId/update` | কোড আপডেট + অটো-রিস্টার্ট |

**Deploy করার সময় যা পাঠাতে পারেন:**

```bash
curl -X POST https://YOUR_DOMAIN/api/deploy \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@bot.py" \
  -F "name=My Telegram Bot" \
  -F "autoRestart=1" \
  -F "requirements=pyTelegramBotAPI\nrequests" \
  -F "env_BOT_TOKEN=12345:ABC..." \
  -F "start=1"
```

**কোড আপডেট করুন:**

```bash
curl -X POST https://YOUR_DOMAIN/api/deploy/BOT_ID/update \
  -H "X-API-Key: YOUR_API_KEY" \
  -F "file=@bot_new.py"
```

---

### বট কন্ট্রোল (সব ক্ষেত্রে `BOT_ID` লাগবে)

| Method | Endpoint | কাজ |
|--------|----------|-----|
| `GET`    | `/api/bots` | সব বটের লিস্ট |
| `GET`    | `/api/bots/:botId` | একটি বটের বিস্তারিত |
| `POST`   | `/api/bots/:botId/start` | বট চালু করুন |
| `POST`   | `/api/bots/:botId/stop` | বট বন্ধ করুন |
| `POST`   | `/api/bots/:botId/restart` | বট রিস্টার্ট করুন |
| `PATCH`  | `/api/bots/:botId` | সেটিংস আপডেট করুন |
| `DELETE` | `/api/bots/:botId` | বট ডিলিট করুন |

---

### লগ

| Method | Endpoint | কাজ |
|--------|----------|-----|
| `GET`    | `/api/bots/:botId/logs` | লগ দেখুন |
| `GET`    | `/api/bots/:botId/logs/download` | লগ .txt ডাউনলোড |
| `DELETE` | `/api/bots/:botId/logs` | লগ মুছুন |

লগ query params: `?limit=500&after=0`

---

### ফাইল এডিটর

| Method | Endpoint | কাজ |
|--------|----------|-----|
| `GET` | `/api/bots/:botId/files` | ফাইল লিস্ট |
| `GET` | `/api/bots/:botId/files?file=main.py` | ফাইলের কোড পড়ুন |
| `PUT` | `/api/bots/:botId/files` | ফাইল সেভ করুন |
| `GET` | `/api/bots/:botId/download` | সব ফাইল .zip ডাউনলোড |

---

## 💡 ব্যবহারের উদাহরণ

### Python দিয়ে বট কন্ট্রোল

```python
import requests

BASE_URL = "https://YOUR_DOMAIN"
API_KEY  = "YOUR_API_KEY"
BOT_ID   = "abc123-..."  # deploy response থেকে পাওয়া

headers = {"X-API-Key": API_KEY}

# বট চালু
requests.post(f"{BASE_URL}/api/bots/{BOT_ID}/start", headers=headers)

# বট বন্ধ
requests.post(f"{BASE_URL}/api/bots/{BOT_ID}/stop", headers=headers)

# বট রিস্টার্ট
requests.post(f"{BASE_URL}/api/bots/{BOT_ID}/restart", headers=headers)

# লগ দেখুন
logs = requests.get(f"{BASE_URL}/api/bots/{BOT_ID}/logs", headers=headers).json()
for log in logs["logs"]:
    print(f"[{log['stream']}] {log['text']}")

# বটের status
info = requests.get(f"{BASE_URL}/api/bots/{BOT_ID}", headers=headers).json()
print(info["bot"]["status"])  # "running" বা "stopped"

# কোড আপডেট + রিস্টার্ট
with open("bot_new.py", "rb") as f:
    requests.post(
        f"{BASE_URL}/api/deploy/{BOT_ID}/update",
        headers=headers,
        files={"file": f}
    )

# বট ডিলিট
requests.delete(f"{BASE_URL}/api/bots/{BOT_ID}", headers=headers)
```

### curl দিয়ে

```bash
API_KEY="YOUR_API_KEY"
BOT_ID="abc123-..."
BASE="https://YOUR_DOMAIN"

# চালু
curl -X POST "$BASE/api/bots/$BOT_ID/start" -H "X-API-Key: $API_KEY"

# বন্ধ
curl -X POST "$BASE/api/bots/$BOT_ID/stop" -H "X-API-Key: $API_KEY"

# রিস্টার্ট
curl -X POST "$BASE/api/bots/$BOT_ID/restart" -H "X-API-Key: $API_KEY"

# লগ দেখুন (শেষ ১০০ লাইন)
curl "$BASE/api/bots/$BOT_ID/logs?limit=100" -H "X-API-Key: $API_KEY"

# সেটিংস আপডেট (env variable যোগ)
curl -X PATCH "$BASE/api/bots/$BOT_ID" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"autoRestart": true, "env": {"BOT_TOKEN": "12345:ABC..."}}'

# ডিলিট
curl -X DELETE "$BASE/api/bots/$BOT_ID" -H "X-API-Key: $API_KEY"
```

---

## ⚙️ সেটিংস আপডেট (PATCH)

```bash
curl -X PATCH "https://YOUR_DOMAIN/api/bots/BOT_ID" \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "নতুন নাম",
    "autoRestart": true,
    "env": {
      "BOT_TOKEN": "12345:ABC...",
      "WEBHOOK_URL": "https://..."
    }
  }'
```

---

## 🌐 Environment Variables (সার্ভার কনফিগ)

| Variable | Default | কাজ |
|----------|---------|-----|
| `PORT` | `3000` | সার্ভার পোর্ট |
| `JWT_SECRET` | random | JWT signing key |
| `ADMIN_USERNAME` | `admin` | প্রথম admin-এর নাম |
| `ADMIN_PASSWORD` | `admin123` | প্রথম admin-এর পাসওয়ার্ড |
| `DISABLE_SIGNUP` | `false` | নতুন রেজিস্ট্রেশন বন্ধ রাখতে |
| `MAX_UPLOAD_MB` | `50` | সর্বোচ্চ ফাইল সাইজ |
| `DATA_DIR` | `./data` | ডেটা ফোল্ডার |

---

## 📦 Supported Languages

| Language | Extension | Runtime |
|----------|-----------|---------|
| Python | `.py` | `python3` / `python` |
| Node.js | `.js` / `.mjs` | `node` |
| Bash | `.sh` | `bash` |
