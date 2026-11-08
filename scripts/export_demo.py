"""Copy only verified demonstration artifacts, never authentication material."""
from pathlib import Path
from hashlib import sha256
import json
import shutil
import zipfile

root = Path(__file__).resolve().parent.parent
task = json.loads((root / 'tmp/final-demo-result.json').read_text(encoding='utf-8'))
session = json.loads((root / 'tmp/qa-session.json').read_text())
source = root / 'tmp/qa-data' / session['user_id'] / task['id']
target = root / 'outputs' / ('demonstration-' + task['id'][:8] + '-final')
if target.exists():
    from datetime import datetime
    target = target.with_name(target.name + '-' + datetime.now().strftime('%H%M%S'))
target.mkdir(exist_ok=False)
names = []
for artifact in task['artifacts']:
    path = (source / artifact['filename']).resolve()
    assert path.is_relative_to(source.resolve()) and artifact['verified']
    assert sha256(path.read_bytes()).hexdigest() == artifact['sha256']
    name = 'AI-Agents-in-Cybersecurity.' + artifact['format']
    shutil.copy2(path, target / name)
    names.append(name)
manifest = {k: task[k] for k in ('id', 'prompt', 'status', 'answer', 'sources', 'claims', 'warnings', 'plan', 'created_at', 'completed_at')}
manifest['sources'] = [{k:v for k,v in source.items() if k not in ('text','paragraphs','evidence')} for source in task['sources']]
manifest['claims'] = [{k:v for k,v in claim.items() if k not in ('evidence','text')} for claim in task['claims']]
manifest['comparison']=task.get('comparison',[])
manifest['research_mode']=task.get('research_mode')
manifest['model_metrics']=task.get('model_metrics',{})
(target / 'demonstration-results.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
names.append('demonstration-results.json')
archive_path = target / 'NEXUS-Demonstration.zip'
with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in names:
        archive.write(target / name, name)
with zipfile.ZipFile(archive_path) as archive:
    assert not archive.testzip() and set(archive.namelist()) == set(names)
print(str(archive_path))
(root / 'tmp/exported-demo-dir.txt').write_text(str(target), encoding='utf-8')
