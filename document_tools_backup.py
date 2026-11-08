from pathlib import Path
from uuid import uuid4
from html import escape

from docx import Document
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from pypdf import PdfReader

OUTPUT = Path(__file__).parent / "outputs"
OUTPUT.mkdir(exist_ok=True)


def create_report(title: str, content: str, formats: list[str]):
    """Create real DOCX/PDF reports and verify saved files."""
    if len(content.strip()) < 100:
        raise ValueError("Report content is too short")

    file_id = uuid4().hex
    results = []

    for fmt in formats:
        if fmt == "docx":
            path = OUTPUT / f"{file_id}.docx"
            doc = Document()
            doc.add_heading(title, 0)

            for paragraph in content.split("\n"):
                if paragraph.strip():
                    doc.add_paragraph(paragraph.strip())

            doc.save(path)

            verify = Document(path)
            text = "\n".join(p.text for p in verify.paragraphs)
            if len(text) < 100:
                raise RuntimeError("Word verification failed")

        elif fmt == "pdf":
            path = OUTPUT / f"{file_id}.pdf"
            styles = getSampleStyleSheet()

            story = [
                Paragraph(escape(title), styles["Title"]),
                Spacer(1, 15)
            ]

            for paragraph in content.split("\n"):
                if paragraph.strip():
                    safe = paragraph.encode(
                        "latin-1", "replace"
                    ).decode("latin-1")
                    story.append(
                        Paragraph(escape(safe), styles["BodyText"])
                    )
                    story.append(Spacer(1, 8))

            SimpleDocTemplate(str(path)).build(story)

            reader = PdfReader(str(path))
            text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )
            if len(text) < 100:
                raise RuntimeError("PDF verification failed")
        else:
            raise ValueError("Unsupported file format")

        results.append({
            "name": f"NEXUS_Report.{fmt}",
            "url": f"/api/download/{file_id}.{fmt}"
        })

    return results
