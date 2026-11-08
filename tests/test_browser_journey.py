"""Browser contracts with a fake renderer; real Chromium acceptance is opt-in."""
import json
from types import SimpleNamespace

from bs4 import BeautifulSoup
from PIL import Image
import pytest

import nexus.browser as browser


class FakePage:
    def __init__(self, calls):
        self.calls = calls
        self.html = ''

    def set_content(self, html, **kwargs):
        self.html = html
        self.calls.append(('render', html))

    def locator(self, selector):
        assert selector == 'body'
        self.calls.append(('locator', selector))
        return self

    def inner_text(self, **kwargs):
        return BeautifulSoup(self.html, 'html.parser').body.get_text('\n', strip=True)

    def screenshot(self, path, **kwargs):
        self.calls.append(('screenshot', path))
        Image.new('RGB', (24, 24), 'white').save(path)


class FakeContext:
    def __init__(self, calls):
        self.calls = calls
        self.page = FakePage(calls)

    def route(self, pattern, handler):
        assert pattern == '**/*'
        route = SimpleNamespace(abort=lambda: self.calls.append(('route_aborted',)))
        handler(route)

    def set_offline(self, value):
        self.calls.append(('offline', value))

    def new_page(self):
        self.calls.append(('new_page',))
        return self.page

    def close(self):
        self.calls.append(('context_closed',))


class FakeBrowser:
    def __init__(self, calls):
        self.calls = calls

    def new_context(self, **kwargs):
        assert kwargs['java_script_enabled'] is False
        assert kwargs['accept_downloads'] is False
        assert kwargs['service_workers'] == 'block'
        self.calls.append(('context', kwargs))
        return FakeContext(self.calls)

    def close(self):
        self.calls.append(('browser_closed',))


class FakePlaywright:
    def __init__(self, calls):
        self.calls = calls
        self.chromium = self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.calls.append(('playwright_closed',))

    def launch(self, **kwargs):
        assert kwargs['headless'] is True
        self.calls.append(('launch',))
        return FakeBrowser(self.calls)


@pytest.fixture
def renderer(monkeypatch):
    import playwright.sync_api
    calls = []
    monkeypatch.setattr(playwright.sync_api, 'sync_playwright', lambda: FakePlaywright(calls))
    return calls


def page(url, body=None):
    return dict(url=url, content_type='text/html', retrieved_at=1000,
                body=(body or '<title>Public research</title><main><h2>Useful findings</h2>'
                '<p>This public page describes useful evidence and limitations for readers.</p></main>').encode())


def test_journey_reads_sequentially_and_verifies_screenshots_and_log(tmp_path, monkeypatch, renderer):
    import nexus.network
    fetches = []
    checkpoints = []
    def checkpoint():
        checkpoints.append(True)
    def fetch(url, **kwargs):
        assert kwargs['checkpoint'] is checkpoint
        assert 0 < kwargs['max_bytes'] <= browser.MAX_PAGE_BYTES
        fetches.append(url)
        renderer.append(('fetch', url))
        kwargs['checkpoint']()
        return page(url + '/final')
    monkeypatch.setattr(nexus.network, 'fetch_public', fetch)
    urls = ['https://one.example/article', 'https://two.example/article']
    result = browser.browser_journey(urls, tmp_path, checkpoint)
    assert fetches == urls
    order = [c[0] for c in renderer if c[0] in ('fetch', 'render', 'screenshot')]
    assert order == ['fetch', 'render', 'screenshot'] * 2
    assert sum(c[0] == 'launch' for c in renderer) == 1
    assert sum(c[0] == 'new_page' for c in renderer) == 1
    assert ('offline', True) in renderer and ('route_aborted',) in renderer
    assert len(checkpoints) >= 12
    assert len(result['artifacts']) == 3
    assert all(a['verified'] for a in result['artifacts'])
    assert len({a['filename'] for a in result['artifacts']}) == 3
    assert [p['requested_url'] for p in result['pages']] == urls
    assert [p['url'] for p in result['pages']] == [u + '/final' for u in urls]
    assert result['sources'][1]['number'] == 2
    assert 'Page 1: Public research' in result['answer'] and 'Page 2:' in result['answer']
    assert '[1]' not in result['answer']
    assert 'not independently verified facts' in result['answer']
    log_artifact = result['artifacts'][-1]
    log = json.loads((tmp_path / log_artifact['filename']).read_text(encoding='utf-8'))
    assert log['live_interaction'] is False
    assert log['independent_fact_check'] is False
    assert len(log['pages']) == 2
    for index, entry in enumerate(log['pages']):
        assert entry['screenshot'] == result['artifacts'][index]['filename']
        assert entry['screenshot_sha256'] == result['artifacts'][index]['sha256']
        assert entry['source_sha256']
        assert entry['reading_characters'] > 30
        assert not any('path' in key or 'cookie' in key or 'password' in key for key in entry)
    assert ('context_closed',) in renderer and ('browser_closed',) in renderer


