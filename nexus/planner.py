import re
from .schemas import Plan, TaskRequest

FORMATS = {
    'pdf': r'\bpdf\b', 'docx': r'\b(word|docx)\b',
    'xlsx': r'\b(excel|xlsx|spreadsheet|workbook|timetable)\b',
    'pptx': r'\b(powerpoint|pptx|presentation|slides)\b',
    'csv': r'\bcsv\b', 'txt': r'\b(txt|text file)\b', 'json': r'\bjson\b',
}


def _prompt_urls(prompt):
    urls = []
    for value in re.findall(r'https://[^\s<>"\]]+', prompt):
        value = value.rstrip('.,;')
        while value.endswith(')') and value.count(')') > value.count('('):
            value = value[:-1].rstrip('.,;')
        if value not in urls:
            urls.append(value)
    return urls


def plan_task(request: TaskRequest, provider=None):
    text = request.prompt.lower()
    formats = list(dict.fromkeys(request.formats or [key for key, pattern in FORMATS.items() if re.search(pattern, text)]))
    research = bool(re.search(r'\b(research|search|reliable sources|latest|compare sources|web research)\b', text))
    code = bool(re.search(r'\b(code|python script|small app|application|website|project)\b', text) and re.search(r'\b(create|generate|build|write|scaffold)\b', text))
    # "real-world applications" does not select code generation.
    urls = _prompt_urls(request.prompt)
    browser = urls[0] if urls and (request.mode == 'browser' or re.search(r'\b(browse|navigate|visit|screenshot|website)\b', text)) else None
    if request.mode != 'auto':
        research = request.mode == 'research'
        code = request.mode == 'code'
        browser = (urls[0] if urls else '') if request.mode == 'browser' else None
    elif request.upload_ids:
        # A filename or the phrase "uploaded research paper" must not start a
        # web search when the requested workflow is a supplied-file summary.
        uploaded_only = bool(re.search(r'\b(?:use|using)\s+only\s+(?:the\s+)?(?:uploaded|attached|supplied)\b|\b(?:no web|without (?:web|browsing))\b', text))
        summary = bool(re.search(r'\b(?:summarize|summarise|summary|briefing|analyze|analyse)\b', text))
        explicit_web = bool(re.search(r'\b(?:search|latest|web research|reliable sources|compare sources)\b', text))
        if uploaded_only or (summary and not explicit_web):
            research = False
    if request.mode == 'browser' and not browser:
        raise ValueError('Browser tasks need a public HTTPS URL in the instruction')
    if request.mode == 'document' and not formats:
        formats = ['pdf']
    if request.parent_task_id:
        # Only the current request can select document formats. Prior text is
        # data and never introduces navigation, code execution or new searches.
        research, code, browser = False, False, None
    if code:
        formats = []
    if browser and len(urls) > 3:
        raise ValueError('Browser tasks support at most three explicitly supplied URLs')
    title = re.split(r'[.;\n]|,?\s+(?:then\s+)?(?:prepare|create|include|give)\b', request.prompt, maxsplit=1, flags=re.I)[0]
    title = re.sub(r'^(?:research|please|create|generate|write|prepare)\s+', '', title, flags=re.I).strip()
    title = title[:100] or 'NEXUS AI task'
    title = title[0].upper() + title[1:]
    result = Plan(research=research, code=code, browser_url=browser, browser_urls=urls if browser else [], formats=formats, title=title)
    if not (research or code or browser or formats or request.upload_ids or request.parent_task_id) and request.mode == 'auto' and provider:
        # Function calling is reserved for requests that deterministic routing cannot classify.
        try:
            candidate = provider.select_plan(request.prompt)
            # The model cannot introduce destinations absent from the user's instruction.
            destinations = candidate.browser_urls or ([candidate.browser_url] if candidate.browser_url else [])
            if any(url not in urls for url in destinations):
                raise ValueError('Model proposed an unauthorized destination')
            result = candidate
        except Exception:
            pass  # Chat fallback; no invented tool execution.
    return result


def sensitive_action(prompt):
    patterns = {
        'external_message': r'\b(send|email|message)\b.{0,30}\b(email|message|someone|recipient)\b',
        'purchase': r'\b(buy|purchase|checkout|place an order)\b',
        'delete_data': r'\b(delete|remove)\b.{0,30}\b(files|folder|account|data)\b',
        'publish': r'\b(publish|deploy publicly)\b',
        'account_change': r'\b(change|reset)\b.{0,20}\b(password|account)\b',
    }
    return next((action for action, pattern in patterns.items() if re.search(pattern, prompt.lower())), None)
