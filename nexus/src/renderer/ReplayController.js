const DB_NAME = 'nexus_replay';
const STORE_NAME = 'sessions';
const DB_KEY = 'nexus_replay_sessions';

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export class ReplayController {
  constructor() {
    this.state = 'idle';
    this.ticks = [];
    this.recordedTicks = [];
    this.playbackIdx = 0;
    this.speed = 1;
    this.timerId = null;
    this.onTick = null;
    this.onStateChange = null;
    this._startTime = 0;
    this._startNs = 0;
  }

  _setState(s) {
    this.state = s;
    if (this.onStateChange) this.onStateChange(s);
  }

  startRecording() {
    this.recordedTicks = [];
    this._setState('recording');
  }

  stopRecording() {
    this._setState('idle');
    return this.recordedTicks;
  }

  async saveSession(name, ticks) {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readwrite');
    const store = tx.objectStore(STORE_NAME);

    const result = await new Promise((resolve, reject) => {
      const getReq = store.get(DB_KEY);
      getReq.onsuccess = () => {
        const sessions = getReq.result || {};
        sessions[name] = { ticks, savedAt: Date.now() };
        const putReq = store.put(sessions, DB_KEY);
        putReq.onsuccess = () => resolve();
        putReq.onerror = () => reject(putReq.error);
      };
      getReq.onerror = () => reject(getReq.error);
    });

    db.close();
    return result;
  }

  async loadSessions() {
    const db = await openDB();
    const tx = db.transaction(STORE_NAME, 'readonly');
    const store = tx.objectStore(STORE_NAME);
    const result = await new Promise((resolve, reject) => {
      const req = store.get(DB_KEY);
      req.onsuccess = () => resolve(req.result || {});
      req.onerror = () => reject(req.error);
    });
    db.close();
    return result;
  }

  startPlayback(ticks, speed = 1) {
    if (this.timerId) {
      clearTimeout(this.timerId);
      this.timerId = null;
    }
    this.ticks = ticks;
    this.playbackIdx = 0;
    this.speed = speed;
    this._setState('playing');
    this._playbackLoop();
  }

  _playbackLoop() {
    if (this.state !== 'playing') return;
    if (this.playbackIdx >= this.ticks.length) {
      this._setState('idle');
      return;
    }

    const tick = this.ticks[this.playbackIdx];
    if (this.onTick) this.onTick(tick);
    this.playbackIdx++;

    let delay = 1;
    if (this.ticks.length > 1 && this.playbackIdx < this.ticks.length) {
      const cur = this.ticks[this.playbackIdx - 1].timestamp_ns || 0;
      const next = this.ticks[this.playbackIdx].timestamp_ns || 0;
      const nsDiff = next - cur;
      if (nsDiff > 0) {
        delay = Math.max(1, (nsDiff / 1e6) / this.speed);
      }
    }

    this.timerId = setTimeout(() => this._playbackLoop(), delay);
  }

  pausePlayback() {
    if (this.state === 'playing') {
      if (this.timerId) {
        clearTimeout(this.timerId);
        this.timerId = null;
      }
      this._setState('paused');
    }
  }

  resumePlayback() {
    if (this.state === 'paused') {
      this._setState('playing');
      this._playbackLoop();
    }
  }

  seekTo(timestampNs) {
    let idx = 0;
    for (let i = 0; i < this.ticks.length; i++) {
      if (this.ticks[i].timestamp_ns <= timestampNs) idx = i;
      else break;
    }
    this.playbackIdx = idx;
  }

  setSpeed(multiplier) {
    this.speed = multiplier;
  }

  getProgress() {
    if (!this.ticks.length) return 0;
    return this.playbackIdx / this.ticks.length;
  }

  getCurrentTime() {
    if (!this.ticks.length || this.playbackIdx === 0) return null;
    const tick = this.ticks[Math.min(this.playbackIdx - 1, this.ticks.length - 1)];
    return tick.timestamp_ns || 0;
  }

  getDuration() {
    if (!this.ticks.length) return 0;
    const first = this.ticks[0].timestamp_ns || 0;
    const last = this.ticks[this.ticks.length - 1].timestamp_ns || 0;
    return last - first;
  }

  destroy() {
    if (this.timerId) {
      clearTimeout(this.timerId);
      this.timerId = null;
    }
    this._setState('idle');
  }
}

let instance = null;

export function getReplayController() {
  if (!instance) {
    instance = new ReplayController();
  }
  return instance;
}
