import sys
sys.path.append('.')
from adapters.myteam import Engine
from generator import generate, GenConfig
cfg = GenConfig(seed=42)
ds = generate(cfg)
engine = Engine()
engine.ingest(ds.train_events)
engine.ingest(ds.eval_events)

sig = ds.eval_signals[0]
ts = sig["ts"]
print(f"Eval signal TS: {ts}")

fams = {}
for m in engine._engine._incidents.values():
    if m.ts.isoformat() < ts:
        fams[m.family] = fams.get(m.family, 0) + 1

print(f"Past incidents for family 4: {fams.get(4, 0)}")
print(f"All past fams: {fams}")
