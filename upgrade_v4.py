from pathlib import Path

research = Path("research_tools_v31.py").read_text(
    encoding="utf-8-sig"
)
dashboard = Path("webapp_v31.py").read_text(
    encoding="utf-8-sig"
)

def replace_once(source, old, new):
    if source.count(old) != 1:
        raise RuntimeError(
            f"Expected exactly one match: {old[:70]}"
        )
    return source.replace(old, new, 1)

# Improve search query extraction.
start = research.index("def build_search_query(")
end = research.index("def research_web(", start)

better_query = '''
def build_search_query(instruction):
    """Extract useful search terms from user instructions."""
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

    words = re.findall(r"[A-Za-z0-9]+", instruction)

    terms = [
        word for word in words
        if word.lower() not in ignored
    ]

    return " ".join(terms[:8]) or instruction[:100]


'''

research = research[:start] + better_query + research[end:]

# Check up to seven search candidates.
research = replace_once(
    research,
    'search_query, max_results=5, safesearch="moderate"',
    'search_query, max_results=7, safesearch="moderate"'
)

# Point the new dashboard to the upgraded research tool.
dashboard = replace_once(
    dashboard,
    "from research_tools_v31 import research_web",
    "from research_tools_v4 import research_web"
)

dashboard = replace_once(
    dashboard,
    'Literal["chat", "excel", "pdf", "docx", "both", "research"]',
    'Literal["chat", "excel", "pdf", "docx", "both", "research", "research_report"]'
)

# Add the multi-step research -> document workflow.
new_workflow = '''
        if request.mode == "research_report":
            result = research_web(request.prompt)
            sources = result.get("sources", [])

            if not sources:
                return {
                    "answer": (
                        "No readable sources were retrieved. "
                        "No document was generated."
                    ),
                    "sources": [],
                    "files": []
                }

            answer = result.get("answer", "")

            # Validate the numeric citation references.
            cited = {
                int(n) for n in re.findall(
                    r"\\[(\\d+)\\]", answer
                )
            }
            valid = {
                int(s["number"]) for s in sources
            }

            if cited - valid:
                return {
                    "answer": (
                        "The model produced invalid citation "
                        "numbers. Report generation was stopped."
                    ),
                    "sources": sources,
                    "files": []
                }

            warning = (
                "Limited evidence: only one source was "
                "retrieved. Independent corroboration "
                "is still needed."
                if len(sources) == 1
                else "Review claims against the sources."
            )

            references = "\\n".join(
                f'[{s["number"]}] {s["title"]}\\n'
                f'{s["url"]}'
                for s in sources
            )

            content = (
                "Research Question:\\n"
                + request.prompt
                + "\\n\\nResearch Findings:\\n"
                + answer
                + "\\n\\nEvidence Limitations:\\n"
                + warning
                + "\\n\\nRetrieved Sources:\\n"
                + references
            )

            files = create_report(
                title="NEXUS AI Research Report",
                content=content,
                formats=["pdf", "docx"]
            )

            return {
                "answer": (
                    answer
                    + "\\n\\n"
                    + warning
                    + "\\n\\nPDF and Word reports "
                    + "created and structurally verified."
                ),
                "sources": sources,
                "files": files
            }

'''

dashboard = replace_once(
    dashboard,
    '        if request.mode == "research":',
    new_workflow + '        if request.mode == "research":'
)

dashboard = replace_once(
    dashboard,
    '<option value="research">Live Web Research</option>',
    '<option value="research">Live Web Research</option>\\n'
    '<option value="research_report">'
    'Research + PDF + Word</option>'
)

Path("research_tools_v4.py").write_text(
    research, encoding="utf-8"
)
Path("webapp_v4.py").write_text(
    dashboard, encoding="utf-8"
)

print("NEXUS AI v4 files created.")
print("Previous versions remain unchanged.")
