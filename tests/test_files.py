from pathlib import Path
import csv
import hashlib
import zipfile
import pytest

from nexus.files import generate_files,extract_upload,safe_child,safe_text,MAX_UPLOAD_BYTES

TITLE="AI agents in cybersecurity"
CONTENT="# Research findings\nAI agents can help analysts organize threat evidence [1].\nHuman approval remains necessary for consequential actions.\nThe local software budget is ₹0, with café text preserved.\n# Evidence limitations\nThis example does not independently verify source claims."
SOURCES=[{"number":1,"title":"Example evidence","url":"https://example.com/evidence","text":"AI agents help analysts."}]


@pytest.mark.parametrize("fmt",["pdf","docx","xlsx","pptx","csv","txt","json"])
def test_each_format_is_real_and_reopened(tmp_path,fmt):
    [artifact]=generate_files(tmp_path,TITLE,CONTENT,[fmt],sources=SOURCES)
    path=tmp_path/artifact["filename"]
    assert artifact["verified"] and artifact["verification"]["parser_reopened"]
    assert artifact["sha256"]==hashlib.sha256(path.read_bytes()).hexdigest()
    text=extract_upload(path)
    assert TITLE in text and "₹0" in text and "café" in text
    assert "https://example.com/evidence" in text
    assert not artifact["verification"]["factual_accuracy_verified"]


def test_workbook_tables_formulas_charts_validation_and_injection(tmp_path):
    from openpyxl import load_workbook
    rows=[["Day","Subject","Activity","Minutes"],["Day 1","  =HYPERLINK(\"https://evil.invalid\")","Learn",60],["Day 2","@SUM(1)","Practice",60]]
    [artifact]=generate_files(tmp_path,TITLE,CONTENT,["xlsx"],sources=SOURCES,rows=rows)
    book=load_workbook(tmp_path/artifact["filename"],data_only=False)
    assert book["Summary"]["B2"].value.startswith("'")
    assert book["Summary"]["B2"].data_type=="s"
    assert book["Summary"]["B3"].value.startswith("'")
    assert book["Totals"]["B2"].value=="=SUM('Summary'!D2:D3)"
    assert book["Summary"].tables and book["Summary"].data_validations.count==1
    assert book["Summary"].conditional_formatting and book["Totals"]._charts
    assert book["Sources"]["C2"].hyperlink.target==SOURCES[0]["url"]
    book.close()


def test_csv_injection_is_literal(tmp_path):
    rows=[["Name","Value"],["=1+1"," \t@SUM(1)"]]
    [artifact]=generate_files(tmp_path,TITLE,CONTENT,["csv"],rows=rows)
    with (tmp_path/artifact["filename"]).open(encoding="utf-8-sig",newline="") as stream: actual=list(csv.reader(stream))
    assert actual[1][0]=="'=1+1" and actual[1][1].startswith("'")


@pytest.mark.parametrize("name",["../other.txt","C:\\other.txt","CON.txt","NUL","foo/bar.txt","x:stream.txt",".hidden","COM1.py"])
def test_unsafe_filenames_rejected(tmp_path,name):
    with pytest.raises(ValueError): safe_child(tmp_path,name)


@pytest.mark.parametrize("name",["file.exe","file.zip","file.docm"])
def test_upload_extensions_rejected(tmp_path,name):
    file=tmp_path/name; file.write_bytes(b"unsafe")
    with pytest.raises(ValueError,match="Unsupported"): extract_upload(file)


@pytest.mark.parametrize("suffix",["pdf","docx","xlsx","pptx"])
def test_upload_signature_rejected(tmp_path,suffix):
    file=tmp_path/f"fake.{suffix}"; file.write_text("This is not a document")
    with pytest.raises(ValueError,match="signature"): extract_upload(file)


def test_macro_and_archive_bomb_rejected(tmp_path):
    path=tmp_path/"macro.docx"
    with zipfile.ZipFile(path,"w") as archive:
        archive.writestr("[Content_Types].xml","<Types/>"); archive.writestr("word/document.xml","<document/>"); archive.writestr("word/vbaProject.bin",b"macro")
    with pytest.raises(ValueError,match="Macros"): extract_upload(path)
    path=tmp_path/"bomb.docx"
    with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml","<Types/>"); archive.writestr("word/document.xml","a"*200_000)
    with pytest.raises(ValueError,match="decompression"): extract_upload(path)


def test_zip_path_traversal_rejected(tmp_path):
    path=tmp_path/"bad.docx"
    with zipfile.ZipFile(path,"w") as archive:
        archive.writestr("[Content_Types].xml","<Types/>"); archive.writestr("word/document.xml","<document/>"); archive.writestr("../outside.txt","no")
    with pytest.raises(ValueError,match="Unsafe"): extract_upload(path)
    assert not (tmp_path.parent/"outside.txt").exists()


