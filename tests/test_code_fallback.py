def test_failed_model_code_is_not_reported_as_finished_application(signed, app):
    task = signed.post('/api/tasks', json=dict(prompt='Generate Python code to add numbers', mode='code')).json()
    owner = signed.get('/api/me').json()['id']
    # Fixture provider returns ordinary prose, invalid structured project JSON.
    app.state.worker.run(owner, task['id'])
    result = app.state.store.task(owner, task['id'])
    assert result['status'] == 'failed'
    assert 'incomplete' in result['error']
    assert result['artifacts'][0]['format'] == 'zip'
