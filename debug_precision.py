import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Anvil-P-E', 'bench-p02-context'))
sys.path.insert(0, '.')
from engine import PersistentContextEngine, _extract_family
from generator import GenConfig, generate
from metrics import score_match

for seed in [101, 202]:
    cfg = GenConfig(seed=seed)
    ds = generate(cfg)
    engine = PersistentContextEngine()
    engine.ingest(ds.train_events)
    engine.ingest(ds.eval_events)
    
    for sig, gt in zip(ds.eval_signals, ds.ground_truth):
        ctx = engine.reconstruct_context({
            "incident_id": sig["incident_id"],
            "ts": sig["ts"],
            "trigger": sig.get("trigger", ""),
            "service": sig.get("service", ""),
        })
        in_top_k, precision = score_match(ctx, gt, k=5)
        if precision < 1.0:
            target = gt["family"]
            matches = ctx.get("similar_past_incidents", [])[:5]
            print(f"seed={seed} sig={sig['incident_id']} gt_fam={target} prec={precision}")
            for m in matches:
                fam = _extract_family(m["incident_id"])
                print(f"  {'✓' if fam == target else '✗'} {m['incident_id']} fam={fam}")
    engine.close()
