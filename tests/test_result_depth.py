from nexus.synthesis import synthesize_comparison
from tests.test_synthesis import SOURCES, QUERY, JsonModel


def test_full_report_adds_useful_review_questions_without_inventing_source_claims():
    result=synthesize_comparison(QUERY,SOURCES,JsonModel())
    assert result['answer'].count('Before a pilot')==3
    assert 'Who reviews the suggested verdict' in result['answer']
    assert 'not additional publisher claims' in result['answer']
    assert all('?' not in claim['text'] for claim in result['claims'])
    brief=synthesize_comparison(QUERY+'. Keep it brief.',SOURCES,JsonModel())
    assert 'Before a pilot' not in brief['answer']
    assert len(result['answer'].split()) > len(brief['answer'].split())+60


def test_document_detail_budget_and_plain_activity_diagnostics(signed,app,monkeypatch):
    seen=[]
    def compose(system,prompt,tokens):
        seen.append(tokens)
        assert 'do not pad, repeat or invent facts' in system
        return 'A document with clear explanations supported by the supplied task inputs.'
    app.state.worker.provider.complete=compose
    owner=signed.get('/api/me').json()['id']
    for prompt in ['Create a TXT guide to planning a personal study routine.','Create a brief TXT guide to planning a personal study routine.']:
        task=signed.post('/api/tasks',json={'prompt':prompt,'mode':'document'}).json()
        app.state.worker.run(owner,task['id'])
        assert signed.get('/api/tasks/'+task['id']).json()['status']=='completed'
    assert seen==[800,650]
    import nexus.research
    monkeypatch.setattr(nexus.research,'research_web',lambda *a,**k:dict(answer='A sourced finding [1].',sources=[dict(number=1,title='Evidence',url='https://example.com')],claims=[],warnings=[],failures=[dict(provider='search-backend',error='HTTP 403 INTERNAL-DIAGNOSTIC')]))
    task=signed.post('/api/tasks',json={'prompt':'Research a topic','mode':'research'}).json()
    app.state.worker.run(owner,task['id'])
    result=signed.get('/api/tasks/'+task['id']).json()
    assert result['status']=='completed'
    assert any('Some searches or pages were unavailable' in warning for warning in result['warnings'])
    assert not any('INTERNAL-DIAGNOSTIC' in warning for warning in result['warnings'])
    assert any('INTERNAL-DIAGNOSTIC' in event['message'] for event in result['events'])