def test_only_escaped_semantic_blocks_reach_chromium(tmp_path, monkeypatch, renderer):
    import nexus.network
    hostile = '''<title>Safe &amp; useful</title><main><h2 onclick="steal()">Real heading</h2>
    <p>Regular source text includes &lt;script&gt; as a literal phrase and sufficient detail.</p>
    <script>stolenSecret()</script><form action="https://evil.example"><input value="secret">Do not show form</form>
    <img src="https://evil.example/tracker" onerror="steal()"><p><a href="javascript:steal()">Link label</a></p>
    <ul><li><p>List detail once</p></li></ul><table><tr><th>Topic</th><th>Evidence</th></tr>
    <tr><td>Real topic</td><td><p>Table evidence once</p></td></tr></table></main>'''
    monkeypatch.setattr(nexus.network, 'fetch_public', lambda *a, **k: page(a[0], hostile))
    result = browser.browser_journey(['https://example.com'], tmp_path)
    html = next(c[1] for c in renderer if c[0] == 'render')
    assert '<h2>Real heading</h2>' in html and '<table>' in html
    assert '&lt;script&gt;' in html
    assert all(value not in html for value in ['stolenSecret', 'onclick', 'onerror', '<form', '<input', '<script', 'href=', '<img', 'Do not show form'])
    assert html.count('List detail once') == 1
    assert html.count('Table evidence once') == 1
    assert result['pages'][0]['heading_count'] == 1
    assert result['pages'][0]['table_count'] == 1
    assert result['pages'][0]['source_link_count'] == 1


@pytest.mark.parametrize('urls', [[], ['https://a.example'] * 4, ['http://example.com'],
    ['https://user:pass@example.com'], ['https://example.com:8080'],
    ['https://example.com/\nheader'], ['https://example.com\\evil'], ['not-a-url'], 'https://example.com'])
def test_invalid_plan_rejected_before_browser_or_network(tmp_path, monkeypatch, renderer, urls):
    import nexus.network
    monkeypatch.setattr(nexus.network, 'fetch_public', lambda *a, **k: pytest.fail('Must not fetch invalid plan'))
    with pytest.raises(ValueError):
        browser.browser_journey(urls, tmp_path)
    assert not renderer


def test_duplicate_urls_are_read_once_and_single_wrapper_remains_compatible(tmp_path, monkeypatch, renderer):
    import nexus.network
    seen = []
    def fetch(url, **kwargs):
        seen.append(url)
        return page(url)
    monkeypatch.setattr(nexus.network, 'fetch_public', fetch)
    journey = browser.browser_journey(['https://example.com'] * 3, tmp_path)
    assert seen == ['https://example.com'] and len(journey['pages']) == 1
    snapshot = browser.browser_snapshot('https://example.com', tmp_path)
    assert snapshot['title'] == 'Public research'
    assert snapshot['url'] == 'https://example.com'
    assert snapshot['artifact']['format'] == 'png' and snapshot['artifact']['verified']
    assert 'Useful findings' in snapshot['answer'] and snapshot['observed']
    assert snapshot['artifact']['filename'] != journey['artifacts'][0]['filename']


def test_cancellation_between_pages_stops_more_fetches_and_closes_context(tmp_path, monkeypatch, renderer):
    import nexus.network
    seen = []
    def fetch(url, **kwargs):
        seen.append(url)
        return page(url)
    def checkpoint():
        if any(c[0] == 'screenshot' for c in renderer):
            raise RuntimeError('Cancelled')
    monkeypatch.setattr(nexus.network, 'fetch_public', fetch)
    with pytest.raises(RuntimeError, match='Cancelled'):
        browser.browser_journey(['https://one.example', 'https://two.example'], tmp_path, checkpoint)
    assert seen == ['https://one.example']
    assert ('context_closed',) in renderer and ('browser_closed',) in renderer
    assert list(tmp_path.glob('*.png'))
    assert not list(tmp_path.glob('*.json'))


def test_fetch_rejection_propagates_without_success_log(tmp_path, monkeypatch, renderer):
    import nexus.network
    def fetch(*args, **kwargs):
        raise nexus.network.NetworkRejected('DNS resolves to a non-public address')
    monkeypatch.setattr(nexus.network, 'fetch_public', fetch)
    with pytest.raises(nexus.network.NetworkRejected, match='non-public'):
        browser.browser_journey(['https://127.0.0.1'], tmp_path)
    assert not list(tmp_path.glob('*'))
    assert not any(c[0] == 'render' for c in renderer)
    assert ('context_closed',) in renderer and ('browser_closed',) in renderer


