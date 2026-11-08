"""Bounded public-page readings rendered in an isolated offline Chromium context.

The pinned-IP fetcher performs each GET. Chromium receives only escaped semantic
blocks, never source HTML, cookies, scripts, forms or remote resources. Page
readings are attributed excerpts, not a model-generated comparison.
"""
from __future__ import annotations

from hashlib import sha256
from html import escape
import json
import re
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

MAX_PAGES = 3
MAX_PAGE_BYTES = 2_000_000
MAX_TOTAL_BYTES = 4_000_000
MAX_TEXT = 12_000
MAX_RENDER_TEXT = 6_500
MAX_BLOCKS = 48
WARNING = ('Browser shows isolated offline readings of the approved public pages. '
           'Live forms, JavaScript, typing, link clicking and consequential interactions are disabled. '
           'Readings are excerpts, not independently verified facts or a model-written comparison.')


def _approved_urls(urls):
    """Reject malformed plans before any fetch; DNS/IP checks belong to fetch_public."""
    if not isinstance(urls, list) or not 1 <= len(urls) <= MAX_PAGES:
        raise ValueError('Browser reading needs one to three explicitly approved HTTPS URLs')
    result = []
    for url in urls:
        if not isinstance(url, str) or not 1 <= len(url) <= 2048:
            raise ValueError('Browser URLs must contain 1-2048 characters')
        try:
            parsed = urlsplit(url)
            if (parsed.scheme != 'https' or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or parsed.port not in (None, 443)
                    or any(ord(c) < 33 or ord(c) == 127 for c in url) or '\\' in url):
                raise ValueError('Only public HTTPS URLs without credentials or custom ports are allowed')
        except ValueError as exc:
            raise ValueError('Invalid approved browser URL') from exc
        if url not in result:
            result.append(url)
    return result


def _reading(fetched):
    from bs4 import BeautifulSoup
    if fetched['content_type'] not in ('text/html', 'application/xhtml+xml'):
        raise ValueError('Browser reading requires an HTML page')
    soup = BeautifulSoup(fetched['body'], 'html.parser')
    for tag in soup(['script', 'style', 'iframe', 'object', 'embed', 'form', 'svg', 'nav', 'header', 'footer', 'aside',
                     'noscript', 'template', 'canvas', 'input', 'button', 'select', 'textarea']):
        tag.decompose()
    title = soup.title.get_text(' ', strip=True)[:160] if soup.title else 'Public webpage'
    root = soup.find('main') or soup.find(attrs={'role': 'main'}) or soup.find('article') or soup.find(id='content') or soup
    plain = re.sub(r'\s+', ' ', root.get_text(' ', strip=True))[:MAX_TEXT]
    if len(plain) < 30:
        raise ValueError('Page has insufficient readable content')
    blocks, consumed, headings, tables, visual_units = [], 0, 0, 0, 0
    for tag in root.find_all(['h1', 'h2', 'h3', 'h4', 'p', 'li', 'blockquote', 'pre', 'table']):
        # Tables and list items contain their own paragraphs. Render each passage once.
        if tag.find_parent(['p', 'li', 'blockquote', 'pre', 'table']):
            continue
        remaining = MAX_RENDER_TEXT - consumed
        if remaining <= 0 or visual_units >= MAX_BLOCKS:
            break
        text = re.sub(r'\s+', ' ', tag.get_text(' ', strip=True))[:remaining]
        if not text:
            continue
        consumed += len(text)
        if tag.name == 'table':
            # Emit new table markup from text-only cells; source attributes/HTML never survive.
            table_rows, table_budget = [], len(text)
            for row in tag.find_all('tr')[:min(12, MAX_BLOCKS - visual_units)]:
                cells = []
                for cell in row.find_all(['th', 'td'], recursive=False)[:6]:
                    value = re.sub(r'\s+', ' ', cell.get_text(' ', strip=True))[:min(300, table_budget)]
                    table_budget -= len(value)
                    if value:
                        cells.append('<td>' + escape(value) + '</td>')
                    if table_budget <= 0:
                        break
                if cells:
                    table_rows.append('<tr>' + ''.join(cells) + '</tr>')
                if table_budget <= 0:
                    break
            if table_rows:
                blocks.append('<table>' + ''.join(table_rows) + '</table>')
                tables += 1
                visual_units += len(table_rows)
            else:
                blocks.append('<p>' + escape(text) + '</p>')
                visual_units += 1
        else:
            name = tag.name if tag.name in ('h1', 'h2', 'h3', 'h4', 'blockquote', 'pre') else 'p'
            prefix = '\u2022 ' if tag.name == 'li' else ''
            blocks.append('<' + name + '>' + prefix + escape(text) + '</' + name + '>')
            headings += tag.name in ('h1', 'h2', 'h3', 'h4')
            visual_units += 1
    if not blocks:
        blocks = ['<p>' + escape(plain[:MAX_RENDER_TEXT]) + '</p>']
        consumed = len(plain[:MAX_RENDER_TEXT])
    html = ('<!doctype html><html><head><meta charset="utf-8"><title>Offline public reading</title>'
            '<style>body{font:18px Segoe UI,sans-serif;color:#142039;margin:60px;line-height:1.65;max-width:1060px;overflow-wrap:anywhere}'
            'h1{font-size:32px}h2{font-size:26px}h3,h4{font-size:22px}small{color:#506078}'
            'table{border-collapse:collapse;width:100%;table-layout:fixed}td{border:1px solid #c6d2e2;padding:10px;vertical-align:top}'
            'pre{white-space:pre-wrap}blockquote{border-left:3px solid #7399c9;padding-left:18px}</style></head><body>'
            '<h1>' + escape(title) + '</h1><small>' + escape(fetched['url']) + '</small>'
            '<p><small>Offline public-page reading. Source scripts, forms and network resources are disabled.</small></p>'
            + ''.join(blocks) + '</body></html>')
    return dict(title=title, text=plain, html=html, rendered_characters=consumed,
                heading_count=headings, table_count=tables,
                source_link_count=min(len(root.find_all('a', href=True)), 10_000))


