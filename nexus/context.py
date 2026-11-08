"""Explicit, owner-scoped snapshots for bounded task follow-ups."""
import json

MAX_TURNS = 3
MAX_TEXT = 2400


def capture_context(db, owner, parent_id):
    turns, raw_turns, sources, visited = [], [], [], set()
    current, remaining, truncated = parent_id, MAX_TEXT, False
    for index in range(MAX_TURNS):
        if not current or current in visited:
            break
        visited.add(current)
        row = db.execute('SELECT id,prompt,status,request,payload FROM tasks WHERE id=? AND user_id=?', (current, owner)).fetchone()
        if not row:
            raise LookupError('Previous task not found')
        payload = json.loads(row['payload'])
        if row['status'] != 'completed' or not payload.get('answer', '').strip():
            raise ValueError('Follow up on a completed task with an answer')
        if index == 0:
            # Keep reference numbers stable across this chain, without copying
            # raw source bodies, artifact paths or execution/approval metadata.
            sources = [{k: s[k] for k in ('number', 'title', 'url', 'published_at', 'retrieved_at') if k in s}
                       for s in payload.get('sources', [])[:3]]
        raw_turns.append(dict(task_id=row['id'],prompt=row['prompt'],answer=payload['answer']))
        current = json.loads(row['request']).get('parent_task_id')
    for turn in raw_turns:
        prompt = turn['prompt'][:min(150, remaining)]
        remaining -= len(prompt)
        truncated |= len(prompt) < len(turn['prompt'])
        turns.append(dict(task_id=turn['task_id'],prompt=prompt,answer=''))
    for index,turn in enumerate(raw_turns):
        # Give the newest result unused space, while reserving a useful excerpt
        # for each older turn. Short recent answers leave room for the report.
        allowance=max(0,remaining-350*(len(raw_turns)-index-1))
        answer = turn['answer'][:allowance]
        remaining -= len(answer)
        truncated |= len(answer) < len(turn['answer'])
        turns[index]['answer']=answer
    truncated |= bool(current)
    return dict(parent_task_id=parent_id, turns=list(reversed(turns)), sources=sources,
                truncated=truncated, text_characters=MAX_TEXT-remaining)


def context_prompt(context):
    """Serialize bounded turns/labels without source bodies or metadata URLs.

    URL strings in the user's earlier conversation remain ordinary data;
    follow-ups never route them to browsing or research tools.
    """
    data = dict(turns=[dict(question=t['prompt'], answer=t['answer']) for t in context['turns']],
                references=[dict(number=s['number'], title=s.get('title', '')[:80]) for s in context['sources']])
    return json.dumps(data, ensure_ascii=False, separators=(',', ':'))
