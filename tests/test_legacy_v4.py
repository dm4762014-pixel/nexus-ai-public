"""Repaired v4 HTTP seam; real search is covered separately by live tests."""
from fastapi.testclient import TestClient
import document_tools
import webapp_v4


def test_v4_research_documents_and_downloads(tmp_path, monkeypatch):
    monkeypatch.setattr(document_tools, 'OUTPUT', tmp_path)
    monkeypatch.setattr(webapp_v4, 'OUTPUT', tmp_path)
    monkeypatch.setattr(webapp_v4, 'research_web', lambda prompt: dict(answer='Security agents assist alert triage using retrieved evidence [1].', sources=[dict(number=1, title='Retrieved source', url='https://example.com')]))
    with TestClient(webapp_v4.app) as client:
        response = client.post('/api/task', json=dict(prompt='Research three applications of AI agents in cybersecurity and provide reliable sources.', mode='research_report'))
        assert response.status_code == 200
        assert {file['format'] for file in response.json()['files']} == {'pdf', 'docx'}
        for file in response.json()['files']:
            assert file['verified']
            assert client.get(file['url']).status_code == 200
        page = client.get('/').text
        assert r'</option>\n<option' not in page
        assert 'Legacy local dashboard' in page


def test_v4_invented_citation_stops_document_generation(monkeypatch):
    monkeypatch.setattr(webapp_v4, 'research_web', lambda prompt: dict(answer='Invented claim [99]', sources=[dict(number=1, title='Source', url='https://example.com')]))
    with TestClient(webapp_v4.app) as client:
        result = client.post('/api/task', json=dict(prompt='Research a test subject', mode='research_report')).json()
    assert not result['files']
    assert 'invalid citation' in result['answer']
