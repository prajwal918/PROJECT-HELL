import { useState, useCallback, useEffect, useRef } from 'react';
import { getReplayController } from '../renderer/ReplayController.js';
import TerminalConfig from '../config/TerminalConfig.js';

const C = {
  BG: '#131722',
  BORDER: '#1E222D',
  TEXT: '#E1E4E8',
  TEXT_MUTED: '#787B86',
  BULLISH: '#26A69A',
  BEARISH: '#EF5350',
  ACCENT: '#26A69A',
};

const SPEEDS = [0.25, 0.5, 1, 2, 5, 10];

function formatNs(ns) {
  if (!ns) return '00:00:00';
  const totalSec = Math.floor(ns / 1e9);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export default function ReplayPanel({ visible, ringBuffer }) {
  const [replayState, setReplayState] = useState('idle');
  const [speed, setSpeed] = useState(1);
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [hasRecording, setHasRecording] = useState(false);
  const controllerRef = useRef(null);
  const rafRef = useRef(null);

  useEffect(() => {
    controllerRef.current = getReplayController();
    const ctrl = controllerRef.current;

    ctrl.onStateChange = (s) => setReplayState(s);

    return () => {
      ctrl.destroy();
    };
  }, []);

  useEffect(() => {
    if (!visible) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }

    const tick = () => {
      const ctrl = controllerRef.current;
      if (ctrl) {
        setProgress(ctrl.getProgress());
        setCurrentTime(ctrl.getCurrentTime());
        setDuration(ctrl.getDuration());
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [visible]);

  const handleRecord = useCallback(() => {
    const ctrl = controllerRef.current;
    if (replayState === 'recording') {
      const ticks = ctrl.stopRecording();
      ctrl.saveSession('default', ticks);
      setHasRecording(true);
    } else {
      ctrl.startRecording();
    }
  }, [replayState]);

  const handlePlay = useCallback(async () => {
    const ctrl = controllerRef.current;
    if (replayState === 'playing') {
      ctrl.pausePlayback();
    } else if (replayState === 'paused') {
      ctrl.resumePlayback();
    } else {
      let ticks = null;
      if (hasRecording) {
        const sessions = await ctrl.loadSessions();
        if (sessions.default) ticks = sessions.default.ticks;
      }
      if (!ticks || ticks.length === 0) {
        ticks = ctrl.recordedTicks;
      }
      if (ticks && ticks.length > 0) {
        ctrl.onTick = (tick) => {
          if (ringBuffer && ringBuffer.current) {
            ringBuffer.current.push({
              timestamp_ns: tick.timestamp_ns,
              price: tick.price,
              bid_size: tick.bid_size,
              ask_size: tick.ask_size,
              trade_size: tick.trade_size,
              order_id: tick.order_id,
              action: tick.action,
              side: tick.side,
              flags: tick.flags || 0,
              seq_num: tick.seq_num || 0,
            });
          }
        };
        ctrl.startPlayback(ticks, speed);
      }
    }
  }, [replayState, speed, hasRecording, ringBuffer]);

  const handleSpeedChange = useCallback((e) => {
    const v = parseFloat(e.target.value);
    setSpeed(v);
    if (controllerRef.current) controllerRef.current.setSpeed(v);
  }, []);

  const handleSeek = useCallback((e) => {
    const pct = parseFloat(e.target.value);
    const ctrl = controllerRef.current;
    if (ctrl && ctrl.ticks.length > 0) {
      const firstNs = ctrl.ticks[0].timestamp_ns || 0;
      const dur = ctrl.getDuration();
      ctrl.seekTo(firstNs + dur * pct);
      setProgress(pct);
    }
  }, []);

  if (!visible) return null;

  return (
    <div style={{
      height: 40,
      background: C.BG,
      borderTop: `1px solid ${C.BORDER}`,
      display: 'flex',
      alignItems: 'center',
      padding: '0 12px',
      gap: 10,
      fontFamily: "'Courier New', monospace",
      fontSize: 11,
      color: C.TEXT_MUTED,
      flexShrink: 0,
    }}>
      <button
        onClick={handleRecord}
        style={{
          width: 18, height: 18, borderRadius: '50%',
          background: replayState === 'recording' ? C.BEARISH : 'transparent',
          border: `2px solid ${C.BEARISH}`,
          cursor: 'pointer', padding: 0,
          boxShadow: replayState === 'recording' ? `0 0 8px ${C.BEARISH}` : 'none',
        }}
        title={replayState === 'recording' ? 'Stop Recording' : 'Start Recording'}
      />

      <button
        onClick={handlePlay}
        style={{
          width: 24, height: 24, borderRadius: 3,
          background: replayState === 'playing' ? C.BULLISH : 'transparent',
          border: `1px solid ${C.BULLISH}`,
          cursor: 'pointer', padding: 0, position: 'relative',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
        title={replayState === 'playing' ? 'Pause' : 'Play'}
      >
        {replayState === 'playing' ? (
          <div style={{ display: 'flex', gap: 2 }}>
            <div style={{ width: 3, height: 10, background: C.BG }} />
            <div style={{ width: 3, height: 10, background: C.BG }} />
          </div>
        ) : (
          <div style={{ width: 0, height: 0, borderLeft: '8px solid #26A69A', borderTop: '5px solid transparent', borderBottom: '5px solid transparent', marginLeft: 2 }} />
        )}
      </button>

      <select value={speed} onChange={handleSpeedChange} style={{ background: '#0B0E11', color: C.TEXT, border: `1px solid ${C.BORDER}`, borderRadius: 3, padding: '2px 4px', fontSize: 10, fontFamily: "'Courier New', monospace" }}>
        {SPEEDS.map(s => <option key={s} value={s}>{s}x</option>)}
      </select>

      <input
        type="range"
        min="0"
        max="1"
        step="0.001"
        value={progress}
        onChange={handleSeek}
        style={{ flex: 1, height: 4, accentColor: C.ACCENT, cursor: 'pointer' }}
      />

      <span style={{ minWidth: 70, textAlign: 'right' }}>{formatNs(currentTime)}</span>
      <span style={{ color: C.BORDER }}>/</span>
      <span style={{ minWidth: 70 }}>{formatNs(duration)}</span>

      <span style={{ color: replayState === 'recording' ? C.BEARISH : replayState === 'playing' ? C.BULLISH : C.TEXT_MUTED, fontWeight: 'bold', letterSpacing: 1 }}>
        {replayState.toUpperCase()}
      </span>
    </div>
  );
}
