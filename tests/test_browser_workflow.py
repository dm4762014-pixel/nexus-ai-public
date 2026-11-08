from hashlib import sha256
import json

import pytest
from pydantic import ValidationError

from nexus.planner import plan_task
from nexus.schemas import Plan, TaskRequest


def test_browser_routes_only_explicit_bounded_destinations():
    plan = plan_task(TaskRequest(prompt='Visit https://a.example/path and https://b.example/page and https://a.example/path.', mode='browser'))
    assert plan.browser_url == 'https://a.example/path'
    assert plan.browser_urls == ['https://a.example/path', 'https://b.example/page']
    with pytest.raises(ValueError, match='at most three'):
        plan_task(TaskRequest(prompt='Visit ' + ' '.join(f'https://{letter}.example' for letter in 'abcd'), mode='browser'))
    with pytest.raises(ValidationError):
        Plan(browser_url='https://a.example', browser_urls=['https://b.example'])
    with pytest.raises(ValidationError):
        Plan(browser_urls=['https://a.example'] * 4)


def test_model_cannot_add_urls_or_authorize_by_substring():
    class Provider:
        def select_plan(self, prompt):
            return Plan(browser_urls=['https://a.example/extra'])
    plan = plan_task(TaskRequest(prompt='Read evidence at https://a.example/extra-secret'), Provider())
    assert not plan.browser_url
    class OtherProvider:
        def select_plan(self, prompt):
            return Plan(browser_urls=['https://a.example', 'https://injected.example'])
    plan = plan_task(TaskRequest(prompt='Read evidence at https://a.example'), OtherProvider())
    assert not plan.browser_url


def test_multi_page_approval_is_frozen_and_downloads_are_protected(signed, app, monkeypatch):
    import nexus.browser
    urls = ['https://a.example', 'https://b.example']
    seen = []
    def journey(destinations, directory, checkpoint):
        checkpoint()
        seen.extend(destinations)
        assert destinations == urls
        path = directory / 'browser-journey.json'
        path.write_text(json.dumps({'pages': destinations}))
        return dict(answer='Two approved public page readings.', warnings=['No forms submitted.'],
                    pages=[dict(number=i, title='Page '+str(i), requested_url=url, url=url, screenshot=f'page-{i}.png', reading_characters=80) for i,url in enumerate(destinations,1)],
                    sources=[dict(number=i, title='Page '+str(i), url=url) for i,url in enumerate(destinations,1)],
                    artifacts=[dict(name=path.name, filename=path.name, format='json', size=path.stat().st_size, sha256=sha256(path.read_bytes()).hexdigest(), verified=True)])
    monkeypatch.setattr(nexus.browser, 'browser_journey', journey)
    task = signed.post('/api/tasks', json={'prompt':'Visit '+' and '.join(urls), 'mode':'browser'}).json()
    owner = signed.get('/api/me').json()['id']
    app.state.worker.run(owner, task['id'])
    assert not seen
    approval = signed.get('/api/approvals').json()[0]
    assert all(url in approval['detail'] for url in urls)
    assert 'No forms or submissions' in approval['detail']
    # Even if request data changes after review, the approved plan is immutable.
    with app.state.store.connect() as db:
        db.execute('UPDATE tasks SET request=? WHERE id=?', (TaskRequest(prompt='Visit https://changed.example', mode='browser').model_dump_json(),task['id']))
    assert signed.post('/api/approvals/'+approval['id'],json={'approved':True}).status_code == 200
    app.state.worker.run(owner, task['id'])
    result = signed.get('/api/tasks/'+task['id']).json()
    assert result['status'] == 'completed', result.get('error')
    assert seen == urls and result['execution_plan']['browser_urls'] == urls
    assert len(result['browser_pages']) == 2
    assert [s['url'] for s in result['sources']] == urls
    link = result['artifacts'][0]['url']
    assert signed.get(link).status_code == 200
    signed.post('/api/logout')
    assert signed.get(link).status_code == 401

def test_browser_urls_preserve_balanced_path_parentheses():
    url = 'https://en.wikipedia.org/wiki/Agent_(computing)'
    for prompt in ['Visit '+url, 'Visit ('+url+').']:
        assert plan_task(TaskRequest(prompt=prompt,mode='browser')).browser_urls == [url]
