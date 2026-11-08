"""Isolated local-model benchmark over previously retrieved evidence.

Not a fresh search test; the full UI acceptance run separately fetches sources.
Run from the project root with: python -m scripts.benchmark_synthesis
"""
from pathlib import Path
import json
import time
from nexus.config import Settings
from nexus.provider import OllamaProvider
from nexus.synthesis import evidence_groups,synthesize_comparison

root=Path(__file__).resolve().parent.parent
saved=json.loads((root/'tmp/final-demo-result.json').read_text())
provider=OllamaProvider(Settings())
provider.progress=lambda message:print(message,flush=True)
groups,_=evidence_groups(saved['sources'],saved['prompt'])
print(json.dumps({'applications':[(g['label'],len(g['evidence'])) for g in groups]}),flush=True)
started=time.monotonic()
try:
    result=synthesize_comparison(saved['prompt'],saved['sources'],provider)
    result['elapsed']=round(time.monotonic()-started,2)
    (root/'tmp/synthesis-benchmark.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(answer=result['answer'],metrics=provider.last_metrics,elapsed=result['elapsed'])),flush=True)
finally:
    provider.unload()
