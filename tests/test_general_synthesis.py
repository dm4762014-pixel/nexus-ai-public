import json
import re

import pytest

from nexus.general_synthesis import select_evidence, source_groups, synthesize_general_comparison
from nexus.research import extract_document, research_web, validate_citations


QUERY = 'Research renewable energy and storage and compare reliable sources'
SOURCES = [
    dict(number=1, title='Grid research', url='https://grid.example/report', text=(
        'Renewable electricity from wind and solar varies with weather, so storage supplies energy when production falls below demand.\n\n'
        'Battery storage shifts electricity between periods, while its usable capacity and cycling requirements constrain the service it supplies.')),
    dict(number=2, title='Storage research', url='https://storage.example/report', text=(
        'Energy storage shifts electricity supply over time, but storage technologies differ in their response characteristics and siting requirements.\n\n'
        'Pumped storage requires suitable geography and reservoirs, while batteries are modular and depend on material supply and replacement.')),
    dict(number=3, title='System research', url='https://systems.example/report', text=(
        'Renewable energy integration depends on transmission, demand flexibility and storage rather than storage alone in every electricity system.\n\n'
        'Storage choices depend on the intended service and local conditions; no single storage technology is suitable for every grid application.')),
]


class GeneralModel:
    def complete_json(self, system, prompt, output_model, tokens):
        self.system, self.prompt, self.tokens = system, prompt, tokens
        groups = json.loads(prompt)['groups']
        assert [group['id'] for group in groups] == [1, 2, 3]
        assert all(len(group['passages']) == 1 for group in groups)
        assert 'question' not in json.loads(prompt)
        return dict(findings=[
            dict(id=1, text='Wind and solar output depends on weather, with storage supplying electricity when generation does not meet demand.'),
            dict(id=2, text='Storage shifts electricity across periods, while technologies vary in response characteristics and requirements for suitable sites.'),
            dict(id=3, text='Integrating renewable energy involves storage, transmission and flexible demand rather than relying on storage alone.'),
        ])


def test_general_comparison_paraphrases_and_preserves_exact_source_mapping():
    model = GeneralModel()
    result = synthesize_general_comparison(QUERY, SOURCES, model)
    assert result['summary_mode'] == 'general_evidence_comparison'
    assert result['comparison_heading'] == 'Aspect'
    assert '# Source 1: Grid research\n' in result['answer']
    assert '# Source coverage and limitations\n' in result['answer']
    assert len(result['comparison']) == 3
    assert [row['source_numbers'] for row in result['comparison']] == [[1], [2], [3]]
    assert 'agreement or disagreement has not been independently established' in result['answer']
    assert 'independent corroboration is limited' in result['answer']
    assert 'missing coverage is not proof that a publisher disagrees' in result['answer']
    assert validate_citations(result['answer'], SOURCES)
    assert model.tokens <= 280
    assert len(model.prompt) < 3500
    assert 'untrusted data' in model.system
    indexed = {source['number']: source for source in SOURCES}
    for claim in result['claims']:
        assert {item['source_number'] for item in claim['evidence']} == set(claim['source_numbers'])
        for item in claim['evidence']:
            assert item['quote'] in indexed[item['source_number']]['text']
        assert all(claim['text'] not in source['text'] for source in SOURCES)


def test_cloud_definitions_are_readable_general_evidence_without_security_verbs():
    text = ('Cloud computing is the delivery of computing resources over a network, including servers, storage and software. '
            'Public cloud services provide shared infrastructure, while private cloud services are dedicated to an organization.')
    document = extract_document(('<article><p>' + text + '</p></article>').encode(), 'text/html', 'Research cloud computing')
    assert document['text'] == text
    source = dict(number=1, title='Cloud definition', url='https://cloud.example', text=text)
    evidence = select_evidence('Research cloud computing', [source])
    assert all(item['quote'] in text for item in evidence.values())


def test_evidence_selection_is_bounded_deterministic_and_does_not_split_sentences():
    first = select_evidence(QUERY, SOURCES)
    assert first == select_evidence(QUERY, SOURCES)
    assert len(first) <= 6
    assert sum(len(item['quote']) for item in first.values()) <= 1800
    assert {item['source_number'] for item in first.values()} == {1, 2, 3}
    assert all(len(item['quote']) <= 450 and item['quote'].endswith('.') for item in first.values())


