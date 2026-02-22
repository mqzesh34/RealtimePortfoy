const express = require('express');
const { Server } = require('socket.io');
const http = require('http');
const cors = require('cors');
const fs = require('fs');
const path = require('path');

const PORT = 8000;
const DATA_DIR = path.join(__dirname, 'data');
const PATHS = {
  live: path.join(DATA_DIR, 'live_data.json'),
  history: path.join(DATA_DIR, 'daily_history.json'),
};

const app = express();
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

const server = http.createServer(app);
const io = new Server(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"],
    credentials: true
  },
  allowEIO3: true,
  transports: ['websocket', 'polling']
});

io.on('connection', (socket) => {
  const live = readJSON(PATHS.live);
  const history = readJSON(PATHS.history);
  if (live) socket.emit('priceUpdate', live);
  if (history) socket.emit('historyUpdate', history);
});

const now = () =>
  new Date().toLocaleString('tr-TR', {
    hour12: false,
    timeZone: 'Europe/Istanbul',
  });

const readJSON = (filePath) => {
  try {
    const raw = fs.readFileSync(filePath, 'utf8');
    if (!raw?.trim()) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

const watchFile = (filePath, event, label) => {
  fs.watch(filePath, (eventType) => {
    if (eventType !== 'change') return;
    const data = readJSON(filePath);
    if (!data) return;
    io.emit(event, data);
    console.log(`[${now()}] ${label}`);
  });
};

app.get('/api/live', (req, res) => {
  res.json(readJSON(PATHS.live) ?? []);
});

app.get('/api/history', (req, res) => {
  res.json(readJSON(PATHS.history) ?? []);
});

watchFile(PATHS.live, 'priceUpdate', 'Canlı veriler güncellendi.');
watchFile(PATHS.history, 'historyUpdate', 'Geçmiş veriler güncellendi.');

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[${now()}] Server ${PORT} üzerinde çalışıyor... (Dış erişime açık)`);
});