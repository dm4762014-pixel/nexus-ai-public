from pathlib import Path

path = Path("webapp_v4.py")
code = path.read_text(encoding="utf-8-sig")

old = r'</option>\n<option value="research_report">'
new = '</option>\n<option value="research_report">'

if old in code:
    code = code.replace(old, new)
    path.write_text(code, encoding="utf-8")
    print("Dashboard dropdown fixed.")
else:
    print("Dropdown already fixed or different.")