@pytest.mark.parametrize('mutation', ['unknown', 'duplicate', 'boolean', 'string', 'omitted_source', 'invented_aspect', 'copied', 'numeric', 'citation', 'extra_field'])
def test_invalid_model_output_is_rejected(mutation):
    class Invalid(GeneralModel):
        def complete_json(self, *args, **kwargs):
            result = super().complete_json(*args, **kwargs)
            row = result['findings'][0]
            if mutation == 'unknown': row['id'] = 7
            if mutation == 'duplicate': result['findings'][1]['id'] = row['id']
            if mutation == 'boolean': row['id'] = True
            if mutation == 'string': row['id'] = str(row['id'])
            if mutation == 'omitted_source': result['findings'].pop()
            if mutation == 'invented_aspect': row['aspect'] = 'Quantum teleportation'
            if mutation == 'copied': row['text'] = SOURCES[0]['text'].split('\n\n')[0]
            if mutation == 'numeric': row['text'] += ' It costs 20 percent less.'
            if mutation == 'citation': row['text'] += ' [99]'
            if mutation == 'extra_field': row['untrusted'] = 'extra output'
            return result
    with pytest.raises(ValueError):
        synthesize_general_comparison(QUERY, SOURCES, Invalid())


def _mock_retrieval(monkeypatch):
    import nexus.research
    monkeypatch.setattr(nexus.research, 'search_candidates', lambda *args, **kwargs: [dict(href=source['url'], title=source['title']) for source in SOURCES])
    def fetch(url, **kwargs):
        source = next(source for source in SOURCES if source['url'] == url)
        return dict(url=url, content_type='text/html', body=('<title>' + source['title'] + '</title><article>' + ''.join('<p>' + passage + '</p>' for passage in source['text'].split('\n\n')) + '</article>').encode())
    monkeypatch.setattr(nexus.research, 'fetch_public', fetch)


def test_research_retrieval_uses_general_structured_comparison(monkeypatch):
    _mock_retrieval(monkeypatch)
    result = research_web(QUERY, GeneralModel())
    assert len(result['sources']) == 3
    assert result['summary_mode'] == 'general_evidence_comparison'
    assert result['comparison_heading'] == 'Aspect'
    assert result['comparison']
    assert not result['failures']
    assert 'Retrieved evidence excerpts' not in result['answer']


def test_invalid_general_synthesis_falls_back_explicitly_without_partial_rows(monkeypatch):
    _mock_retrieval(monkeypatch)
    class Invalid(GeneralModel):
        def complete_json(self, *args, **kwargs):
            return {'findings': [{'id': 99, 'text': 'An invented claim should not become a validated research finding.'}]}
    result = research_web(QUERY, Invalid())
    assert result['summary_mode'] == 'retrieved_excerpts'
    assert result['comparison'] == []
    assert any('Model synthesis unavailable or invalid' in warning for warning in result['warnings'])
    assert 'invented claim' not in result['answer']
    assert validate_citations(result['answer'], result['sources'])


def test_single_source_comparison_honestly_limits_corroboration():
    class Single:
        def complete_json(self, system, prompt, output_model, tokens):
            return dict(findings=[dict(id=1, text='Weather variability influences renewable electricity supply, with storage helping shift the timing of available energy.')])
    result = synthesize_general_comparison(QUERY, SOURCES[:1], Single())
    assert 'independent corroboration is limited' in result['answer']
    assert result['claims'][0]['source_numbers'] == [1]


def test_checkpoint_cancellation_is_not_converted_to_a_successful_summary():
    def checkpoint():
        raise RuntimeError('Cancelled')
    with pytest.raises(RuntimeError, match='Cancelled'):
        synthesize_general_comparison(QUERY, SOURCES, GeneralModel(), checkpoint)


def test_paragraph_metadata_cannot_introduce_evidence_absent_from_retrieved_text():
    source = dict(SOURCES[0], paragraphs=[
        'A fabricated storage explanation provides unsupported claims absent from the retained source document and must be rejected.'
    ])
    with pytest.raises(ValueError, match='No bounded descriptive passages'):
        select_evidence(QUERY, [source])


def test_fixed_groups_use_source_registry_numbers_not_model_selected_passages():
    sources = [dict(source, number=number) for source, number in zip(SOURCES, [3, 8, 11])]
    groups = source_groups(QUERY, sources)
    assert [group['id'] for group in groups] == [1, 2, 3]
    result = synthesize_general_comparison(QUERY, sources, GeneralModel())
    assert [claim['source_numbers'] for claim in result['claims']] == [[3], [8], [11]]
    assert validate_citations(result['answer'], sources)