def test_pdf_encrypted_and_oversized_upload_rejected(tmp_path):
    from pypdf import PdfWriter
    file=tmp_path/"encrypted.pdf"; writer=PdfWriter(); writer.add_blank_page(100,100); writer.encrypt("secret"); writer.write(file)
    with pytest.raises(ValueError,match="Encrypted"): extract_upload(file)
    file=tmp_path/"large.txt"
    with file.open("wb") as stream: stream.truncate(MAX_UPLOAD_BYTES+1)
    with pytest.raises(ValueError,match="10 MB"): extract_upload(file)


def test_invalid_json_and_binary_text_rejected(tmp_path):
    path=tmp_path/"bad.json"; path.write_text("{bad}")
    with pytest.raises(ValueError): extract_upload(path)
    path=tmp_path/"binary.txt"; path.write_bytes(b"abc\0def")
    with pytest.raises(ValueError,match="Binary"): extract_upload(path)


def test_format_arguments_validated_before_writing(tmp_path):
    for formats in [["exe"],["pdf","pdf"],[]]:
        with pytest.raises(ValueError): generate_files(tmp_path,TITLE,CONTENT,formats)
    with pytest.raises(ValueError): generate_files(tmp_path,TITLE,CONTENT,["xlsx"],rows=[["a","b"],["wrong width"]])
    assert not list(tmp_path.iterdir())


def test_word_headings_and_page_field(tmp_path):
    from docx import Document
    [artifact]=generate_files(tmp_path,TITLE,CONTENT,["docx"])
    doc=Document(tmp_path/artifact["filename"])
    assert doc.paragraphs[0].style.name=="Title"
    assert "pBdr" not in doc.styles["Title"]._element.xml
    assert any(p.style.name=="Heading 1" for p in doc.paragraphs)
    assert "PAGE" in doc.sections[0].footer._element.xml


def test_presentation_has_editable_text_notes_and_source_hyperlink(tmp_path):
    from pptx import Presentation
    [artifact]=generate_files(tmp_path,TITLE,CONTENT,["pptx"],sources=SOURCES)
    presentation=Presentation(tmp_path/artifact["filename"])
    assert len(presentation.slides)>=3
    assert any("Human approval" in slide.notes_slide.notes_text_frame.text for slide in presentation.slides)
    urls=[run.hyperlink.address for slide in presentation.slides for shape in slide.shapes if shape.has_text_frame for p in shape.text_frame.paragraphs for run in p.runs]
    assert SOURCES[0]["url"] in urls


def test_safe_text_preserves_real_numbers():
    assert safe_text(-2)==-2 and safe_text(3.14)==3.14
    assert safe_text("normal")=="normal"
    assert safe_text("\ufeff=1+1").startswith("'")


def test_slide_chunking_keeps_section_heading_with_its_content():
    from nexus.files import _chunks
    chunks=_chunks("A research finding.\nEvidence limitations\nThis finding requires review.")
    assert chunks==["A research finding.","Evidence limitations\nThis finding requires review."]


def test_reference_groups_keep_titles_with_urls_and_full_long_targets():
    from nexus.files import _reference_groups
    refs=[{"number":i,"title":"Reference "+str(i)+" "+"x"*85,"url":"https://example.com/"+str(i)+"/"+"a"*80} for i in range(1,4)]
    groups=_reference_groups(refs)
    assert len(groups)>=2
    for ref in refs:
        group=next(group for group in groups if ref["url"] in group["links"].values())
        assert ref["title"] in group["text"]
    long_url="https://example.com/"+"long"*200
    [group]=_reference_groups([{"number":1,"title":"Long URL","url":long_url}])
    assert long_url in group["links"].values() and long_url in group["full_text"]
    assert len(group["text"])<500


def test_short_warning_and_standalone_heading_do_not_create_empty_slide_bodies(tmp_path):
    from pptx import Presentation
    content='Research comparison\nIncident response and containment\nA concrete defensive workflow.\nhttps://example.com/report: Invalid response Content-Length'
    [artifact]=generate_files(tmp_path,TITLE,content,['pptx'])
    presentation=Presentation(tmp_path/artifact['filename'])
    for slide in presentation.slides:
        frames=[shape.text for shape in slide.shapes if shape.has_text_frame]
        assert frames[1].strip()
    assert any('https://example.com/report: Invalid response' in slide.notes_slide.notes_text_frame.text for slide in presentation.slides)


def test_word_reference_label_stays_with_its_url(tmp_path):
    from docx import Document
    [artifact]=generate_files(tmp_path,TITLE,CONTENT,['docx'],sources=SOURCES)
    document=Document(tmp_path/artifact['filename'])
    label=next(p for p in document.paragraphs if p.text.startswith('[1]'))
    assert label.paragraph_format.keep_with_next is True
