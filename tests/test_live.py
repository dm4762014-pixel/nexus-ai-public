"""Opt-in real tests. Default suite never requires internet or a loaded model."""
import os
from pathlib import Path
import pytest

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.getenv('NEXUS_LIVE_TESTS') != '1', reason='Set NEXUS_LIVE_TESTS=1 to use local Ollama and internet')]


def test_real_ollama_and_function_call(tmp_path):
    from nexus.config import Settings
    from nexus.provider import OllamaProvider
    provider = OllamaProvider(Settings(data_dir=tmp_path))
    assert provider.health() == dict(reachable=True, installed=True)
    text = provider.complete('Answer with a short greeting.', 'Say hello.', tokens=40)
    assert text.strip()
    # Calling validates the real function-call schema; routing semantics are separately deterministic.
    plan = provider.select_plan('Create a PDF report about cloud computing')
    assert plan.formats


def test_real_research_html_pdf():
    from nexus.network import fetch_public
    from nexus.research import research_web, extract_document, validate_citations
    html = fetch_public('https://www.python.org/')
    assert len(extract_document(html['body'], html['content_type'])['text']) > 150
    pdf = fetch_public('https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf')
    assert 'Dummy PDF' in extract_document(pdf['body'], pdf['content_type'])['text']
    result = research_web('Research three applications of AI Agents in cybersecurity and provide reliable source references.')
    assert len(result['sources']) >= 2
    assert validate_citations(result['answer'], result['sources'])


def test_real_browser_read_snapshot(tmp_path):
    from nexus.browser import browser_snapshot
    result = browser_snapshot('https://example.com', tmp_path)
    assert result['artifact']['verified']
    assert 'Example Domain' in result['answer']