def test_publisher_footnotes_are_removed_only_from_model_input():
    sources = [dict(SOURCES[0], text=SOURCES[0]['text'].replace('storage supplies', 'storage [42] [1, 9] supplies'))]
    class Capture:
        def complete_json(self, system, prompt, output_model, tokens):
            assert '[42]' not in prompt and '[1, 9]' not in prompt
            assert json.loads(prompt)['groups'][0]['id'] == 1
            return dict(findings=[dict(id=1, text='Weather variability influences renewable electricity supply, with storage helping shift the timing of available energy.')])
    result = synthesize_general_comparison(QUERY, sources, Capture())
    assert any('[42]' in item['quote'] for item in result['claims'][0]['evidence'])
    assert '[42]' not in result['answer']


@pytest.mark.parametrize('text', [
    'Storage supplies renewable electricity, while PostgreSQL on the other hand,',
    'Storage supplies renewable electricity and supports grid operations at high-',
    'Storage shifts renewable electricity supply. Batteries have different requirements.',
    'Storage shifts renewable electricity supply...',
    'Storage shifts renewable electricity supply…',
    'Storage shifts renewable electricity supply and.',
    'Storage shifts renewable electricity supply with.',
    'Storage shifts renewable electricity supply on the other hand.',
    'Storage shifts renewable electricity supply, .',
])
def test_incomplete_or_multiple_sentences_are_rejected(text):
    class Invalid(GeneralModel):
        def complete_json(self, *args, **kwargs):
            result = super().complete_json(*args, **kwargs)
            result['findings'][0]['text'] = text
            return result
    with pytest.raises(ValueError):
        synthesize_general_comparison(QUERY, SOURCES, Invalid())


def test_source_perspective_heading_is_bounded_at_a_word_boundary():
    source = dict(SOURCES[0], title='An unusually long publisher title discussing electricity storage and renewable energy system design requirements')
    group = source_groups(QUERY, [source])[0]
    assert len(group['label']) <= 58
    assert source['title'].startswith(group['label'].split(': ', 1)[1])
    assert source['title'] == 'An unusually long publisher title discussing electricity storage and renewable energy system design requirements'


def test_source_group_exposes_only_one_complete_sentence_and_retains_exact_provenance():
    for group in source_groups(QUERY, SOURCES):
        assert len(group['evidence']) == 1
        quote = group['evidence'][0]['quote']
        assert len(re.split(r'(?<=[.!?])\s+', quote)) == 1
        assert quote in SOURCES[group['source_number'] - 1]['text']


@pytest.mark.parametrize('introduced_actor', ['PostgreSQL', 'postgresql'])
def test_model_cannot_introduce_a_query_actor_from_another_sentence(introduced_actor):
    first = 'SQLite uses database-level locking to coordinate writers, which restricts the write concurrency available to applications.'
    second = 'PostgreSQL supports concurrent sessions and supplies additional coordination capabilities for shared database workloads.'
    source = dict(number=1, title='Database comparison', url='https://database.example', text=first + ' ' + second)
    class Invented:
        def complete_json(self, system, prompt, output_model, tokens):
            group = json.loads(prompt)['groups'][0]
            assert group['passages'] == [first]
            assert 'PostgreSQL' not in prompt
            return dict(findings=[dict(id=1, text=introduced_actor + ' uses database-level locking to manage writer access and restrict concurrent writes in shared applications.')])
    with pytest.raises(ValueError, match='named query actor'):
        synthesize_general_comparison('Research SQLite and PostgreSQL database differences', [source], Invented())


EXTRA_SENTENCES = [
    'Battery projects require replacement planning and material sourcing, which affect their maintenance obligations over the equipment lifetime.',
    'Thermal storage retains heat rather than electricity directly, so its suitable uses depend on the intended heating or conversion process.',
    'Grid planning requires coordination between network operators and storage owners to establish the service needed at each location.',
]
PARAPHRASES = [
    'Wind and solar output depends on weather, with storage supplying electricity when generation does not meet demand.',
    'Battery capacity and cycling requirements constrain how stored electricity shifts between periods to supply the intended service.',
    'Battery maintenance planning includes material sourcing and equipment replacement obligations over its operating lifetime.',
    'Storage shifts electricity across periods, while technologies vary in response characteristics and requirements for suitable sites.',
    'Reservoir storage depends on geography, whereas modular batteries depend on material availability and eventual replacement.',
    'Heat storage serves heating or conversion needs, with suitability determined by its intended use rather than direct electricity retention.',
    'Integrating renewable energy involves storage, transmission and flexible demand rather than relying on storage alone.',
    'Local conditions and the intended grid service influence storage selection because a single technology cannot suit every application.',
    'Network operators and storage owners coordinate planning to determine which service is required at a particular location.',
]


