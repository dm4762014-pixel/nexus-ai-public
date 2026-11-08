"""Render a fuller edition of the saved cybersecurity demo; no new AI/search.

Original QA answer/artifacts and all original user outputs are retained.
"""
from datetime import datetime
from pathlib import Path
import json
import re
import shutil
import zipfile
from nexus.files import generate_files
from nexus.store import Store
from nexus.synthesis import synthesize_comparison

ROOT=Path(__file__).resolve().parent.parent
session=json.loads((ROOT/'tmp/qa-session.json').read_text())
task=Store(ROOT/'tmp/qa-data/nexus.sqlite3').task(session['user_id'],'6ae5e82f96db40aa8dd1e0ceaaa5224d')
assert task['status']=='completed' and task['research_mode']=='evidence_id_comparison'
class SavedDraft:
    def complete_json(self,*args,**kwargs):
        return dict(findings=[dict(id=index,text=claim['text']) for index,claim in enumerate(task['claims'],1)])
revision=synthesize_comparison(task['prompt'],task['sources'],SavedDraft())
output=ROOT/'outputs'/('fuller-cybersecurity-report-'+datetime.now().strftime('%Y%m%d-%H%M%S'));output.mkdir()
warnings=[warning for warning in task['warnings'] if not re.match(r'^(?:duckduckgo|bing|google|https?://)',warning,re.I)]
warnings.append('Some searches or pages were unavailable. Only the listed retrieved sources were used.')
content=revision['answer']+'\n\nEvidence limitations\n'+'\n'.join(dict.fromkeys(warnings))+'\nThis edition expands the saved demonstration with review questions. No new sources or model claims were obtained.'
rows=[['Application','Summary','Source comparison','References']]+[[row['application'],row['summary'],row['comparison'],' '.join(f'[{n}]' for n in row['source_numbers'])] for row in revision['comparison']]
artifacts=generate_files(output,'AI Agents in Cybersecurity',content,['pdf','docx','pptx','xlsx'],sources=task['sources'],rows=rows)
names=[]
for artifact in artifacts:
    name='AI-Agents-in-Cybersecurity.'+artifact['format'];shutil.copy2(output/artifact['filename'],output/name);names.append(name)
manifest=dict(source_task=task['id'],new_retrieval=False,new_inference=False,source_claims_changed=False,pilot_questions=9,original_answer_words=len(task['answer'].split()),expanded_answer_words=len(revision['answer'].split()),verification='Saved source claims and original evidence retained; new pilot questions are editorial review prompts, not source claims or deployment validation.')
(output/'revision-results.json').write_text(json.dumps(manifest,indent=2));names.append('revision-results.json')
with zipfile.ZipFile(output/'NEXUS-Fuller-Report.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for name in names:archive.write(output/name,name)
with zipfile.ZipFile(output/'NEXUS-Fuller-Report.zip') as archive:assert not archive.testzip()
(ROOT/'tmp/fuller-demo-output.txt').write_text(str(output));print(json.dumps(dict(output=str(output),**manifest)))
