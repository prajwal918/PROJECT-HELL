import TerminalConfig from '../config/TerminalConfig.js';

const C = TerminalConfig;

const TOOLS = [
  { id: 'horizontal_line', label: '\u2500', title: 'Horizontal Line' },
  { id: 'trend_line', label: '\u2571', title: 'Trend Line' },
  { id: 'ray', label: '\u2192', title: 'Ray' },
  { id: 'fibonacci_retracement', label: '\u0424', title: 'Fibonacci Retracement' },
  { id: 'eraser', label: '\u2715', title: 'Eraser' },
  { id: 'clear_all', label: '\u2716', title: 'Clear All' },
];

const CURSORS = {
  horizontal_line: 'crosshair',
  trend_line: 'crosshair',
  ray: 'crosshair',
  fibonacci_retracement: 'crosshair',
  eraser: 'pointer',
};

export default function DrawingToolbar({ activeTool, onToolSelect }) {
  const handleToolClick = (tool) => {
    if (tool.id === 'clear_all') {
      onToolSelect('clear_all');
      return;
    }
    if (activeTool === tool.id) {
      onToolSelect(null);
    } else {
      onToolSelect(tool.id);
    }
  };

  return (
    <div style={{
      position: 'absolute',
      top: 28,
      left: 4,
      display: 'flex',
      gap: 2,
      zIndex: 10,
      background: 'rgba(11,14,17,0.92)',
      border: `1px solid ${C.COLOR_BORDER}`,
      borderRadius: 4,
      padding: '3px 4px',
    }}>
      {TOOLS.map(tool => (
        <button
          key={tool.id}
          onClick={() => handleToolClick(tool)}
          title={tool.title}
          style={{
            width: 36,
            height: 36,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: activeTool === tool.id ? 'rgba(38,166,154,0.25)' : 'transparent',
            color: activeTool === tool.id ? C.BULLISH : C.COLOR_TEXT_MUTED,
            border: activeTool === tool.id ? `1px solid ${C.BULLISH}` : `1px solid transparent`,
            borderRadius: 3,
            cursor: 'pointer',
            fontSize: tool.id === 'fibonacci_retracement' ? 14 : 16,
            fontFamily: "'Courier New', monospace",
            padding: 0,
            lineHeight: 1,
          }}
        >
          {tool.label}
        </button>
      ))}
    </div>
  );
}

export { CURSORS };
