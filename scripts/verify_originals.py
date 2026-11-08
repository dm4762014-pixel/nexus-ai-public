"""Confirm original user outputs remain byte-for-byte unchanged."""
from pathlib import Path
from hashlib import sha256
import json

root = Path(__file__).resolve().parent.parent
manifest = root / 'backups' / '20261021-212529' / 'outputs-manifest.json'
items = json.loads(manifest.read_text(encoding='utf-8-sig'))
for item in items:
    path = Path(item['Path'])
    assert path.is_file() and sha256(path.read_bytes()).hexdigest().upper() == item['Hash'], path
print(f'{len(items)} original user outputs preserved byte-for-byte')
