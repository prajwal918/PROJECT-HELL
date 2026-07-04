"""Quick score diagnostics script."""
from backtest.data_loader import load_spot_data
from engine_logic.gates.gate_registry import GateRegistry
from ml.framework_scorer import aggregate_framework_scores
from ml.load_model import predict_trade_quality
from config.instrument_config import InstrumentConfig

ticks = load_spot_data("EURUSD", max_ticks=500)
registry = GateRegistry()
inst = InstrumentConfig.get_instance()

scores = []
fw_samples = []
for i, t in enumerate(ticks):
    inst.enrich_tick(t)
    gs = registry.evaluate(t)
    if gs.get("gate_D") and gs.get("gate_Z7"):
        score = predict_trade_quality(gs)
        fw = aggregate_framework_scores(gs)
        scores.append(score)
        if len(fw_samples) < 3:
            fw_samples.append((score, fw))

print(f"Ticks where gate_D AND gate_Z7 pass: {len(scores)}/{len(ticks)}")
if scores:
    print(f"Score range: {min(scores):.4f} - {max(scores):.4f}")
    print(f"Score mean: {sum(scores)/len(scores):.4f}")
    above_30 = sum(1 for s in scores if s > 0.30)
    above_50 = sum(1 for s in scores if s > 0.50)
    above_65 = sum(1 for s in scores if s > 0.65)
    print(f"Above 0.30: {above_30}, Above 0.50: {above_50}, Above 0.65: {above_65}")
    print("\nSample framework scores:")
    for sc, fw in fw_samples:
        print(f"  score={sc:.4f}")
        for k, v in sorted(fw.items()):
            print(f"    {k}: {v:.4f}")
else:
    print("No ticks passed gate_D + gate_Z7")
