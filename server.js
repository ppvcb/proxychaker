// server.js — Bot Hosting Panel entry point
// Express HTTP API + static web UI + Socket.IO for live logs.
require('dotenv').config();

// compiled Python extensions (.so files) খুঁজে পেতে LD_LIBRARY_PATH সেট করো
// grpc, numpy, cryptography ইত্যাদি Nix store থেকে libstdc++ খোঁজে
if (process.platform !== 'win32') {
  const { execSync } = require('child_process');
  const pathMod = require('path');
  try {
    const libPaths = new Set(['/usr/lib', '/usr/local/lib', '/lib', '/lib64', '/usr/lib64']);

    // Nix store-এ libstdc++ খোঁজো (সবচেয়ে reliable)
    try {
      const nixLibs = execSync(
        'find /nix/store -name "libstdc++.so.6" 2>/dev/null | head -5',
        { encoding: 'utf8', shell: true, timeout: 5000 }
      ).trim();
      if (nixLibs) nixLibs.split('\n').filter(Boolean)
        .forEach(p => libPaths.add(pathMod.dirname(p)));
    } catch (_) {}

    // gcc -print-file-name
    try {
      const gccLib = execSync('gcc -print-file-name=libstdc++.so.6 2>/dev/null', {
        encoding: 'utf8', shell: true, timeout: 3000,
      }).trim();
      if (gccLib && gccLib !== 'libstdc++.so.6' && gccLib.startsWith('/'))
        libPaths.add(pathMod.dirname(gccLib));
    } catch (_) {}

    // ldconfig
    try {
      const ldOut = execSync('ldconfig -p 2>/dev/null | grep libstdc++ | head -3', {
        encoding: 'utf8', shell: true, timeout: 3000,
      }).trim();
      ldOut.split('\n').forEach(line => {
        const m = line.match(/=>\s+(.+)/);
        if (m) libPaths.add(pathMod.dirname(m[1].trim()));
      });
    } catch (_) {}

    const existing = (process.env.LD_LIBRARY_PATH || '').split(':').filter(Boolean);
    const merged = [...new Set([...libPaths, ...existing])].join(':');
    if (merged) {
      process.env.LD_LIBRARY_PATH = merged;
      console.log(`[boot] LD_LIBRARY_PATH: ${[...libPaths].length} lib paths set`);
    }
  } catch (_) {}
}

const http = require('http');
const path = require('path');
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const { Server } = require('socket.io');

const config = require('./src/config');
const store = require('./db/store');
const pm = require('./src/processManager');
const { router: authRouter, ensureAdminBootstrap, requireAuth } = require('./src/auth');
const botsRouter = require('./src/routes/bots');
const deployRouter = require('./src/routes/deploy');
const statsRouter = require('./src/routes/stats');
const aiRouter = require('./src/routes/ai');
const { ensurePythonAndPip } = require('./src/setupPython');

// ---------- App ----------
const app = express();
app.set('trust proxy', 1); // Trust first-hop proxy (Cloud Run, reverse proxies)
const server = http.createServer(app);
const io = new Server(server, { path: '/socket.io', cors: { origin: '*' } });

// ---------- Security Headers ----------
app.use(helmet({
  contentSecurityPolicy: false, // SPA frontend-এর জন্য relax করা
  crossOriginEmbedderPolicy: false,
}));

// ---------- Rate Limiting ----------
// Login/Register: brute-force রোধ করো
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 মিনিট
  max: 20,
  message: { error: 'অনেকবার চেষ্টা করা হয়েছে। ১৫ মিনিট পর আবার চেষ্টা করুন।' },
  standardHeaders: true,
  legacyHeaders: false,
});

// API general: প্রতি মিনিটে ১০০ request
const apiLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 200,
  message: { error: 'Too many requests. Please slow down.' },
  standardHeaders: true,
  legacyHeaders: false,
  skip: (req) => req.path === '/health', // health check skip
});

app.use(cors());
app.use(express.json({ limit: '2mb' }));       // body size limit
app.use(express.urlencoded({ extended: true, limit: '2mb' }));
app.use('/api', apiLimiter);
app.use('/api/auth/login', authLimiter);
app.use('/api/auth/register', authLimiter);

// ---------- Socket.IO: authenticate + join bot rooms ----------
const jwt = require('jsonwebtoken');
io.use((socket, next) => {
  const token = socket.handshake.auth?.token || socket.handshake.query?.token;
  const apiKey = socket.handshake.auth?.apiKey || socket.handshake.query?.apiKey;
  try {
    let user = null;
    if (apiKey) user = store.getUserByKey(apiKey);
    else if (token) {
      const payload = jwt.verify(token, config.jwtSecret);
      user = store.getUserById(payload.sub);
    }
    if (!user) return next(new Error('Unauthorized'));
    socket.data.user = user;
    next();
  } catch (e) {
    next(new Error('Unauthorized'));
  }
});
io.on('connection', (socket) => {
  // ইউজারের সব বটের status room-এ auto-join করো
  const userBots = store.getBotsByUser(socket.data.user.id);
  if (socket.data.user.is_admin) {
    // admin সব বটের update পাবে
    store.getAllBots().forEach(b => socket.join(`bot:${b.id}`));
  } else {
    userBots.forEach(b => socket.join(`bot:${b.id}`));
  }

  socket.on('subscribe', (botId) => {
    const bot = store.getBot(botId);
    if (!bot) return;
    if (bot.user_id !== socket.data.user.id && !socket.data.user.is_admin) return;
    socket.join(`bot:${botId}`);
    // send last N lines as catch-up
    const recent = store.getLogs(botId, 0, 200);
    socket.emit('history', { botId, logs: recent });
  });
  socket.on('unsubscribe', (botId) => socket.leave(`bot:${botId}`));
});

pm.setIO(io);

// ---------- Public health ----------
app.get('/health', (req, res) => res.json({ ok: true, uptime: process.uptime() }));

// ---------- API routes ----------
app.use('/api/auth', authRouter);
app.use('/api/bots', requireAuth, botsRouter);
app.use('/api/deploy', requireAuth, deployRouter);
app.use('/api/stats', requireAuth, statsRouter);
app.use('/api/ai', requireAuth, aiRouter);

// catch-all API 404
app.use('/api', (req, res) => res.status(404).json({ error: 'Not found' }));

// ---------- Static web UI ----------
app.use(express.static(path.join(__dirname, 'public')));
// SPA-ish fallback: any non-file GET returns index.html (so /#/dashboard works)
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ---------- Graceful shutdown ----------
function shutdown(signal) {
  console.log(`\n[shutdown] ${signal} received, stopping bots...`);
  pm.stopAll();
  setTimeout(() => process.exit(0), 800);
}
process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));

// ---------- Boot ----------
ensureAdminBootstrap();
server.listen(config.port, () => {
  console.log(`\n╔════════════════════════════════════════════╗`);
  console.log(`║  🚀 Bot Hosting Panel running              ║`);
  console.log(`║  → Web UI:  http://localhost:${config.port}`);
  console.log(`║  → API:     http://localhost:${config.port}/api`);
  console.log(`╚════════════════════════════════════════════╝\n`);
  
  // Run python/pip self-healing in the background
  ensurePythonAndPip().catch(err => {
    console.error('[setup-python] Error running python/pip self-healing setup:', err);
  });
});