def _artifact(path, fmt, verification):
    return dict(name=path.name, filename=path.name, format=fmt, size=path.stat().st_size,
                sha256=sha256(path.read_bytes()).hexdigest(), verified=True,
                verification=verification)


def browser_journey(urls: list[str], directory: Path, checkpoint=None):
    """Read 1-3 approved pages sequentially and retain screenshots plus a JSON log.

    Retrieval and rendering failures fail the task rather than silently dropping a
    requested page. Already-written files remain available for manual recovery.
    Redirects use the fetcher's repeated public-address checks and are logged.
    """
    from .network import fetch_public
    from playwright.sync_api import sync_playwright
    from PIL import Image

    urls = _approved_urls(urls)
    checkpoint = checkpoint or (lambda: None)
    checkpoint()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    run = uuid4().hex[:12]
    pages, sources, artifacts, answer = [], [], [], []
    total_bytes = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=['--disable-dev-shm-usage'], timeout=20000)
        try:
            context = browser.new_context(java_script_enabled=False, accept_downloads=False,
                                          service_workers='block', viewport=dict(width=1280, height=900))
            try:
                context.route('**/*', lambda route: route.abort())
                context.set_offline(True)
                page = context.new_page()
                for number, url in enumerate(urls, 1):
                    checkpoint()
                    remaining = MAX_TOTAL_BYTES - total_bytes
                    if remaining <= 0:
                        raise ValueError('Browser journey exceeds total download budget')
                    fetched = fetch_public(url, max_bytes=min(MAX_PAGE_BYTES, remaining), checkpoint=checkpoint)
                    body_size = len(fetched['body'])
                    total_bytes += body_size
                    # Defensive check also protects against a broken/custom fetch adapter.
                    if body_size > min(MAX_PAGE_BYTES, remaining) or total_bytes > MAX_TOTAL_BYTES:
                        raise ValueError('Browser journey exceeds download budget')
                    checkpoint()
                    reading = _reading(fetched)
                    page.set_content(reading['html'], wait_until='domcontentloaded', timeout=10000)
                    checkpoint()
                    observed = page.locator('body').inner_text(timeout=5000)
                    path = directory / f'browser-{run}-page-{number}.png'
                    checkpoint()
                    page.screenshot(path=str(path), full_page=True, timeout=10000)
                    with Image.open(path) as image:
                        image.verify()
                    checkpoint()
                    artifact = _artifact(path, 'png', 'PNG reopened; isolated offline semantic page reading; no live interaction')
                    artifacts.append(artifact)
                    pages.append(dict(number=number, requested_url=url, url=fetched['url'], title=reading['title'],
                                      retrieved_at=fetched.get('retrieved_at'), downloaded_bytes=body_size,
                                      source_sha256=sha256(fetched['body']).hexdigest(),
                                      text_characters=len(reading['text']), rendered_characters=reading['rendered_characters'],
                                      heading_count=reading['heading_count'], table_count=reading['table_count'],
                                      source_link_count=reading['source_link_count'], observed_excerpt=observed[:500],
                                      reading_characters=min(len(observed), MAX_RENDER_TEXT), observed=observed[:500],
                                      screenshot=path.name, screenshot_sha256=artifact['sha256']))
                    sources.append(dict(number=number, url=fetched['url'], title=reading['title'],
                                        retrieved_at=fetched.get('retrieved_at')))
                    # The result matches what Chromium actually read, not a longer hidden extraction.
                    excerpt = observed.split('Offline public-page reading. Source scripts, forms and network resources are disabled.', 1)[-1].strip()
                    excerpt = re.sub(r'\[(\d+)\]', r'(page reference \1)', excerpt[:MAX_RENDER_TEXT])
                    shown_title = re.sub(r'\[(\d+)\]', r'(page reference \1)', reading['title'])
                    answer.append(f'Page {number}: {shown_title}\n{fetched["url"]}\n\n{excerpt}')
                    # Do not retain original HTML or the previous page's parsed tree.
                    del fetched, reading
            finally:
                context.close()
        finally:
            browser.close()
    checkpoint()
    log = dict(version=1, kind='offline_public_page_readings', pages=pages,
               downloaded_bytes=total_bytes, page_limit=MAX_PAGES, warnings=[WARNING],
               live_interaction=False, independent_fact_check=False)
    log_path = directory / f'browser-{run}-journey.json'
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding='utf-8')
    reopened = json.loads(log_path.read_text(encoding='utf-8'))
    if len(reopened['pages']) != len(urls):
        raise RuntimeError('Browser journey log verification failed')
    artifacts.append(_artifact(log_path, 'json', 'JSON reopened; ordered page readings and recorded screenshot hashes preserved'))
    checkpoint()
    return dict(answer='Public-page readings\n\n' + '\n\n'.join(answer) + '\n\n' + WARNING,
                sources=sources, pages=pages, artifacts=artifacts, warnings=[WARNING])


def browser_snapshot(url: str, directory: Path, checkpoint=None):
    """Backward-compatible single-page snapshot, including the new journey log."""
    result = browser_journey([url], directory, checkpoint)
    first = result['pages'][0]
    return dict(result, title=first['title'], url=first['url'], artifact=result['artifacts'][0],
                observed=first['observed_excerpt'][:200])
