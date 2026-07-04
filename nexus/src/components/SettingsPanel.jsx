import { useState, useEffect, useCallback } from 'react';
import TerminalConfig from '../config/TerminalConfig.js';

const C = TerminalConfig;

const SETTINGS_KEY = 'nexus-flow-settings';

const DEFAULT_SETTINGS = {
  heatmapDimming: 100,
  heatmapContrast: 1.0,
  imbalanceThreshold: 3.0,
  valueAreaPercent: 70,
  tpoSlotDuration: 30,
  showVolumeProfile: true,
  showTPO: false,
  showImbalance: true,
  showStackedImbalance: true,
  showCellNumbers: true,
  showAbsorption: true,
  showDivergence: true,
  priceScaleMode: 'linear',
};

function loadSettings() {
  try {
    const stored = localStorage.getItem(SETTINGS_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return { ...DEFAULT_SETTINGS, ...parsed };
    }
  } catch (e) {
    // ignore
  }
  return { ...DEFAULT_SETTINGS };
}

function saveSettings(settings) {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch (e) {
    // ignore
  }
}

export default function SettingsPanel({ visible, onClose, heatmapRef, footprintRef }) {
  const [settings, setSettings] = useState(loadSettings);

  useEffect(() => {
    saveSettings(settings);

    if (heatmapRef?.current) {
      heatmapRef.current.dimming = settings.heatmapDimming / 100;
    }
    if (footprintRef?.current) {
      footprintRef.current.showVolumeProfile = settings.showVolumeProfile;
      footprintRef.current.showTPO = settings.showTPO;
      footprintRef.current.showImbalance = settings.showImbalance;
      footprintRef.current.showStackedImbalance = settings.showStackedImbalance;
      footprintRef.current.showCellNumbers = settings.showCellNumbers;
      footprintRef.current.showAbsorption = settings.showAbsorption;
      footprintRef.current.showDivergence = settings.showDivergence;
      footprintRef.current.viewState.priceScaleMode = settings.priceScaleMode || 'linear';
    }
  }, [settings, heatmapRef, footprintRef]);

  const handleChange = useCallback((key, value) => {
    setSettings(prev => ({ ...prev, [key]: value }));
  }, []);

  const handleToggle = useCallback((key) => {
    setSettings(prev => ({ ...prev, [key]: !prev[key] }));
  }, []);

  if (!visible) return null;

  const toggleBtn = (key, label) => (
    <button
      onClick={() => handleToggle(key)}
      style={{
        background: settings[key] ? C.BULLISH : C.BG_PRIMARY,
        color: settings[key] ? C.BG_PRIMARY : C.COLOR_TEXT_MUTED,
        border: `1px solid ${settings[key] ? C.BULLISH : C.COLOR_BORDER}`,
        borderRadius: 3,
        padding: '3px 8px',
        cursor: 'pointer',
        fontSize: 10,
        fontFamily: "'Courier New', monospace",
        minWidth: 50,
      }}
    >
      {settings[key] ? 'ON' : 'OFF'}
    </button>
  );

  return (
    <div style={{
      position: 'absolute',
      right: 0,
      top: 0,
      bottom: 0,
      width: 300,
      background: C.BG_SURFACE,
      borderLeft: `1px solid ${C.COLOR_BORDER}`,
      zIndex: 100,
      overflow: 'auto',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <div style={{
        padding: '12px 16px',
        borderBottom: `1px solid ${C.COLOR_BORDER}`,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span style={{ color: C.COLOR_TEXT_PRIMARY, fontWeight: 'bold', fontSize: 13, fontFamily: "'Courier New', monospace", letterSpacing: 1 }}>
          SETTINGS
        </span>
        <button onClick={onClose} style={{
          background: 'transparent',
          color: C.COLOR_TEXT_MUTED,
          border: 'none',
          cursor: 'pointer',
          fontSize: 16,
          padding: '0 4px',
        }}>
          &times;
        </button>
      </div>

      <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Section title="HEATMAP">
          <SliderRow label="Dimming" value={settings.heatmapDimming} min={0} max={100} step={1}
            onChange={v => handleChange('heatmapDimming', v)} unit="%" />
          <SliderRow label="Contrast" value={Math.round(settings.heatmapContrast * 100)} min={10} max={500} step={10}
            onChange={v => handleChange('heatmapContrast', v / 100)} unit="%" />
        </Section>

        <Section title="FOOTPRINT">
        <InputRow label="Imbalance Threshold" value={settings.imbalanceThreshold} step={0.5}
          onChange={v => handleChange('imbalanceThreshold', parseFloat(v))} />
        <InputRow label="Value Area %" value={settings.valueAreaPercent} step={5}
          onChange={v => handleChange('valueAreaPercent', parseFloat(v))} />
        <SelectRow label="TPO Slot Duration" value={settings.tpoSlotDuration}
          options={[{ value: 15, label: '15 min' }, { value: 30, label: '30 min' }, { value: 60, label: '1 hour' }]}
          onChange={v => handleChange('tpoSlotDuration', parseInt(v, 10))} />
        <SelectRow label="Price Scale" value={settings.priceScaleMode || 'linear'}
          options={[{ value: 'linear', label: 'Linear' }, { value: 'log', label: 'Logarithmic' }, { value: 'sqrt', label: 'Square Root' }]}
          onChange={v => handleChange('priceScaleMode', v)} />
      </Section>

        <Section title="OVERLAYS">
          <ToggleRow label="Volume Profile" toggle={toggleBtn('showVolumeProfile', 'Volume Profile')} />
          <ToggleRow label="TPO" toggle={toggleBtn('showTPO', 'TPO')} />
          <ToggleRow label="Imbalance" toggle={toggleBtn('showImbalance', 'Imbalance')} />
          <ToggleRow label="Stacked Imbalance" toggle={toggleBtn('showStackedImbalance', 'Stacked Imbalance')} />
          <ToggleRow label="Cell Numbers" toggle={toggleBtn('showCellNumbers', 'Cell Numbers')} />
          <ToggleRow label="Absorption" toggle={toggleBtn('showAbsorption', 'Absorption')} />
          <ToggleRow label="Divergence" toggle={toggleBtn('showDivergence', 'Divergence')} />
        </Section>
      </div>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <span style={{ color: C.BULLISH, fontSize: 9, letterSpacing: 2, fontFamily: "'Courier New', monospace" }}>{title}</span>
      {children}
    </div>
  );
}

function SliderRow({ label, value, min, max, step, onChange, unit }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
        <span style={{ fontSize: 11, color: C.COLOR_TEXT_MUTED, fontFamily: "'Courier New', monospace" }}>{label}</span>
        <span style={{ fontSize: 11, color: C.COLOR_TEXT_PRIMARY, fontFamily: "'Courier New', monospace" }}>{value}{unit}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))}
        style={{ width: '100%', accentColor: C.BULLISH }}
      />
    </div>
  );
}

