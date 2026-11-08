"""Bounded local document tools. File integrity checks are not fact checking."""
from __future__ import annotations
import csv
import hashlib
import io
import json
import os
import re
import zipfile
from datetime import datetime
from html import escape
from pathlib import Path, PurePosixPath
from uuid import uuid4

MAX_UPLOAD_BYTES = 10*1024*1024
MAX_CONTENT = 50_000
MAX_EXTRACT = 100_000
FORMATS = {"pdf", "docx", "xlsx", "pptx", "csv", "txt", "json"}
_FONTS=[]


def safe_text(value):
    if isinstance(value,str):
        value=re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]","",value)
        if value.lstrip(" \t\r\n\v\f\ufeff\u200b\u200c\u200d").startswith(("=","+","-","@")): return "'"+value
    return value


def safe_child(directory:Path,filename:str)->Path:
    directory=Path(directory).resolve()
    reserved={"CON","PRN","AUX","NUL",*[f"COM{i}" for i in range(1,10)],*[f"LPT{i}" for i in range(1,10)]}
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}",filename) or filename.split(".")[0].upper() in reserved: raise ValueError("Unsafe or reserved file name")
    path=(directory/filename).resolve()
    if path.parent!=directory: raise ValueError("File escapes task workspace")
    return path


def _lines(text): return [p.strip() for p in text.splitlines() if p.strip()]


def _is_heading(line):
    if line.casefold() in {'how the sources differ','applications described by publishers'}: return True
    return line.startswith("#") or len(line)<80 and line.endswith(":") or line.casefold() in {"research findings","research comparison","alert triage and investigation","phishing investigation","identity and access review","incident response and containment","vulnerability prioritization","threat hunting and malware analysis","evidence limitations","retrieved evidence excerpts","retrieved sources","source comparison","uploaded evidence","summary","scope","conclusion","overview","applications","findings","recommendations","introduction"}


def _refs(sources):
    result=[]
    for i,s in enumerate(sources or [],1):
        url=str(s.get("url",""))
        if url.startswith("https://") and not any(c in url for c in '\r\n<>"'):
            result.append(f'[{s.get("number",i)}] {str(s.get("title",url))[:240]}\n{url[:2000]}')
    return result


def _fonts():
    if _FONTS: return _FONTS
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    win=Path(os.environ.get("WINDIR","C:/Windows"))/"Fonts"
    for path in [win/"arial.ttf",win/"Nirmala.ttc",win/"seguisym.ttf",Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]:
        if path.is_file():
            try:
                name=f"NexusUnicode{len(_FONTS)}"; pdfmetrics.registerFont(TTFont(name,str(path))); _FONTS.append(name)
            except Exception: continue
    if not _FONTS: raise RuntimeError("PDF needs installed Unicode TTF fonts, such as Windows Arial or DejaVu Sans")
    return _FONTS


def _pdf_text(text):
    from reportlab.pdfbase import pdfmetrics
    fonts=_fonts(); runs=[]; previous=None; buf=""
    for ch in text:
        name=next((name for name in fonts if ord(ch) in pdfmetrics.getFont(name).face.charToGlyph),None)
        if name is None and not ch.isspace(): raise ValueError(f"No installed PDF font supports U+{ord(ch):04X}; use DOCX for this script")
        name=name or fonts[0]
        if name!=previous and buf: runs.append(f'<font name="{previous}">{escape(buf)}</font>'); buf=""
        previous=name; buf+=ch
    if buf: runs.append(f'<font name="{previous}">{escape(buf)}</font>')
    return "".join(runs)


def _write_pdf(path,title,content,sources):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate,Paragraph,KeepTogether
    font=_fonts()[0]
    body=ParagraphStyle("Body",fontName=font,fontSize=10.5,leading=15,spaceAfter=6,textColor=colors.HexColor("#202938"))
    heading=ParagraphStyle("Heading",parent=body,fontSize=13,leading=18,spaceBefore=14,spaceAfter=8,keepWithNext=True)
    large=ParagraphStyle("Title",parent=heading,fontSize=23,leading=29,spaceAfter=20)
    story=[Paragraph(_pdf_text(title),large)]
    for line in _lines(content):
        is_heading=_is_heading(line)
        story.append(Paragraph(_pdf_text(line.lstrip("# ") if is_heading else line),heading if is_heading else body))
    if sources:
        story.append(Paragraph("Retrieved sources",heading))
        for ref in _refs(sources):
            label,url=ref.split("\n",1)
            story.append(KeepTogether([Paragraph(_pdf_text(label),body),Paragraph(f'<link href="{escape(url,quote=True)}" color="#2459a6">{_pdf_text(url)}</link>',body)]))
    def footer(canvas,doc):
        canvas.saveState(); canvas.setFont(font,8); canvas.setFillColor(colors.HexColor("#607083"))
        canvas.drawString(54,32,"NEXUS AI | Local workspace"); canvas.drawRightString(A4[0]-54,32,str(doc.page)); canvas.restoreState()
    SimpleDocTemplate(str(path),pagesize=A4,rightMargin=54,leftMargin=54,topMargin=50,bottomMargin=54,title=title,author="NEXUS AI").build(story,onFirstPage=footer,onLaterPages=footer)


