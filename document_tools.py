"""Legacy v4 compatibility. Production downloads use owner-scoped routes."""
from pathlib import Path
from nexus.files import generate_files

OUTPUT=Path(__file__).resolve().parent/"outputs"
OUTPUT.mkdir(exist_ok=True)


def create_report(title:str,content:str,formats:list[str]):
    if len(content.strip())<100: raise ValueError("Report content is too short")
    if any(fmt not in {"pdf","docx"} for fmt in formats): raise ValueError("Legacy reports support PDF and DOCX")
    return [{**file,"name":f'NEXUS_Report.{file["format"]}',"url":f'/api/download/{file["filename"]}'} for file in generate_files(OUTPUT,title,content,formats)]
