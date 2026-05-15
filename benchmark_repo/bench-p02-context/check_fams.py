import sys
import os
sys.path.append(os.getcwd())
from generator import generate, GenConfig

cfg = GenConfig(seed=42)
ds = generate(cfg)

fams = {}
for e in ds.train_events:
    if e.get("kind") == "incident_signal":
        f = int(e["incident_id"].split("-")[-1])
        fams[f] = fams.get(f, 0) + 1

print(f"Train Incident Families: {fams}")