def _rich_sources():
    return [dict(source, text=source['text'] + '\n\n' + extra) for source, extra in zip(SOURCES, EXTRA_SENTENCES)]


class RichModel:
    def __init__(self):
        self.calls = []
        self.responses = {}
        for index, source in enumerate(_rich_sources()):
            for detail, sentence in enumerate(source['text'].split('\n\n')):
                self.responses[sentence] = PARAPHRASES[index * 3 + detail]

    def complete_json(self, system, prompt, output_model, tokens):
        groups = json.loads(prompt)['groups']
        self.calls.append(groups)
        assert len(groups) <= 3 and tokens == 280
        assert all(len(group['passages']) == 1 for group in groups)
        return dict(findings=[dict(id=group['id'], text=self.responses[group['passages'][0]]) for group in groups])


def test_fuller_default_returns_nine_distinct_grounded_findings_in_three_small_batches():
    sources, model = _rich_sources(), RichModel()
    result = synthesize_general_comparison(QUERY, sources, model)
    assert len(model.calls) == 3
    assert result['detail_count'] == 9 and result['detail_limit'] == 3
    assert len(result['comparison']) == 9 and not result['warnings']
    assert result['answer'].count('# Source 1: Grid research\n') == 1
    assert result['answer'].count('independent corroboration is limited') == 1
    assert len({claim['text'] for claim in result['claims']}) == 9
    assert len({claim['evidence'][0]['quote'] for claim in result['claims']}) == 9
    for claim in result['claims']:
        assert len(claim['evidence']) == 1
        source = next(source for source in sources if source['number'] == claim['source_numbers'][0])
        assert claim['evidence'][0]['quote'] in source['text']
    assert validate_citations(result['answer'], sources)


@pytest.mark.parametrize('failure', ['invalid', 'unavailable', 'duplicate'])
def test_optional_detail_failure_preserves_validated_main_source_coverage(failure):
    class LaterFailure(RichModel):
        def complete_json(self, *args, **kwargs):
            if self.calls:
                if failure == 'unavailable':
                    raise TimeoutError('optional provider timeout')
                if failure == 'invalid':
                    return {'findings': [{'id': 99, 'text': 'An invalid extra finding must not replace useful validated findings from the main research batch.'}]}
                return dict(findings=[dict(id=index + 1, text=text) for index, text in enumerate([PARAPHRASES[0], PARAPHRASES[3], PARAPHRASES[6]])])
            return super().complete_json(*args, **kwargs)
    result = synthesize_general_comparison(QUERY, _rich_sources(), LaterFailure())
    assert result['detail_count'] == 3
    assert {claim['source_numbers'][0] for claim in result['claims']} == {1, 2, 3}
    assert len(result['warnings']) == 1
    assert 'validated main findings are retained' in result['answer']


def test_cancellation_after_optional_round_propagates_instead_of_retaining_a_success_result():
    model, checks = RichModel(), []
    def checkpoint():
        checks.append(True)
        if len(checks) == 4:
            raise RuntimeError('Cancelled after optional round')
    with pytest.raises(RuntimeError, match='Cancelled after optional round'):
        synthesize_general_comparison(QUERY, _rich_sources(), model, checkpoint)
    assert len(model.calls) == 2


@pytest.mark.parametrize('short_instruction', ['Keep it brief', 'Write a short report'])
def test_explicit_short_request_uses_only_one_main_batch(short_instruction):
    model = RichModel()
    result = synthesize_general_comparison(QUERY + '. ' + short_instruction, _rich_sources(), model)
    assert len(model.calls) == 1
    assert result['detail_count'] == 3 and result['detail_limit'] == 1
    assert not result['warnings']


def test_sparse_source_returns_one_real_finding_without_padding():
    source = dict(SOURCES[0], text=SOURCES[0]['text'].split('\n\n')[0])
    model = RichModel()
    result = synthesize_general_comparison(QUERY, [source], model)
    assert len(model.calls) == 1 and result['detail_count'] == 1
    assert 'no additional facts were added to fill the report' in result['answer']