def _write_docx(path,title,content,sources,rows):
    from docx import Document
    from docx.shared import Inches,Pt,RGBColor
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    doc=Document(); section=doc.sections[0]
    section.top_margin=section.bottom_margin=Inches(.75); section.left_margin=section.right_margin=Inches(.8)
    for name in ["Normal","Title","Heading 1","Heading 2"]:
        doc.styles[name].font.name="Arial"; doc.styles[name].font.color.rgb=RGBColor(0,0,0)
        # python-docx's default Title style includes a blue bottom border.
        # Remove inherited decoration rather than relying on font color alone.
        for border in list(doc.styles[name]._element.iter(qn("w:pBdr"))):
            border.getparent().remove(border)
    doc.styles["Normal"].font.size=Pt(10.5); doc.styles["Normal"].paragraph_format.space_after=Pt(8); doc.styles["Normal"].paragraph_format.line_spacing=1.15
    doc.add_paragraph(title,"Title")
    for line in _lines(content):
        if _is_heading(line): doc.add_heading(line.lstrip("# ").rstrip(":"),level=1)
        else: doc.add_paragraph(line)
    if rows and len(rows)<100 and all(len(str(v))<=350 for row in rows for v in row):
        doc.add_heading("Summary table",level=1); table=doc.add_table(rows=1,cols=len(rows[0])); table.style="Table Grid"
        for i,value in enumerate(rows[0]): table.rows[0].cells[i].text=str(value)
        for row in rows[1:]:
            for cell,value in zip(table.add_row().cells,row): cell.text=str(value)
        table.autofit=False
        if len(rows[0])==3:
            for column,width in zip(table.columns,[3.4,.95,2.55]): column.width=Inches(width)
        elif len(rows[0])==4 and rows[0][0] in ('Application','Aspect') and rows[0][1:]==['Summary','Source comparison','References']:
            for column,width in zip(table.columns,[1.4,2.4,2.2,.6]):
                column.width=Inches(width)
                for cell in column.cells: cell.width=Inches(width)
        borders=OxmlElement('w:tblBorders')
        for side in ('top','left','bottom','right','insideH','insideV'):
            border=OxmlElement('w:'+side); border.set(qn('w:val'),'single'); border.set(qn('w:sz'),'4'); border.set(qn('w:color'),'D9D9D9'); borders.append(border)
        table._tbl.tblPr.append(borders)
        for index,row in enumerate(table.rows):
            # Keep a record intact across pages and repeat its header on continuation.
            properties=row._tr.get_or_add_trPr(); properties.append(OxmlElement('w:cantSplit'))
            if index==0: properties.append(OxmlElement('w:tblHeader'))
            for cell in row.cells:
                shade=OxmlElement('w:shd'); shade.set(qn('w:fill'),'183E69' if index==0 else ('F3F6FA' if index%2 else 'FFFFFF')); cell._tc.get_or_add_tcPr().append(shade)
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.space_after=Pt(3); paragraph.paragraph_format.line_spacing=1.05
                    for run in paragraph.runs:
                        run.font.size=Pt(9.5); run.font.bold=index==0; run.font.color.rgb=RGBColor(255,255,255) if index==0 else RGBColor(0,0,0)
    if sources:
        doc.add_heading("Retrieved sources",level=1)
        for ref in _refs(sources):
            label,url=ref.split("\n",1); label_paragraph=doc.add_paragraph(label); label_paragraph.paragraph_format.keep_with_next=True
            p=doc.add_paragraph(); p.paragraph_format.keep_together=True; link=OxmlElement("w:hyperlink")
            link.set(qn("r:id"),p.part.relate_to(url,RT.HYPERLINK,is_external=True)); run=OxmlElement("w:r"); txt=OxmlElement("w:t"); txt.text=url; run.append(txt); link.append(run); p._p.append(link)
    footer=section.footer.paragraphs[0]; footer.add_run("NEXUS AI | Page "); field=OxmlElement("w:fldSimple"); field.set(qn("w:instr"),"PAGE"); footer._p.append(field)
    doc.core_properties.title=title; doc.core_properties.author="NEXUS AI"; doc.save(path)


