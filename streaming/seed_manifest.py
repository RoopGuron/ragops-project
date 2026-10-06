# streaming/seed_manifest.py
# (kafka-client-venv) ➜  ragops-project > python3 streaming/seed_manifest.py
# -------------------


import json
from pathlib import Path

CORPUS_DIR = Path("corpus/clean")
MANIFEST_PATH = Path("streaming/.manifest.json")

manifest = {
    p.stem: p.stat().st_mtime
    for p in CORPUS_DIR.glob("*.txt")
}

MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
print(f"Seeded manifest with {len(manifest)} existing docs (no events published).")
