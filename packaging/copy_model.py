"""Package only the selected default model's blobs, not every development model."""
import json
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nook.local_ai import MODEL

target = Path(sys.argv[1]).resolve()
source = Path('vendor/models').resolve()
name, tag = MODEL.split(':')
relative = Path('manifests/registry.ollama.ai/library') / name / tag
manifest = source / relative
data = json.loads(manifest.read_text())
(target / relative).parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(manifest, target / relative)
(target / 'blobs').mkdir(exist_ok=True)
for row in [data['config']] + data['layers']:
    name = row['digest'].replace(':', '-')
    if not name.startswith('sha256-') or '/' in name or '\\' in name:
        raise ValueError('Invalid model blob')
    existing = target / 'blobs' / name
    if not existing.exists() or existing.stat().st_size != (source / 'blobs' / name).stat().st_size:
        shutil.copy2(source / 'blobs' / name, existing)

# Retire only Nook's previous bundled defaults. Preserve all other user-added models.
for retired in ('0.6b', '1.7b', '4b'):
    obsolete = target / 'manifests/registry.ollama.ai/library/qwen3' / retired
    if MODEL == 'qwen3:' + retired or not obsolete.is_file() or not obsolete.resolve().is_relative_to(target):
        continue
    old = json.loads(obsolete.read_text())
    in_use = set()
    for path in (target / 'manifests').rglob('*'):
        if path.is_file() and path != obsolete:
            saved = json.loads(path.read_text())
            in_use.update(row['digest'] for row in [saved['config']] + saved['layers'])
    obsolete.unlink()
    for row in [old['config']] + old['layers']:
        blob = target / 'blobs' / row['digest'].replace(':', '-')
        if row['digest'] not in in_use and blob.is_file() and blob.resolve().is_relative_to(target):
            blob.unlink()
