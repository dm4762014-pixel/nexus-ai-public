import json
import time
import httpx
import pytest
from nexus.config import Settings
from nexus.provider import OllamaProvider
from nexus.synthesis import Draft


def provider_with_frames(tmp_path,monkeypatch,frames):
    requests=[]
    real_client=httpx.Client
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200,content='\n'.join(json.dumps(frame) for frame in frames)+'\n')
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:real_client(transport=httpx.MockTransport(handle),**kwargs))
    return OllamaProvider(Settings(data_dir=tmp_path)),requests


def test_stream_assembles_tokens_and_uses_configured_cpu_limits(tmp_path,monkeypatch):
    provider,requests=provider_with_frames(tmp_path,monkeypatch,[{'message':{'content':'Useful '}},{'message':{'content':'summary'},'done':True,'eval_count':2,'prompt_eval_count':10}])
    assert provider.complete('Be concise','Explain something')=='Useful summary'
    assert requests[0]['stream'] is True
    assert requests[0]['options']['num_thread']==4
    assert requests[0]['options']['num_batch']==64
    assert provider.last_metrics['generated_tokens']==2


def test_structured_stream_stops_at_complete_json_without_trailing_whitespace(tmp_path,monkeypatch):
    body=json.dumps({'findings':[{'id':1,'text':'Agents help analysts investigate and prioritize security alerts.'}]})
    provider,requests=provider_with_frames(tmp_path,monkeypatch,[{'message':{'content':body},'done':False},{'error':'Must not consume another frame'}])
    result=provider.complete_json('Return JSON','Evidence',Draft)
    assert result['findings'][0]['id']==1
    assert isinstance(requests[0]['format'],dict)
    assert provider.last_metrics['early_json_stop']


def test_incomplete_json_fails_instead_of_becoming_a_summary(tmp_path,monkeypatch):
    provider,_=provider_with_frames(tmp_path,monkeypatch,[{'message':{'content':'{"findings":['},'done':True,'done_reason':'length'}])
    with pytest.raises(ValueError,match='token budget'):
        provider.complete_json('Return JSON','Evidence',Draft)


def test_cancellation_is_checked_during_generation(tmp_path,monkeypatch):
    provider,_=provider_with_frames(tmp_path,monkeypatch,[{'message':{'content':'first'}},{'message':{'content':'second'},'done':True}])
    calls=[]
    def checkpoint():
        calls.append(True)
        if len(calls)==3: raise RuntimeError('Cancelled at streamed token')
    provider.checkpoint=checkpoint
    with pytest.raises(RuntimeError,match='Cancelled'):
        provider.complete('Explain','Something')


def test_total_deadline_checked_even_when_tokens_keep_arriving(tmp_path,monkeypatch):
    provider,_=provider_with_frames(tmp_path,monkeypatch,[{'message':{'content':'first'}},{'message':{'content':'second'},'done':True}])
    provider.settings.model_timeout=.02
    provider.checkpoint=lambda:time.sleep(.03)
    with pytest.raises(TimeoutError,match='total inference deadline'):
        provider.complete('Explain','Something')