function InputRow({ label, value, step, onChange }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: 11, color: C.COLOR_TEXT_MUTED, fontFamily: "'Courier New', monospace" }}>{label}</span>
      <input type="number" value={value} step={step}
        onChange={e => onChange(e.target.value)}
        style={{
          width: 60,
          background: C.BG_PRIMARY,
          color: C.COLOR_TEXT_PRIMARY,
          border: `1px solid ${C.COLOR_BORDER}`,
          borderRadius: 3,
          padding: '3px 6px',
          fontSize: 11,
          fontFamily: "'Courier New', monospace",
          textAlign: 'right',
        }}
      />
    </div>
  );
}

function SelectRow({ label, value, options, onChange }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: 11, color: C.COLOR_TEXT_MUTED, fontFamily: "'Courier New', monospace" }}>{label}</span>
      <select value={value} onChange={e => onChange(e.target.value)}
        style={{
          background: C.BG_PRIMARY,
          color: C.COLOR_TEXT_PRIMARY,
          border: `1px solid ${C.COLOR_BORDER}`,
          borderRadius: 3,
          padding: '3px 6px',
          fontSize: 11,
          fontFamily: "'Courier New', monospace",
        }}
      >
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function ToggleRow({ label, toggle }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <span style={{ fontSize: 11, color: C.COLOR_TEXT_MUTED, fontFamily: "'Courier New', monospace" }}>{label}</span>
      {toggle}
    </div>
  );
}

export { DEFAULT_SETTINGS, loadSettings };