def _write_xlsx(path,title,content,sources,rows):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.worksheet.table import Table,TableStyleInfo
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.formatting.rule import ColorScaleRule
    from openpyxl.chart import BarChart,Reference
    from openpyxl.chart.label import DataLabelList
    wb=Workbook(); sheet=wb.active; sheet.title="Summary"
    data=rows or [["Item","Finding","Source references"]]+[[i,line,", ".join(re.findall(r"\[\d+\]",line))] for i,line in enumerate(_lines(content),1)]
    for row in data: sheet.append([safe_text(v) for v in row])
    for i,cell in enumerate(sheet[1],1): cell.value=str(cell.value or f"Column {i}")
    if len({c.value for c in sheet[1]})!=sheet.max_column: raise ValueError("Spreadsheet headers must be unique")
    table=Table(displayName="NexusSummary",ref=sheet.dimensions); table.tableStyleInfo=TableStyleInfo(name="TableStyleMedium2",showRowStripes=True); sheet.add_table(table); sheet.freeze_panes="A2"
    for row in sheet:
        for cell in row: cell.alignment=Alignment(vertical="top",wrap_text=True); cell.font=Font(name="Calibri",size=11)
    for cell in sheet[1]: cell.font=Font(bold=True,color="FFFFFF"); cell.fill=PatternFill("solid",fgColor="183E69")
    for col in sheet.columns:
        header=str(col[0].value).lower()
        sheet.column_dimensions[col[0].column_letter].width=64 if any(s in header for s in ["finding","detail","activity","evidence","summary","comparison"]) else (16 if header=='references' else 28)
    if [cell.value for cell in sheet[1]] == ['Finding','Summary','Quoted passage','Location']:
        for letter,width in zip('ABCD',[24,48,68,30]):
            sheet.column_dimensions[letter].width=width
    for row in sheet:
        visual_lines=max(sum(max(1,(len(line)+int(sheet.column_dimensions[cell.column_letter].width)-1)//int(sheet.column_dimensions[cell.column_letter].width)) for line in str(cell.value or "").splitlines()) for cell in row)
        sheet.row_dimensions[row[0].row].height=min(409,max(30,visual_lines*16+14))
    notes=wb.create_sheet("Report text"); notes.append(["Title",safe_text(title)])
    for line in _lines(content): notes.append(["Content",safe_text(line)])
    notes.column_dimensions["A"].width=18; notes.column_dimensions["B"].width=110
    for row in notes:
        for cell in row: cell.alignment=Alignment(wrap_text=True,vertical="top")
        notes.row_dimensions[row[0].row].height=max(30,min(180,len(str(row[1].value))/100*18+18))
    if sources:
        refs=wb.create_sheet("Sources"); refs.append(["Reference","Title","Retrieved URL","Publication date"])
        for i,s in enumerate(sources,1):
            published=s.get("published_at") or "Not available"
            try: published=datetime.fromisoformat(str(published).replace("Z","+00:00")).date()
            except ValueError: pass
            refs.append([s.get("number",i),safe_text(str(s.get("title",""))),safe_text(str(s.get("url",""))),published])
            if not isinstance(published,str): refs.cell(refs.max_row,4).number_format="yyyy-mm-dd"
            if str(s.get("url","")).startswith("https://"): refs.cell(refs.max_row,3).hyperlink=s["url"]
        for col,width in {"A":14,"B":55,"C":90,"D":24}.items(): refs.column_dimensions[col].width=width
        for row in refs:
            for cell in row: cell.alignment=Alignment(wrap_text=True,vertical="top")
            refs.row_dimensions[row[0].row].height=max(30,min(409,max(len(str(c.value or ""))/refs.column_dimensions[c.column_letter].width for c in row)*16+20))
        refs.freeze_panes="A2"
        source_table=Table(displayName="NexusSources",ref=refs.dimensions)
        source_table.tableStyleInfo=TableStyleInfo(name="TableStyleMedium2",showRowStripes=True)
        refs.add_table(source_table)
        for cell in refs[1]: cell.font=Font(bold=True,color="FFFFFF"); cell.fill=PatternFill("solid",fgColor="183E69")
    numeric=[i for i in range(1,sheet.max_column+1) if sheet.max_row>1 and all(isinstance(sheet.cell(r,i).value,(int,float)) and not isinstance(sheet.cell(r,i).value,bool) for r in range(2,sheet.max_row+1))]
    if rows and numeric:
        col=numeric[-1]; letter=sheet.cell(1,col).column_letter; totals=wb.create_sheet("Totals"); totals.append(["Metric","Value"]); totals.append([f'Total {sheet.cell(1,col).value}',f"=SUM('Summary'!{letter}2:{letter}{sheet.max_row})"])
        totals.column_dimensions["A"].width=35; totals.column_dimensions["B"].width=20
        rule=DataValidation(type="decimal",operator="between",formula1="0",formula2="1000000000"); rule.showErrorMessage=True; sheet.add_data_validation(rule); rule.add(f"{letter}2:{letter}{sheet.max_row}")
        sheet.conditional_formatting.add(f"{letter}2:{letter}{sheet.max_row}",ColorScaleRule(start_type="min",start_color="EDF5FF",end_type="max",end_color="5798E3"))
        if sheet.max_row<=40:
            chart=BarChart(); chart.title=str(sheet.cell(1,col).value); chart.add_data(Reference(sheet,min_col=col,min_row=1,max_row=sheet.max_row),titles_from_data=True); chart.set_categories(Reference(sheet,min_col=1,min_row=2,max_row=sheet.max_row))
            chart.height=10; chart.width=20; chart.style=13; chart.legend=None
            chart.x_axis.title=str(sheet.cell(1,1).value); chart.y_axis.title=str(sheet.cell(1,col).value)
            chart.x_axis.delete=False; chart.y_axis.delete=False; chart.y_axis.scaling.min=0
            chart.x_axis.tickLblPos="nextTo"; chart.y_axis.tickLblPos="nextTo"
            chart.dLbls=DataLabelList(); chart.dLbls.showVal=True
            chart.series[0].graphicalProperties.solidFill="3478E5"
            totals.add_chart(chart,"A5")
    wb.properties.title=title; wb.properties.creator="NEXUS AI"; wb.save(path)


def _chunks(text,limit=500):
    chunks=[]; buf=""
    for line in _lines(text):
        if _is_heading(line) and buf:
            chunks.append(buf); buf=""
        while len(line)>limit:
            split=line.rfind(" ",0,limit); split=split if split>limit//2 else limit
            if buf: chunks.append(buf); buf=""
            chunks.append(line[:split]); line=line[split:].lstrip()
        # At 20pt a line holds about 70 Latin characters. Leave room for
        # wrapping, source URLs and paragraph spacing within the content box.
        prospective=buf+("\n" if buf else "")+line
        visual_lines=sum(max(1,(len(p)+64)//65) for p in prospective.splitlines())
        if len(prospective)>limit or visual_lines>8:
            if buf: chunks.append(buf)
            buf=""
        buf+=("\n" if buf else "")+line
    if buf: chunks.append(buf)
    return chunks


def _reference_groups(sources):
    """Keep each reference label and its clickable URL on the same slide."""
    groups=[]; current={"text":"","full_text":"","links":{}}
    for i,reference in enumerate(_refs(sources),1):
        label,url=reference.split("\n",1)
        # Very long URLs remain intact as the actual link target and in notes.
        shown=url if len(url)<=200 else url[:160]+f"... [source {i}]"
        displayed=label+"\n"+shown
        candidate=current["text"]+("\n" if current["text"] else "")+displayed
        visual_lines=sum(max(1,(len(line)+64)//65) for line in candidate.splitlines())
        if current["text"] and (len(candidate)>500 or visual_lines>8):
            groups.append(current); current={"text":"","full_text":"","links":{}}
        current["text"]+=("\n" if current["text"] else "")+displayed
        current["full_text"]+=("\n\n" if current["full_text"] else "")+reference
        current["links"][shown]=url
    if current["text"]: groups.append(current)
    return groups


def _comparison_overview(content,sources):
    """Select cited heading/summary pairs; never infer a sequence or new facts.

    Only a compact overview is abbreviated. The original report and complete
    source links still appear on the ordinary detail and reference slides.
    """
    available={str(source.get('number',i)) for i,source in enumerate(sources or [],1)
               if str(source.get('url','')).startswith('https://')}
    excluded={'research comparison','research findings','summary','scope','conclusion',
              'overview','introduction','findings','applications','recommendations',
              'evidence limitations','retrieved evidence excerpts','retrieved sources',
              'source comparison','uploaded evidence','how the sources differ',
              'applications described by publishers','source coverage and limitations'}
    lines=_lines(content); selected=[]; seen=set()
    for label,summary in zip(lines,lines[1:]):
        explicit_heading=label.startswith('#')
        label=label.lstrip('# ').rstrip(':').strip()
        if (not 4<=len(label)<=(90 if explicit_heading else 70) or label.casefold() in excluded or
                label.casefold() in seen or re.search(r'\[|\]|https?://',label) or
                (not explicit_heading and re.search(r'[.!?]',label)) or
                label.lower().startswith(('source comparison:','evidence gap:'))):
            continue
        citations=re.findall(r'\[(\d+)\]',summary)
        if (not citations or not set(citations)<=available or
                summary.lower().startswith(('source comparison:','evidence gap:'))):
            continue
        text=re.sub(r'\s*\[\d+\]','',summary).strip()
        # Labels and the visible summary must remain comfortably readable.
        # Long uninterrupted strings are kept on detail slides, not a diagram.
        if len(text)<25 or any(len(word)>36 for word in (label+' '+text).split()):
            continue
        shown=text
        if len(shown)>155:
            shown=shown[:152].rsplit(' ',1)[0].rstrip(' ,;:')+'…'
        selected.append(dict(label=label,text=shown,full_text=summary,
                             citations=' '.join(f'[{number}]' for number in dict.fromkeys(citations))))
        seen.add(label.casefold())
    # Two or three parallel branches are useful without shrinking body text.
    return selected[:3] if len(selected)>=2 else []


def _add_comparison_diagram(slide,items):
    """Native, editable hierarchy: findings contain parallel cited aspects."""
    from pptx.util import Inches,Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE,MSO_CONNECTOR
    from pptx.enum.text import PP_ALIGN,MSO_ANCHOR
    root=slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,Inches(4.9),Inches(2.35),Inches(3.5),Inches(.6))
    root.name='Comparison overview root'; root.fill.solid(); root.fill.fore_color.rgb=RGBColor(24,62,105)
    root.line.color.rgb=RGBColor(130,190,255)
    frame=root.text_frame; frame.word_wrap=True; frame.vertical_anchor=MSO_ANCHOR.MIDDLE
    p=frame.paragraphs[0]; p.text='Selected findings'; p.alignment=PP_ALIGN.CENTER
    p.font.name='Arial'; p.font.size=Pt(21); p.font.bold=True; p.font.color.rgb=RGBColor(236,243,255)
    count=len(items); width=(11.8-.35*(count-1))/count; centers=[]
    for index,item in enumerate(items): centers.append(.75+index*(width+.35)+width/2)
    # No arrowheads: these are sibling aspects, not a workflow or causal chain.
    def line(x1,y1,x2,y2):
        connector=slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,Inches(x1),Inches(y1),Inches(x2),Inches(y2))
        connector.name='Comparison overview branch'; connector.line.color.rgb=RGBColor(130,190,255); connector.line.width=Pt(1.5)
    line(6.65,2.95,6.65,3.25); line(centers[0],3.25,centers[-1],3.25)
    for index,(item,center) in enumerate(zip(items,centers)):
        left=.75+index*(width+.35); line(center,3.25,center,3.55)
        frame=slide.shapes.add_textbox(Inches(left),Inches(3.65),Inches(width),Inches(1.05)).text_frame
        frame.word_wrap=True; frame.margin_left=frame.margin_right=Inches(.05)
        shape=slide.shapes[-1]; shape.name=f'Comparison aspect {index+1}'
        visible_label=item['label']
        if len(visible_label)>58: visible_label=visible_label[:55].rsplit(' ',1)[0]+'…'
        p=frame.paragraphs[0]; p.text=visible_label; p.font.name='Arial'; p.font.size=Pt(18 if len(visible_label)>42 else 21); p.font.bold=True; p.font.color.rgb=RGBColor(236,243,255)
        frame=slide.shapes.add_textbox(Inches(left),Inches(4.8),Inches(width),Inches(1.5)).text_frame
        frame.word_wrap=True; frame.margin_left=frame.margin_right=Inches(.05)
        slide.shapes[-1].name=f'Comparison summary {index+1}'
        p=frame.paragraphs[0]; p.text=item['text']; p.font.name='Arial'; p.font.size=Pt(17); p.font.color.rgb=RGBColor(202,216,240)
        frame=slide.shapes.add_textbox(Inches(left),Inches(6.35),Inches(width),Inches(.35)).text_frame
        frame.margin_top=frame.margin_bottom=0; frame.margin_left=frame.margin_right=Inches(.05)
        slide.shapes[-1].name=f'Comparison references {index+1}'
        p=frame.paragraphs[0]; p.text=item['citations']; p.font.name='Arial'; p.font.size=Pt(16); p.font.color.rgb=RGBColor(130,190,255)
    slide.notes_slide.notes_text_frame.text=('Parallel aspects from the report; connectors indicate membership only, not sequence or causation. '
        'Overview summaries may be abbreviated; complete findings and source URLs follow.\n\n'+
        '\n\n'.join(item['label']+'\n'+item['full_text'] for item in items))


def _write_pptx(path,title,content,sources):
    from pptx import Presentation
    from pptx.util import Inches,Pt
    from pptx.dml.color import RGBColor
    prs=Presentation(); prs.slide_width=Inches(13.333); prs.slide_height=Inches(7.5); chunks=_chunks(content)
    if len(chunks)>45: raise ValueError("Presentation exceeds 45 content slides")
    def add(label,body,links=None):
        slide=prs.slides.add_slide(prs.slide_layouts[6]); slide.background.fill.solid(); slide.background.fill.fore_color.rgb=RGBColor(10,18,34)
        frame=slide.shapes.add_textbox(Inches(.75),Inches(.65),Inches(11.8),Inches(1.1)).text_frame; frame.word_wrap=True; p=frame.paragraphs[0]; p.text=label; p.font.name="Arial"; p.font.size=Pt(24 if len(label)>110 else 28); p.font.bold=True; p.font.color.rgb=RGBColor(236,243,255)
        frame=slide.shapes.add_textbox(Inches(.8),Inches(1.95),Inches(11.6),Inches(4.5)).text_frame; frame.word_wrap=True
        for i,line in enumerate(body.splitlines()):
            p=frame.paragraphs[0] if i==0 else frame.add_paragraph(); p.text=line; p.font.name="Arial"; p.font.size=Pt(20); p.font.color.rgb=RGBColor(202,216,240); p.space_after=Pt(8)
            if line.startswith("https://"):
                for run in p.runs:
                    # Do not turn a retrieval warning containing a URL plus an
                    # error description into a malformed hyperlink.
                    target=(links or {}).get(line,line if not any(ch.isspace() for ch in line) else None)
                    if target: run.hyperlink.address=target
                    run.font.color.rgb=RGBColor(130,190,255)
        frame=slide.shapes.add_textbox(Inches(.8),Inches(6.9),Inches(11),Inches(.3)).text_frame; p=frame.paragraphs[0]; p.text=f"NEXUS AI | {len(prs.slides)}"; p.font.size=Pt(10); p.font.color.rgb=RGBColor(127,155,200)
        slide.notes_slide.notes_text_frame.text=body
        return slide
    add(title,"Research findings and supporting evidence\nReview source references and evidence limitations in the following slides.")
    overview=_comparison_overview(content,sources)
    if overview:
        slide=add('Compared aspects','Evidence cited for each aspect; detailed findings follow.')
        # The ordinary body placeholder only contains the short subtitle;
        # limit its geometry so it cannot overlap editable diagram objects.
        slide.shapes[1].height=Inches(.4)
        _add_comparison_diagram(slide,overview)
    for i,body in enumerate(chunks,1):
        parts=body.splitlines(); first=parts[0]
        if _is_heading(first) and len(parts)>1 and len(first)<95:
            add(first.lstrip("# ").rstrip(":"),"\n".join(line.lstrip("# ") for line in parts[1:]))
        else: add(f"Findings {i}","\n".join(line.lstrip("# ") for line in parts))
    for group in _reference_groups(sources):
        slide=add("Retrieved sources",group["text"],group["links"])
        slide.notes_slide.notes_text_frame.text=group["full_text"]
    prs.core_properties.title=title; prs.core_properties.author="NEXUS AI"; prs.save(path)
    # PowerPoint overrides explicit run colors for hyperlinks with theme hlink.
    # Set a readable theme color for the dark slide background as well.
    from lxml import etree
    buffer=io.BytesIO()
    ns={"a":"http://schemas.openxmlformats.org/drawingml/2006/main"}
    with zipfile.ZipFile(path) as original,zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as revised:
        for entry in original.infolist():
            data=original.read(entry.filename)
            if entry.filename.startswith("ppt/theme/") and entry.filename.endswith(".xml"):
                tree=etree.fromstring(data)
                for key,color in [("hlink","82BEFF"),("folHlink","C4A8FF")]:
                    for node in tree.findall(f".//a:clrScheme/a:{key}",ns):
                        for child in list(node): node.remove(child)
                        etree.SubElement(node,"{"+ns["a"]+"}srgbClr",val=color)
                data=etree.tostring(tree,xml_declaration=True,encoding="UTF-8",standalone=True)
            revised.writestr(entry,data)
    path.write_bytes(buffer.getvalue())


def _check_zip(path,root):
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if len(entries)>600 or sum(e.file_size for e in entries)>20_000_000: raise ValueError("Office archive exceeds extraction limits")
        for e in entries:
            name=e.filename.replace("\\","/"); p=PurePosixPath(name)
            if p.is_absolute() or ".." in p.parts or ":" in name or e.flag_bits&1: raise ValueError("Unsafe or encrypted Office archive")
            if e.file_size>8_000_000 or e.file_size/max(e.compress_size,1)>200: raise ValueError("Office decompression limit exceeded")
            if "vbaproject" in name.lower() or name.lower().endswith((".exe",".dll",".js")) or "/embeddings/" in name: raise ValueError("Macros and embedded files unsupported")
        names={e.filename for e in entries}
        if "[Content_Types].xml" not in names or root not in names: raise ValueError("Office format signature mismatch")
        if archive.testzip(): raise ValueError("Corrupt Office archive")


def _pdf_extract(path):
    from pypdf import PdfReader,apply_configuration
    with apply_configuration(maximum_declared_stream_length=4_000_000,array_based_stream_maximum_output_length=4_000_000,zlib_maximum_output_length=4_000_000,lzw_maximum_output_length=4_000_000,run_length_maximum_output_length=4_000_000,brotli_maximum_output_length=4_000_000,stream_decoding_work_maximum_length=12_000_000,page_tree_maximum_entries=1000,stream_parsing_work_maximum_count=200_000,jbig2dec_binary=None):
        reader=PdfReader(path,strict=True)
        if reader.is_encrypted: raise ValueError("Encrypted PDF unsupported")
        if len(reader.pages)>60: raise ValueError("PDF exceeds 60 pages")
        parts=[]
        for page in reader.pages:
            parts.append(page.extract_text() or "")
            if sum(map(len,parts))>MAX_EXTRACT: raise ValueError("PDF extracted text exceeds limit")
        return "\n".join(parts)


def extract_upload(path:Path)->str:
    path=Path(path)
    if not path.is_file() or path.stat().st_size>MAX_UPLOAD_BYTES: raise ValueError("File missing or larger than 10 MB")
    fmt=path.suffix.lower().lstrip(".")
    if fmt not in FORMATS: raise ValueError("Unsupported upload format")
    with path.open("rb") as stream: prefix=stream.read(12)
    if fmt in {"docx","xlsx","pptx"}:
        if not prefix.startswith(b"PK"): raise ValueError("Invalid Office signature")
        _check_zip(path,{"docx":"word/document.xml","xlsx":"xl/workbook.xml","pptx":"ppt/presentation.xml"}[fmt])
    if fmt=="pdf":
        if not prefix.startswith(b"%PDF-"): raise ValueError("Invalid PDF signature")
        text=_pdf_extract(path)
    elif fmt=="docx":
        from docx import Document
        doc=Document(path); text="\n".join([p.text for p in doc.paragraphs]+["\t".join(c.text for c in row.cells) for table in doc.tables for row in table.rows])
    elif fmt=="xlsx":
        from openpyxl import load_workbook
        wb=load_workbook(path,read_only=True,data_only=True,keep_links=False); parts=[]; count=0
        try:
            if len(wb.sheetnames)>20: raise ValueError("Workbook exceeds 20 sheets")
            for sheet in wb:
                if sheet.max_row>5000 or sheet.max_column>50: raise ValueError("Workbook dimensions exceed limits")
                parts.append("Worksheet: "+sheet.title)
                for row in sheet.iter_rows(values_only=True):
                    count+=len(row)
                    if count>30_000: raise ValueError("Workbook exceeds cell limit")
                    parts.append("\t".join(str(v) if v is not None else "" for v in row))
                    if sum(map(len,parts))>MAX_EXTRACT: raise ValueError("Workbook text exceeds limit")
        finally: wb.close()
        text="\n".join(parts)
    elif fmt=="pptx":
        from pptx import Presentation
        prs=Presentation(path)
        if len(prs.slides)>60: raise ValueError("Presentation exceeds 60 slides")
        text="\n".join(s.text for slide in prs.slides for s in slide.shapes if s.has_text_frame)
    else:
        raw=path.read_bytes()
        if b"\0" in raw: raise ValueError("Binary content in text upload")
        try: text=raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc: raise ValueError("Text uploads require UTF-8") from exc
        if len(text)>MAX_EXTRACT: raise ValueError("Extracted text exceeds 100,000 characters")
        if fmt=="json":
            try: json.loads(text)
            except (json.JSONDecodeError,RecursionError) as exc: raise ValueError("Invalid JSON or excessive JSON nesting") from exc
        if fmt=="csv":
            rows=list(csv.reader(io.StringIO(text)))
            if len(rows)>5000 or any(len(row)>50 for row in rows): raise ValueError("CSV exceeds row or column limits")
    if len(text)>MAX_EXTRACT: raise ValueError("Extracted text exceeds 100,000 characters")
    text=re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]","",text).strip()
    if not text: raise ValueError("No readable text; scanned files require unavailable OCR")
    return text


def artifact_metadata(path:Path,verification:dict)->dict:
    path=Path(path)
    return {"name":path.name,"filename":path.name,"format":path.suffix[1:],"size":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"verified":True,"verification":verification}


def generate_files(directory:Path,title:str,content:str,formats:list[str],sources=None,rows=None)->list[dict]:
    if not isinstance(title,str) or not title.strip() or len(title)>200: raise ValueError("Title must contain 1–200 characters")
    if not isinstance(content,str) or not 1<=len(content.strip())<=MAX_CONTENT: raise ValueError("File content must contain 1–50,000 characters")
    if not formats or len(formats)>7 or len(set(formats))!=len(formats) or any(f not in FORMATS for f in formats): raise ValueError("Unsupported or repeated file format")
    if rows is not None and (not isinstance(rows,list) or not 2<=len(rows)<=2001 or not 1<=len(rows[0])<=30 or any(not isinstance(row,list) or len(row)!=len(rows[0]) or any(not isinstance(v,(str,int,float,bool,type(None))) or len(str(v))>2000 for v in row) for row in rows)): raise ValueError("Invalid table: header plus up to 2,000 rows and 30 columns")
    sources=sources or []
    if len(sources)>20: raise ValueError("At most 20 sources per artifact")
    content=re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]","",content.strip()); title=title.strip(); directory=Path(directory).resolve(); directory.mkdir(parents=True,exist_ok=True)
    identifier=uuid4().hex; result=[]
    for fmt in formats:
        path=safe_child(directory,f"{identifier}.{fmt}")
        if path.exists(): raise ValueError("Artifact already exists")
        try:
            if fmt=="pdf": _write_pdf(path,title,content,sources)
            elif fmt=="docx": _write_docx(path,title,content,sources,rows)
            elif fmt=="xlsx": _write_xlsx(path,title,content,sources,rows)
            elif fmt=="pptx": _write_pptx(path,title,content,sources)
            elif fmt=="txt": path.write_text(f"{title}\n\n{content}\n\n"+"\n\n".join(_refs(sources)),encoding="utf-8")
            elif fmt=="json":
                source_metadata=[{k:v for k,v in source.items() if k not in {"text","paragraphs","evidence"}} for source in sources]
                path.write_text(json.dumps({"title":title,"content":content,"sources":source_metadata,"rows":rows},ensure_ascii=False,indent=2),encoding="utf-8")
            elif fmt=="csv":
                with path.open("w",newline="",encoding="utf-8-sig") as stream: csv.writer(stream).writerows([[safe_text(v) for v in row] for row in rows] if rows else [["Title","Content","Sources"],[safe_text(title),safe_text(content),"\n\n".join(_refs(sources))]])
            if path.stat().st_size>MAX_UPLOAD_BYTES: raise ValueError("Generated artifact exceeds 10 MB")
            text=extract_upload(path); norm=lambda v:re.sub(r"\s+","",str(v)).casefold(); expected=str(rows[1][0]) if fmt=="csv" and rows else title
            if norm(expected) not in norm(text): raise RuntimeError(f"{fmt.upper()} expected title/table content missing after reopening")
            paragraphs=_lines(content)
            samples=[paragraphs[i].lstrip("# ").rstrip(":")[:60] for i in sorted({0,len(paragraphs)//2,len(paragraphs)-1})]
            if fmt not in {"csv","json"} and any(norm(sample) not in norm(text) for sample in samples): raise RuntimeError(f"{fmt.upper()} expected report content missing after reopening")
            artifact=artifact_metadata(path,{"parser_reopened":True,"expected_content_present":True,"text_characters":len(text),"factual_accuracy_verified":False,"note":"Structure and expected text verified; claims require review."})
            slug=re.sub(r"[^A-Za-z0-9]+","-",title).strip("-")[:80] or "NEXUS-report"
            artifact["name"]=f"{slug}.{fmt}"; result.append(artifact)
        except Exception:
            path.unlink(missing_ok=True); raise
    return result
