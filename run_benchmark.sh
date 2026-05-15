#!/bin/bash
set -e
echo "=== Engram P-02 Quickstart ==="

# Install deps
pip install -r requirements.txt

# Clone harness if not present
if [ ! -d "Anvil-P-E" ]; then
  git clone https://github.com/Sauhard74/Anvil-P-E
fi

# Copy adapter files into harness
cp engine.py Anvil-P-E/bench-p02-context/
cp schema.py Anvil-P-E/bench-p02-context/
cp myteam_adapter.py Anvil-P-E/bench-p02-context/adapters/myteam.py
cp -r engine/ Anvil-P-E/bench-p02-context/engine/
cp -r integrations/ Anvil-P-E/bench-p02-context/integrations/

# Run self-check
cd Anvil-P-E/bench-p02-context
python self_check.py --adapter adapters.myteam:Engine

echo "=== Done ==="
