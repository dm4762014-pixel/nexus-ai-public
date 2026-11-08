from pathlib import Path

source = Path("research_tools.py").read_text(
    encoding="utf-8-sig"
)

dashboard = Path("webapp_v3.py").read_text(
    encoding="utf-8-sig"
)

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(
            f"Expected one occurrence: {old[:65]}"
        )
    return text.replace(old, new, 1)

source = replace_once(
    source,
    "from urllib.parse import urlsplit",
    "from urllib.parse import urlsplit\nimport re"
)

helper = '''
def build_search_query(instruction):
    """Convert a task instruction into concise search terms."""
    ignored = {
        "research", "explain", "please", "provide",
        "citations", "citation", "sources", "source",
        "real", "online", "simple", "english",
        "use", "used", "in", "on", "the",
        "a", "an", "to", "for", "about",
        "how", "are", "with", "and", "me",
        "three", "give", "write", "short",
        "report", "information"
    }

    words = re.findall(
        r"[A-Za-z0-9][A-Za-z0-9.+-]*",
        instruction
    )

    terms = [
        word for word in words
        if word.lower() not in ignored
    ]

    return " ".join(terms[:10]) or instruction[:100]


'''

source = replace_once(
    source,
    "def research_web(query):",
    helper + "def research_web(query):"
)

source = replace_once(
    source,
    "    try:\n        with DDGS(timeout=8) as search:",
    '    search_query = build_search_query(query)\n'
    '    print("[Research] Searching:", search_query)\n\n'
    '    try:\n        with DDGS(timeout=8) as search:'
)

source = replace_once(
    source,
    '                query, max_results=5, safesearch="moderate"',
    '                search_query, max_results=5, safesearch="moderate"'
)

source = replace_once(
    source,
    "        text = get_page_text(url)",
    '        text = get_page_text(url)\n'
    '        print(f"[Research] {len(text)} chars: {url}")'
)

dashboard = replace_once(
    dashboard,
    "from research_tools import research_web",
    "from research_tools_v31 import research_web"
)

Path("research_tools_v31.py").write_text(
    source, encoding="utf-8"
)

Path("webapp_v31.py").write_text(
    dashboard, encoding="utf-8"
)

print("NEXUS AI v3.1 created!")
print("Existing v3 files remain unchanged.")
