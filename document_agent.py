from pathlib import Path
from html import escape

from ollama import chat
from docx import Document
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet
from pypdf import PdfReader

OUTPUT = Path(__file__).resolve().parent / "outputs"
OUTPUT.mkdir(exist_ok=True)

TITLE = "AI Agents - The Future of AI"

print("NEXUS AI: Generating report content...")

response = chat(
    model="qwen3:1.7b",
    messages=[
        {
            "role": "system",
            "content": (
                "You write simple, accurate educational reports. "
                "Use plain text, short paragraphs and numbered "
                "section headings. Do not invent statistics. "
                "Do not claim to have researched websites."
            )
        },
        {
            "role": "user",
            "content": (
                "Write a short report for Diploma IT students "
                "about AI Agents. Include four sections: "
                "1. Introduction, 2. How AI Agents Work, "
                "3. Applications, 4. Challenges and Future. "
                "Use clear simple English."
            )
        }
    ],
    think=False,
    options={"num_ctx": 2048, "num_predict": 550},
    keep_alive="30s"
)

content = (response.message.content or "").strip()

if len(content) < 100:
    raise RuntimeError("AI produced insufficient report content")

# Generate Word file
docx_path = OUTPUT / "NEXUS_AI_Agents_Report.docx"
doc = Document()
doc.add_heading(TITLE, 0)

for line in content.splitlines():
    if line.strip():
        doc.add_paragraph(line.strip())

doc.save(docx_path)

# Generate PDF file
pdf_path = OUTPUT / "NEXUS_AI_Agents_Report.pdf"
styles = getSampleStyleSheet()
story = [
    Paragraph(escape(TITLE), styles["Title"]),
    Spacer(1, 16)
]

for line in content.splitlines():
    if line.strip():
        # Built-in PDF fonts have limited Unicode support.
        safe = line.encode("ascii", "replace").decode("ascii")
        story.append(
            Paragraph(escape(safe), styles["BodyText"])
        )
        story.append(Spacer(1, 8))

SimpleDocTemplate(str(pdf_path)).build(story)

# Verify actual files
verified_doc = Document(docx_path)
word_text = "\n".join(
    p.text for p in verified_doc.paragraphs
)

reader = PdfReader(str(pdf_path))
pdf_text = "\n".join(
    page.extract_text() or "" for page in reader.pages
)

if len(word_text) < 100 or len(pdf_text) < 100:
    raise RuntimeError("Document verification failed")

print("\nSUCCESS: Both reports created and verified!")
print("WORD:", docx_path)
print("PDF :", pdf_path)
print("\nNEXUS AI Document Agent completed.")
