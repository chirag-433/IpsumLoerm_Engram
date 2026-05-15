import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Anvil-P-E', 'bench-p02-context'))
sys.path.insert(0, '.')
from engine import PersistentContextEngine, _extract_family
import generator as gen_mod
import metrics as metrics_mod

for seed in [101, 202, 303, 404]:
    cfg = gen_mod.GenConfig(seed=seed)
    ds = gen_mod.generate(cfg)
    engine = PersistentContextEngine()
    engine.ingest(ds.train_events)
    engine.ingest(ds.eval_events)
    for sig, gt in zip(ds.eval_signals, ds.ground_truth):
        ctx = engine.reconstruct_context(sig, mode='fast')
        in_top_k, precision = metrics_mod.score_match(ctx, gt, k=5)
        if precision < 1.0:
            target = gt['family']
            matches = ctx.get('similar_past_incidents', [])[:5]
            fams = [metrics_mod._family_from_incident_id(m['incident_id']) for m in matches]
            print(f'seed={seed} sig={sig["incident_id"]} gt_fam={target} prec={precision} returned_fams={fams}')
    engine.close()
