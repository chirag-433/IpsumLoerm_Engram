import sys
import os
sys.path.append(os.getcwd())
from adapters.myteam import Engine
from generator import generate, GenConfig
from metrics import score_match

cfg = GenConfig(seed=42)
ds = generate(cfg)
engine = Engine()
engine.ingest(ds.train_events)
engine.ingest(ds.eval_events)

sig = ds.eval_signals[0]
target = ds.ground_truth[0]["family"]
ctx = engine.reconstruct_context(sig)

print(f"Total incidents in engine memory: {len(engine._engine._incidents)}")
fams = {}
for m in engine._engine._incidents.values():
    fams[m.family] = fams.get(m.family, 0) + 1
print(f"Family distribution in memory: {fams}")

print(f"Signal ID: {sig['incident_id']}")
print(f"Target Family: {target}")
print("Matches:")
for m in ctx["similar_past_incidents"]:
    print(f"  {m['incident_id']} (similarity: {m['similarity']})")

res = score_match(ctx, target)
print(f"Score Match Result: {res}")