@pytest.mark.parametrize('bad_point', ['numeric', 'copied', 'duplicate'])
def test_one_bad_optional_point_retains_other_points_and_collects_later_batch(bad_point):
    class Partial(RichModel):
        def complete_json(self, *args, **kwargs):
            result = super().complete_json(*args, **kwargs)
            if len(self.calls) == 2:
                if bad_point == 'numeric':
                    result['findings'][0]['text'] = 'Battery systems provide 20 percent higher efficiency when their capacity and cycling requirements support the intended service.'
                elif bad_point == 'copied':
                    result['findings'][0]['text'] = self.calls[-1][0]['passages'][0]
                else:
                    result['findings'][0]['text'] = PARAPHRASES[0]
            return result
    model = Partial()
    result = synthesize_general_comparison(QUERY, _rich_sources(), model)
    assert len(model.calls) == 3 and result['detail_count'] == 8
    assert len(result['warnings']) == 1
    assert not any(claim['detail'] == 2 and claim['source_numbers'] == [1] for claim in result['claims'])
    assert sum(claim['detail'] == 2 for claim in result['claims']) == 2
    assert sum(claim['detail'] == 3 for claim in result['claims']) == 3


def test_structurally_invalid_optional_batch_leaks_no_points_but_later_batch_progresses():
    class InvalidIds(RichModel):
        def complete_json(self, *args, **kwargs):
            result = super().complete_json(*args, **kwargs)
            if len(self.calls) == 2:
                result['findings'][2]['id'] = result['findings'][0]['id']
            return result
    model = InvalidIds()
    result = synthesize_general_comparison(QUERY, _rich_sources(), model)
    assert len(model.calls) == 3 and result['detail_count'] == 6
    assert all(claim['detail'] != 2 for claim in result['claims'])
    assert sum(claim['detail'] == 3 for claim in result['claims']) == 3
    assert len(result['warnings']) == 1


def test_optional_provider_outage_stops_extra_calls():
    class Unavailable(RichModel):
        attempts = 0
        def complete_json(self, *args, **kwargs):
            self.attempts += 1
            if self.attempts == 2:
                raise TimeoutError('Model unavailable')
            return super().complete_json(*args, **kwargs)
    model = Unavailable()
    result = synthesize_general_comparison(QUERY, _rich_sources(), model)
    assert model.attempts == 2 and result['detail_count'] == 3
    assert len(result['warnings']) == 1


def test_optional_pool_reaches_later_retained_facts_after_opinion_is_removed():
    opinion = 'Many developers believe storage is all you need for reliable electrical service, although this is an opinion about product choice.'
    later = 'Storage controls monitor equipment condition and coordinate charging with grid signals to manage the intended operational service.'
    paragraphs = SOURCES[0]['text'].split('\n\n') + [opinion, later]
    source = dict(SOURCES[0], text='\n\n'.join(paragraphs), paragraphs=paragraphs)
    groups = source_groups(QUERY, [source], detail_limit=3)
    quotes = [group['evidence'][0]['quote'] for group in groups]
    assert len(quotes) == 3
    assert later in quotes and opinion not in quotes
    assert all(quote in source['text'] for quote in quotes)

def test_same_finding_from_different_publishers_is_not_a_same_source_duplicate():
    source=dict(SOURCES[0],number=1)
    other=dict(SOURCES[0],number=2,title='Independent publisher',url='https://other.example/report')
    class Matching:
        def complete_json(self,system,prompt,output_model,tokens):
            return {'findings':[{'id':group['id'],'text':'Variable weather changes renewable generation, so storage helps shift the timing of available electricity.'} for group in json.loads(prompt)['groups']]}
    result=synthesize_general_comparison(QUERY+' brief',[source,other],Matching())
    assert len(result['claims'])==2
    assert [claim['source_numbers'] for claim in result['claims']]==[[1],[2]]

def test_factual_detail_does_not_fill_with_unsupported_product_choice_opinions():
    source=dict(SOURCES[0],text=SOURCES[0]['text']+'\n\nSome practitioners insist that storage is all you need while others claim you will regret a different choice.')
    groups=source_groups(QUERY,[source],detail_limit=3)
    assert not any('regret' in group['evidence'][0]['quote'] for group in groups)
