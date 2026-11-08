from fastapi.testclient import TestClient
from nexus.planner import plan_task
from nexus.schemas import TaskRequest


def attach(signed, text, name='pilot.txt'):
    response = signed.post('/api/uploads', files={'file': (name, text.encode(), 'text/plain')})
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_auto_uploaded_research_summary_does_not_accidentally_browse():
    for prompt in ['Summarize the uploaded research paper.', 'Research the topic using only the uploaded evidence.']:
        plan = plan_task(TaskRequest(prompt=prompt, upload_ids=['a' * 32]))
        assert not plan.research and not plan.browser_url and not plan.code
    assert plan_task(TaskRequest(prompt='Summarize this report and search reliable sources.', upload_ids=['a' * 32])).research


def test_new_upload_retains_late_text_and_task_uses_owner_snapshot(signed, app, monkeypatch):
    text = 'Project background and planning details.\n' * 850 + 'Final handover is scheduled for Friday.'
    assert len(text) > 30000
    upload_id = attach(signed, text)
    owner = signed.get('/api/me').json()['id']
    with app.state.store.connect() as db:
        assert db.execute('SELECT text FROM uploads WHERE id=?', (upload_id,)).fetchone()['text'] == text
    import nexus.upload_briefing
    def briefing(prompt, documents, provider, checkpoint):
        checkpoint()
        assert documents == [dict(name='pilot.txt', text=text)]
        return dict(answer='A fuller briefing covering the final Friday handover.', warnings=[], claims=[], rows=[['Finding', 'Summary'], ['Handover', 'Friday']], coverage=[dict(name='pilot.txt')], model_metrics={})
    monkeypatch.setattr(nexus.upload_briefing, 'brief_uploads', briefing)
    task = signed.post('/api/tasks', json=dict(prompt='Summarize the attached pilot as a TXT report.', mode='document', upload_ids=[upload_id])).json()
    app.state.worker.run(owner, task['id'])
    result = signed.get('/api/tasks/' + task['id']).json()
    assert result['status'] == 'completed', result.get('error')
    assert 'Friday handover' in result['answer']
    assert result['upload_coverage'] == [dict(name='pilot.txt')]
    assert len(result['artifacts']) == 1
    other = TestClient(app)
    try:
        assert other.post('/api/login', json=dict(username='testuser', password='wrong-password')).status_code == 401
        assert other.get('/api/tasks/' + task['id']).status_code == 401
        assert other.get(result['artifacts'][0]['url']).status_code == 401
    finally:
        other.close()


def test_research_uploads_get_separate_bounded_briefing(signed, app, monkeypatch):
    import nexus.upload_briefing
    import nexus.research
    upload_id = attach(signed, 'The internal pilot starts in November.')
    monkeypatch.setattr(nexus.research, 'research_web', lambda *a, **k: dict(answer='Public evidence [1].', sources=[dict(number=1, title='Public page', url='https://example.com')], claims=[], warnings=[]))
    def briefing(prompt, documents, provider, checkpoint):
        assert 'brief' in prompt
        return dict(answer='Internal pilot in November [U1].', warnings=[], claims=[], rows=[], coverage=[], model_metrics={})
    monkeypatch.setattr(nexus.upload_briefing, 'brief_uploads', briefing)
    task = signed.post('/api/tasks', json=dict(prompt='Research and compare with the attached pilot.', mode='research', upload_ids=[upload_id])).json()
    app.state.worker.run(signed.get('/api/me').json()['id'], task['id'])
    result = signed.get('/api/tasks/' + task['id']).json()
    assert result['status'] == 'completed', result.get('error')
    assert '[1]' in result['answer'] and '[U1]' in result['answer']
    assert 'Separate uploaded evidence excerpt' not in result['answer']
    assert any('no joint factual reconciliation' in warning for warning in result['warnings'])


def test_foreign_upload_is_rejected_before_planning(signed, app):
    upload_id = attach(signed, 'Private owner text.')
    with app.state.store.connect() as db:
        db.execute('UPDATE uploads SET user_id=? WHERE id=?', ('another-owner', upload_id))
    response = signed.post('/api/tasks', json=dict(prompt='Summarize the attached file.', upload_ids=[upload_id]))
    assert response.status_code == 404
