import pytest
from nexus.synthesis import evidence_groups,synthesize_comparison

SOURCES=[
    dict(number=1,title='Publisher A',url='https://a.example/report',text='Security agents investigate and triage alerts, correlating endpoint evidence before recommending action to a human analyst.\n\nAn identity agent reviews unusual account activity and recommends access restrictions for approval by an analyst.'),
    dict(number=2,title='Publisher B',url='https://b.example/report',text='An alert triage agent performs dynamic investigations and prepares supporting evidence for analysts to review.\n\nA phishing investigation agent examines suspicious email indicators and gathers context before recommending a response.'),
    dict(number=3,title='Publisher C',url='https://c.example/report',text='An identity agent reviews unusual account activity, correlates access evidence and recommends a response to security analysts.')]
QUERY='Research real-world applications of AI agents in cybersecurity and compare reliable sources'


class JsonModel:
    def complete_json(self,system,prompt,output_model,tokens):
        import json
        groups=json.loads(prompt)['groups']
        return {'findings':[{'id':g['id'],'text':'Agents assist analysts by investigating relevant security signals and preparing evidence for a reviewed response.'} for g in groups]}


def test_comparison_has_three_applications_and_attaches_actual_quotes_in_python():
    result=synthesize_comparison(QUERY,SOURCES,JsonModel())
    assert result['summary_mode']=='evidence_id_comparison'
    assert len(result['comparison'])==3
    assert 'Source comparison:' in result['answer']
    assert 'Parallel descriptions' in result['answer']
    assert 'No second publisher' in result['answer']
    for claim in result['claims']:
        for evidence in claim['evidence']:
            assert evidence['quote'] in SOURCES[evidence['source_number']-1]['text']


def test_generic_iam_definition_is_not_an_agent_application():
    extra=dict(number=4,title='Glossary',url='https://d.example',text='Identity and access management is a cybersecurity discipline concerned with account permissions and access policies.')
    groups,evidence=evidence_groups(SOURCES+[extra],QUERY)
    assert not any(item['source_number']==4 for item in evidence.values())


def test_security_of_agents_is_not_misrepresented_as_a_defensive_application():
    extra=dict(number=4,title='Secure agents',url='https://d.example',text='Securing agents requires practitioners to pay attention to the action layer where threats can diverge by agent type or its place in an agent hierarchy.')
    groups,evidence=evidence_groups(SOURCES+[extra],QUERY)
    assert not any(item['source_number']==4 for item in evidence.values())


def test_offensive_agents_and_broad_definitions_do_not_displace_concrete_workflows():
    extras=[dict(number=4,title='Overview',url='https://d.example',text='These malicious agents can modify their code to avoid detection by antivirus software or firewalls, making them harder to defend against.'),
            dict(number=5,title='Definition',url='https://e.example',text='Agentic AI in cybersecurity refers to how agents are used to detect and respond to cyber threats across security operations.')]
    groups,evidence=evidence_groups(SOURCES+extras,QUERY)
    assert all(g['topic']!='general' for g in groups)
    assert not any(item['source_number']==4 for item in evidence.values())


def test_concrete_actions_and_adjacent_preview_wording_are_retained():
    source=dict(number=1,title='Product',url='https://a.example',text='Agents provide a range of applications for automated incident response to improve the security posture of organizations.\n\nThe incident response agent can notify team members, initiate rollback protocols and generate incident reports. Expected to preview for selected customers.')
    result=synthesize_comparison(QUERY,[source],JsonModel())
    assert 'rollback' in result['claims'][0]['evidence'][0]['quote']
    assert 'preview or forward-looking wording' in result['comparison'][0]['comparison']


def test_unknown_application_ids_are_rejected():
    class Invented(JsonModel):
        def complete_json(self,*args,**kwargs):
            result=super().complete_json(*args,**kwargs)
            result['findings'][0]['id']=3
            return result
    with pytest.raises(ValueError,match='every selected application'):
        synthesize_comparison(QUERY,SOURCES,Invented())


def test_model_cannot_silently_omit_an_application():
    class Omitted(JsonModel):
        def complete_json(self,*args,**kwargs):
            result=super().complete_json(*args,**kwargs)
            result['findings'].pop()
            return result
    with pytest.raises(ValueError,match='every selected application'):
        synthesize_comparison(QUERY,SOURCES,Omitted())


def test_full_worker_exports_comparison_rows_and_preserves_sources(signed,app,monkeypatch):
    import nexus.research
    import nexus.files
    from openpyxl import load_workbook
    order=[]
    original_generate=nexus.files.generate_files
    def render(*args,**kwargs):
        order.append('render')
        return original_generate(*args,**kwargs)
    monkeypatch.setattr(nexus.files,'generate_files',render)
    app.state.worker.provider.unload=lambda:order.append('unload') or True
    app.state.worker.provider.complete_json=JsonModel().complete_json
    monkeypatch.setattr(nexus.research,'search_candidates',lambda *args,**kwargs:[dict(href=s['url'],title=s['title']) for s in SOURCES])
    def fetch(url,**kwargs):
        source=next(s for s in SOURCES if s['url']==url)
        return dict(url=url,body=('<article>'+''.join('<p>'+p+'</p>' for p in source['text'].split('\n\n'))+'</article>').encode(),content_type='text/html')
    monkeypatch.setattr(nexus.research,'fetch_public',fetch)
    task=signed.post('/api/tasks',json=dict(prompt=QUERY+'. Create PDF, Word, Excel and PowerPoint.')).json()
    owner=signed.get('/api/me').json()['id']
    app.state.worker.run(owner,task['id'])
    result=app.state.store.task(owner,task['id'])
    assert result['status']=='completed',result.get('error')
    assert result['research_mode']=='evidence_id_comparison'
    assert len(result['comparison'])==3
    assert len(result['artifacts'])==4
    assert order[0]=='unload' and order.count('render')==4
    artifact=next(a for a in result['artifacts'] if a['format']=='xlsx')
    book=load_workbook(artifact['path'],read_only=True)
    rows=list(book['Summary'].iter_rows(values_only=True));book.close()
    assert rows[0]==('Application','Summary','Source comparison','References')
    assert len(rows)==4
    assert any('Parallel descriptions' in row[2] for row in rows[1:])
