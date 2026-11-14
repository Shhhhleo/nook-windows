"""Download the two small, redistributable Vosk English models from their publisher."""
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent / 'vendor/speech'
root.mkdir(parents=True, exist_ok=True)
models = ['vosk-model-small-en-us-0.15', 'vosk-model-small-en-in-0.4']
manifest = {}
for name in models:
    url = 'https://alphacephei.com/vosk/models/' + name + '.zip'
    archive = root / (name + '.zip')
    if not archive.exists():
        urllib.request.urlretrieve(url, archive)
    manifest[name] = {'url': url, 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'license': 'Apache-2.0'}
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            if not (root / member.filename).resolve().is_relative_to(root.resolve()):
                raise ValueError('Unsafe path in speech model archive')
        bundle.extractall(root)
    print('Prepared', name, flush=True)
(root / 'sources.json').write_text(json.dumps(manifest, indent=2), 'utf-8')
