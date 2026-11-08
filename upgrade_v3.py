from pathlib import Path

old = Path("webapp_v2.py").read_text(encoding="utf-8-sig")

changes = [
    (
        "from document_tools import create_report",
        "from document_tools import create_report\n"
        "from research_tools import research_web"
    ),
    (
        'Literal["chat", "excel", "pdf", "docx", "both"]',
        'Literal["chat", "excel", "pdf", "docx", "both", "research"]'
    ),
    (
        '        if request.mode == "excel":',
        '''        if request.mode == "research":
            return research_web(request.prompt)

        if request.mode == "excel":'''
    ),
    (
        '<option value="chat">AI Chat</option>',
        '<option value="chat">AI Chat</option>\n'
        '<option value="research">Live Web Research</option>'
    ),
    (
        '  result.textContent=data.answer;\n'
        '  for(const file of data.files || []){',
        '''  result.textContent=data.answer;
  for(const source of data.sources || []){
   const a=document.createElement("a");
   a.href=source.url;
   a.target="_blank";
   a.rel="noopener noreferrer";
   a.textContent="["+source.number+"] "+source.title;
   files.appendChild(a);
  }
  for(const file of data.files || []){'''
    )
]

for old_text, new_text in changes:
    matches = old.count(old_text)
    if matches != 1:
        raise RuntimeError(
            f"Expected one matching code section, found {matches}: "
            f"{old_text[:70]}"
        )
    old = old.replace(old_text, new_text, 1)

Path("webapp_v3.py").write_text(old, encoding="utf-8")
print("NEXUS AI v3 created successfully!")
