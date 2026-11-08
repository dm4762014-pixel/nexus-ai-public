"""Editable comparisons preserve attribution without inventing a workflow."""
import re

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from nexus.files import _comparison_overview, extract_upload, generate_files


SOURCES=[
    {'number':4,'title':'Storage evidence','url':'https://example.com/storage'},
    {'number':9,'title':'Power evidence','url':'https://example.org/power'},
]
CONTENT='''Research comparison
The retrieved sources describe different applications and limits.

Grid storage
Batteries store electricity for use after renewable generation decreases [4].
Source comparison: This aspect has evidence from one publisher.

Power conversion
Inverters convert direct current into alternating current for use on the grid [9].
Source comparison: This aspect has evidence from one publisher.

Demand response
Demand response adjusts electricity consumption when grid operators need flexibility [4] [9].
Source comparison: Both retrieved sources cover this aspect without independent validation.

Source coverage and limitations
Selected passages cannot establish a current consensus or verify deployment claims.
'''


def test_comparison_overview_uses_exact_report_labels_and_registry_citations():
    items=_comparison_overview(CONTENT,SOURCES)
    assert [item['label'] for item in items]==['Grid storage','Power conversion','Demand response']
    assert [item['citations'] for item in items]==['[4]','[9]','[4] [9]']
    assert all(item['full_text'] in CONTENT for item in items)
    assert all(item['text']==re.sub(r'\s*\[\d+\]','',item['full_text']).strip() for item in items)


def test_diagram_is_native_editable_and_has_no_sequential_arrows(tmp_path):
    [artifact]=generate_files(tmp_path,'Grid applications',CONTENT,['pptx'],sources=SOURCES)
    deck=Presentation(tmp_path/artifact['filename'])
    overview=next(slide for slide in deck.slides if slide.shapes[0].text=='Compared aspects')
    native=[shape for shape in overview.shapes if shape.name.startswith('Comparison ')]
    assert any(shape.shape_type==MSO_SHAPE_TYPE.AUTO_SHAPE for shape in native)
    branches=[shape for shape in native if shape.shape_type==MSO_SHAPE_TYPE.LINE]
    assert len(branches)==5  # Shared stem, horizontal branch, three sibling leaves.
    assert all('headEnd' not in shape._element.xml and 'tailEnd' not in shape._element.xml for shape in branches)
    assert all(shape.shape_type!=MSO_SHAPE_TYPE.PICTURE for shape in overview.shapes)
    for shape in overview.shapes:
        assert 0<=shape.left and 0<=shape.top
        assert shape.left+shape.width<=deck.slide_width
        assert shape.top+shape.height<=deck.slide_height
    notes=overview.notes_slide.notes_text_frame.text
    assert 'not sequence or causation' in notes
    for item in _comparison_overview(CONTENT,SOURCES):
        assert item['full_text'] in notes
        assert any(shape.has_text_frame and shape.text==item['label'] for shape in overview.shapes)
        assert any(shape.has_text_frame and shape.text==item['citations'] for shape in overview.shapes)
    # The diagram supplements rather than replacing the report and references.
    extracted=extract_upload(tmp_path/artifact['filename'])
    for line in CONTENT.splitlines():
        if line.strip(): assert line in extracted
    for source in SOURCES:
        assert source['url'] in extracted


def test_overview_is_skipped_for_unstructured_uncited_and_unknown_evidence(tmp_path):
    for content,sources in [
        ('A simple report paragraph.\nAnother paragraph that needs no diagram.',SOURCES),
        ('First topic\nAn uncited summary describes a finding.\nSecond topic\nAnother uncited summary describes a finding.',SOURCES),
        (CONTENT,[]),
        (CONTENT,[{'number':1,'url':'https://example.com/unrelated'}]),
    ]:
        assert _comparison_overview(content,sources)==[]
        [artifact]=generate_files(tmp_path,'Simple report',content,['pptx'],sources=sources)
        deck=Presentation(tmp_path/artifact['filename'])
        assert not any(shape.name=='Comparison overview root' for slide in deck.slides for shape in slide.shapes)


def test_single_aspect_and_limitations_do_not_become_comparison():
    assert _comparison_overview('Overview\nA general statement with a reference [4].\nGrid storage\nBatteries store electricity for later use [4].\nEvidence limitations\nThis report has not been independently checked [9].',SOURCES)==[]


def test_overview_abbreviates_only_visible_copy_and_preserves_full_notes(tmp_path):
    summary='Battery storage '+('supports renewable generation when supply varies across the day, '*4)+'with operating constraints [4].'
    content='Grid storage\n'+summary+'\nPower conversion\nInverters change the current type for grid operation [9].'
    items=_comparison_overview(content,SOURCES)
    assert len(items)==2 and len(items[0]['text'])<=155
    assert items[0]['text'].endswith('…') and items[0]['full_text']==summary
    [artifact]=generate_files(tmp_path,'Energy comparison',content,['pptx'],sources=SOURCES)
    deck=Presentation(tmp_path/artifact['filename'])
    overview=next(slide for slide in deck.slides if slide.shapes[0].text=='Compared aspects')
    assert summary in overview.notes_slide.notes_text_frame.text
    assert summary in '\n'.join(slide.notes_slide.notes_text_frame.text for slide in deck.slides if slide!=overview)


def test_more_aspects_are_bounded_without_removing_detailed_findings(tmp_path):
    extra='\nEnergy monitoring\nMonitoring makes electricity demand patterns visible to grid operators [4].'
    assert len(_comparison_overview(CONTENT+extra,SOURCES))==3
    [artifact]=generate_files(tmp_path,'Bounded comparison',CONTENT+extra,['pptx'],sources=SOURCES)
    assert 'Energy monitoring' in extract_upload(tmp_path/artifact['filename'])

def test_explicit_long_source_headings_allow_punctuation_and_preserve_full_notes(tmp_path):
    label='Source 4: Which storage designs support the grid? A publisher perspective'
    content='# '+label+'\nBattery storage can shift renewable electricity to other periods [4].\n# Source 9: Power conversion\nInverters convert electricity into a form used on the grid [9].'
    items=_comparison_overview(content,SOURCES)
    assert len(items)==2 and items[0]['label']==label
    [artifact]=generate_files(tmp_path,'Publisher perspectives',content,['pptx'],sources=SOURCES)
    deck=Presentation(tmp_path/artifact['filename'])
    overview=next(slide for slide in deck.slides if slide.shapes[0].text=='Compared aspects')
    assert label in overview.notes_slide.notes_text_frame.text
    shown=next(shape.text for shape in overview.shapes if shape.name=='Comparison aspect 1')
    assert shown.endswith('…') and len(shown)<=58
