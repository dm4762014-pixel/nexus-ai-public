def test_browser_releases_model_before_launch(signed, app, monkeypatch):
    import nexus.browser
    order = []
    app.state.worker.provider.unload = lambda: order.append('unload') or True
    def snapshot(*args, **kwargs):
        order.append('browser')
        raise RuntimeError('Stop after checking lifecycle order')
    monkeypatch.setattr(nexus.browser, 'browser_snapshot', snapshot)
    task = signed.post('/api/tasks', json=dict(prompt='Visit https://example.com', mode='browser')).json()
    owner = signed.get('/api/me').json()['id']
    app.state.worker.run(owner, task['id'])
    approval = signed.get('/api/approvals').json()[0]
    signed.post('/api/approvals/' + approval['id'], json={'approved': True})
    app.state.worker.run(owner, task['id'])
    assert order[:2] == ['unload', 'browser']


def test_browser_refuses_low_memory_after_unload(signed, app, monkeypatch):
    import psutil
    import nexus.browser
    from types import SimpleNamespace
    app.state.worker.provider.unload = lambda: True
    monkeypatch.setattr(psutil, 'virtual_memory', lambda: SimpleNamespace(available=100 * 1024**2))
    def forbidden(*args, **kwargs):
        raise AssertionError('Browser should not launch with insufficient RAM')
    monkeypatch.setattr(nexus.browser, 'browser_snapshot', forbidden)
    task = signed.post('/api/tasks', json=dict(prompt='Visit https://example.com', mode='browser')).json()
    owner = signed.get('/api/me').json()['id']
    app.state.worker.run(owner, task['id'])
    approval = signed.get('/api/approvals').json()[0]
    signed.post('/api/approvals/' + approval['id'], json={'approved': True})
    app.state.worker.run(owner, task['id'])
    result = app.state.store.task(owner, task['id'])
    assert result['status'] == 'failed'
    assert '384 MiB' in result['error']
