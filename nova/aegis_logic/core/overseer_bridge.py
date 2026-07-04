import asyncio
import json
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

from config import OVERSEER_DATA_DIR, OVERSEER_L3_DATA_PATH, OVERSEER_SIGNALS_PATH

class OverseerBridge:
    """
    Direct integration with OVERSEER's data structures
    Reads L3 MBO data and signals from OVERSEER's data directory
    """

    def __init__(self):
        self.data_dir = OVERSEER_DATA_DIR
        self.l3_data_file = OVERSEER_L3_DATA_PATH
        self.signals_file = OVERSEER_SIGNALS_PATH
        self.last_signal = None
        self._watcher_task = None

    async def start(self):
        """Start watching OVERSEER data files"""
        print("[INTEGRATION] Starting OVERSEER bridge...")
        print(f"[INTEGRATION] Data directory: {self.data_dir}")
        print(f"[INTEGRATION] L3 data: {self.l3_data_file}")
        print(f"[INTEGRATION] Signals: {self.signals_file}")

        if not self.data_dir.exists():
            print(f"[INTEGRATION] Creating data directory: {self.data_dir}")
            self.data_dir.mkdir(parents=True, exist_ok=True)

        self._watcher_task = asyncio.create_task(self._watch_signals())
        print("[INTEGRATION] OVERSEER bridge started")

    async def _watch_signals(self):
        """Watch for new signals from OVERSEER"""
        last_modified = 0

        while True:
            try:
                if self.signals_file.exists():
                    modified = self.signals_file.stat().st_mtime
                    if modified > last_modified:
                        last_modified = modified
                        signal = await self._read_latest_signal()
                        if signal:
                            print(f"[INTEGRATION] New signal from OVERSEER: {signal.get('action', 'UNKNOWN')}")
                            self.last_signal = signal
            except Exception as e:
                print(f"[INTEGRATION] Error watching signals: {e}")

            await asyncio.sleep(1)

    async def _read_latest_signal(self) -> Dict[str, Any]:
        """Read latest signal from OVERSEER"""
        try:
            with open(self.signals_file, 'r') as f:
                lines = f.readlines()
                if lines:
                    return json.loads(lines[-1])
        except Exception as e:
            print(f"[INTEGRATION] Error reading signals: {e}")
        return {}

    async def get_overseer_l3_data(self) -> Dict[str, Any]:
        """Get current L3 MBO data from OVERSEER"""
        try:
            if self.l3_data_file.exists():
                with open(self.l3_data_file, 'r') as f:
                    data = json.load(f)
                    return data
        except Exception as e:
            print(f"[INTEGRATION] Error reading L3 data: {e}")
        return {}

    async def write_signal_to_overseer(self, signal: Dict[str, Any]):
        """Write signal back to OVERSEER for logging/tracking"""
        try:
            timestamp = datetime.now().isoformat()
            signal_entry = {
                "timestamp": timestamp,
                "source": "AEGIS",
                **signal
            }

            with open(self.signals_file, 'a') as f:
                f.write(json.dumps(signal_entry) + '\n')

            print(f"[INTEGRATION] Signal written to OVERSEER")
        except Exception as e:
            print(f"[INTEGRATION] Error writing signal: {e}")

    async def get_overseer_framework_scores(self) -> Dict[str, float]:
        """Get current framework scores from OVERSEER"""
        signal = await self._read_latest_signal()
        if signal:
            return signal.get("framework_scores", {})
        return {}

    async def stop(self):
        """Stop OVERSEER bridge"""
        if self._watcher_task:
            self._watcher_task.cancel()
        print("[INTEGRATION] OVERSEER bridge stopped")