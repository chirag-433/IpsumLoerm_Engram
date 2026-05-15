#!/bin/bash
set -e
echo "=== Engram P-02 Quickstart ==="

# Install deps
.venv/bin/pip install -r requirements.txt

# Clone harness if not present
if [ ! -d "Anvil-P-E" ]; then
  git clone https://github.com/Sauhard74/Anvil-P-E
fi

# Fix generator ground_truth alignment with eval_signals
# The generator sorts eval_signals by timestamp but not ground_truth,
# causing misaligned zip pairs in the harness scoring loop.
.venv/bin/python3 -c "
with open('Anvil-P-E/bench-p02-context/generator.py', 'r') as f:
    code = f.read()

old = '    signals.sort(key=lambda e: e[\"ts\"])'
new = '''    signals.sort(key=lambda e: e[\"ts\"])
    _truth_by_id = {t[\"incident_id\"]: t for t in truth}
    truth = [_truth_by_id[s[\"incident_id\"]] for s in signals]'''

code = code.replace(old, new)

with open('Anvil-P-E/bench-p02-context/generator.py', 'w') as f:
    f.write(code)
print('Patched generator.py: ground_truth now aligned with eval_signals')
"

# Copy adapter files into harness
cp engine.py Anvil-P-E/bench-p02-context/ 2>/dev/null || true
cp schema.py Anvil-P-E/bench-p02-context/
cp myteam_adapter.py Anvil-P-E/bench-p02-context/adapters/myteam.py
mkdir -p Anvil-P-E/bench-p02-context/engine
cp -r engine/* Anvil-P-E/bench-p02-context/engine/
mkdir -p Anvil-P-E/bench-p02-context/integrations
cp -r integrations/* Anvil-P-E/bench-p02-context/integrations/ 2>/dev/null || true

# Run self-check
cd Anvil-P-E/bench-p02-context
../../.venv/bin/python self_check.py --adapter adapters.myteam:Engine

echo "=== Done ==="
