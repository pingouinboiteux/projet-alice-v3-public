import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from web_passages import select_passages, MAX_BYTES


def joined(result):
    return '\n'.join(p['text'] for p in result['passages'])


def test_information_after_first_ten_thousand_characters_is_selected():
    text=('Un paragraphe general sans rapport avec la demande. ' * 360
          + 'Les horaires du planetarium sont de 09:00 a 18:00 chaque mardi. '
          + 'Autres renseignements sans rapport. ' * 400)
    result=select_passages(text,'Quels sont les horaires du planetarium ?',1500)
    assert '09:00 a 18:00' in joined(result)
    assert result['passages'][0]['start']>10000
    assert result['truncated']


def test_multiple_requested_fields_are_selected_across_long_document():
    text=('Les horaires sont disponibles sur place. ' * 300 +
          'Adresse du musee : 14 rue des Tilleuls. ' +
          'Divers details sur les collections. ' * 300 +
          'Tarif du musee : 12 euros. ' + 'Texte secondaire. '*100)
    result=select_passages(text,'Adresse et tarif du musee ?',2600)
    assert '14 rue des Tilleuls' in joined(result)
    assert '12 euros' in joined(result)


def test_accents_case_and_original_offsets_are_preserved():
    text='Préambule. '*1500+'ÉQUIPEMENTS disponibles : fauteuil roulant. '+'Fin. '*3000
    result=select_passages(text,'Quels equipements sont disponibles ?',1200)
    assert 'ÉQUIPEMENTS disponibles : fauteuil roulant.' in joined(result)
    previous=0
    for passage in result['passages']:
        assert passage['start']>=previous
        assert passage['text']==text[passage['start']:passage['end']]
        previous=passage['end']
    assert result['selected_chars']==sum(len(p['text']) for p in result['passages'])<=1200


def test_url_words_do_not_dominate_question_matching():
    text='Publicite remise promotion soldes. '*500+'La fermeture annuelle commence le 12 juin. '
    result=select_passages(text,'Lis https://example.org/publicite/remise/promotion/soldes : quelle fermeture annuelle ?',1100)
    assert '12 juin' in joined(result)


def test_absence_does_not_claim_that_the_requested_fact_does_not_exist():
    text='Aucune relation avec la question posee. '*500
    result=select_passages(text,'Combien de satellites ?',1700)
    assert result['truncated'] and result['passages']
    assert 'answer' not in result and 'found' not in result


def test_small_page_is_returned_entirely_and_empty_page_is_explicit():
    text='Un texte court avec accents éè et espaces  doubles.'
    assert select_passages(text,'quoi')['passages']==[
        {'id':'p1','start':0,'end':len(text),'text':text}]
    assert not select_passages(text,'quoi')['truncated']
    assert select_passages('','quoi')==dict(passages=[],total_chars=0,selected_chars=0,truncated=False)


@pytest.mark.parametrize('budget',[0,255,10001,True,'1000',1.5])
def test_invalid_budgets_rejected(budget):
    with pytest.raises(ValueError):select_passages('text','question',budget)


def test_input_limits_are_enforced_before_selection():
    with pytest.raises(ValueError):select_passages('é'*(MAX_BYTES//2+1),'question')
    with pytest.raises(ValueError):select_passages('x'*(MAX_BYTES+1),'question')
    with pytest.raises(ValueError):select_passages('text','x'*2001)
    with pytest.raises(ValueError):select_passages(None,'question')


def test_overlap_is_merged_and_budget_is_exact_for_varied_sizes():
    text=('Un texte de test contigu avec prix 17 euros et heures 08:00. '*800)
    for budget in (256,1000,1500,10000):
        result=select_passages(text,'prix heures',budget)
        assert result['selected_chars']<=budget
        for a,b in zip(result['passages'],result['passages'][1:]):
            assert a['end']<b['start']
        for p in result['passages']:
            assert p['text']==text[p['start']:p['end']]
