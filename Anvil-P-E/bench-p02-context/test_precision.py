import sys
sys.path.append('.')
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
print(f"Sig family: {sig['incident_id'].split('-')[-1]}")
print(f"Target family: {target}")
print("Returned:")
for m in ctx["similar_past_incidents"]:
    print(f"  {m['incident_id']}")
res = score_match(ctx, ds.ground_truth[0])
print(f"Score: {res}")
