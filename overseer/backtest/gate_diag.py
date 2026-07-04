"""Quick gate diagnostics script."""
from backtest.data_loader import load_spot_data
from engine_logic.gates.gate_registry import GateRegistry
from config.instrument_config import InstrumentConfig

ticks = load_spot_data("EURUSD", max_ticks=100)
registry = GateRegistry()
inst = InstrumentConfig.get_instance()

pass_counts: dict[str, int] = {}
total = 0
gs = {}
for t in ticks:
    inst.enrich_tick(t)
    gs = registry.evaluate(t)
    total += 1
    for k, v in gs.items():
        if v:
            pass_counts[k] = pass_counts.get(k, 0) + 1

print("Total ticks:", total)
print("\nGates that EVER passed:")
for k in sorted(pass_counts.keys()):
    pct = pass_counts[k] / total * 100
    print(f"  {k}: {pass_counts[k]}/{total} ({pct:.1f}%)")

all_gates = list(gs.keys())
never = [g for g in all_gates if g not in pass_counts]
print(f"\nGates that NEVER passed ({len(never)}):")
for g in sorted(never):
    print(f"  {g}")

print(f"\nTotal gates: {len(all_gates)}")
print(f"Ever passed: {len(pass_counts)}")
print(f"Never passed: {len(never)}")
print(f"gate_D: {pass_counts.get('gate_D', 0)}/{total}")
print(f"gate_Z7: {pass_counts.get('gate_Z7', 0)}/{total}")