@pytest.mark.parametrize('content_type,body,error', [('application/pdf', b'%PDF-1.7', 'HTML'),
    ('text/html', b'<p>Too short</p>', 'insufficient'),
    ('text/html', b'a' * (browser.MAX_PAGE_BYTES + 1), 'download budget')], ids=['non-html', 'too-short', 'over-budget'])
def test_bad_responses_fail_closed(tmp_path, monkeypatch, renderer, content_type, body, error):
    import nexus.network
    monkeypatch.setattr(nexus.network, 'fetch_public', lambda *a, **k: dict(url=a[0], content_type=content_type, body=body))
    with pytest.raises(ValueError, match=error):
        browser.browser_journey(['https://example.com'], tmp_path)
    assert not list(tmp_path.glob('*.json'))


def test_aggregate_download_budget_is_passed_to_each_fetch(tmp_path, monkeypatch, renderer):
    import nexus.network
    budgets = []
    monkeypatch.setattr(browser, 'MAX_PAGE_BYTES', 300)
    monkeypatch.setattr(browser, 'MAX_TOTAL_BYTES', 450)
    def fetch(url, **kwargs):
        budgets.append(kwargs['max_bytes'])
        if len(budgets) == 2:
            raise nexus.network.NetworkRejected('Response exceeds bounded download limit')
        return dict(url=url, content_type='text/html', body=b'<p>' + b'evidence ' * 25 + b'</p>')
    monkeypatch.setattr(nexus.network, 'fetch_public', fetch)
    with pytest.raises(nexus.network.NetworkRejected):
        browser.browser_journey(['https://one.example', 'https://two.example'], tmp_path)
    assert budgets == [300, 218]
    assert not list(tmp_path.glob('*.json'))


def test_rendering_text_is_bounded_with_many_blocks(tmp_path, monkeypatch, renderer):
    import nexus.network
    body = '<main>' + ''.join('<p>' + str(i) + ' evidence ' * 100 + '</p>' for i in range(100)) + '</main>'
    monkeypatch.setattr(nexus.network, 'fetch_public', lambda *a, **k: page(a[0], body))
    result = browser.browser_journey(['https://example.com'], tmp_path)
    assert result['pages'][0]['text_characters'] <= browser.MAX_TEXT
    assert result['pages'][0]['rendered_characters'] <= browser.MAX_RENDER_TEXT
    assert result['pages'][0]['reading_characters'] <= browser.MAX_RENDER_TEXT
    assert len(result['answer']) < browser.MAX_RENDER_TEXT + 1000


def test_many_short_blocks_and_table_rows_cannot_create_unbounded_screenshot_height():
    tables = ''.join('<table>' + '<tr><td>a</td><td>b</td></tr>' * 12 + '</table>' for _ in range(50))
    reading = browser._reading(page('https://example.com', '<main>' + tables + '</main>'))
    rendered = BeautifulSoup(reading['html'], 'html.parser')
    assert len(rendered.find_all('tr')) <= browser.MAX_BLOCKS
    paragraphs = ''.join('<p>detail</p>' for _ in range(1000))
    reading = browser._reading(page('https://example.com', '<main>' + paragraphs + '</main>'))
    rendered = BeautifulSoup(reading['html'], 'html.parser')
    assert len(rendered.find_all('p')) <= browser.MAX_BLOCKS + 1
    whitespace = '<main><pre>line' + ('\n' * 1000 + 'next') * 10 + '</pre></main>'
    reading = browser._reading(page('https://example.com', whitespace))
    assert '\n' not in reading['html']

def test_reader_removes_navigation_and_keeps_source_reference_labels_separate(tmp_path, monkeypatch, renderer):
    import nexus.network
    body = '<title>[77] Public source</title><header><p>Private navigation menu should not appear here.</p></header><nav><p>Menu links to unrelated pages should be excluded.</p></nav><div role="main"><h2>Main evidence</h2><p>The selected public content provides enough readable evidence for this page [77].</p></div><footer><p>Footer links should also be excluded from the reading.</p></footer>'
    monkeypatch.setattr(nexus.network, 'fetch_public', lambda *a, **k: page(a[0], body))
    result = browser.browser_journey(['https://example.com'], tmp_path)
    assert 'Main evidence' in result['answer']
    assert 'Private navigation' not in result['answer']
    assert 'Menu links' not in result['answer']
    assert 'Footer links' not in result['answer']
    assert '(page reference 77) Public source' in result['answer'] and '[77]' not in result['answer']
