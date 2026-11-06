"""Synthetic phrasing/provenance checks, without model or personal storage."""
import pytest
from observer_note_intent import _CREATE, validate_intent, payload_for_intent
from note_operations import operation_kind, validate_operation


@pytest.mark.parametrize('text', [
    'Crée une liste Courses avec le texte lait, pain et pommes',
    'Peu tu me créer une liste intitulée Courses avec le texte Du pain',
    "Alice, s'il te plaît, tu peux me créer une note titre Projet texte Finir demain",
    "J'aimerais que tu crées une liste titre Jardin texte Arroser demain",
    'Fais-moi une liste titre Stream texte Vérifier le micro',
    'Peux-tu m écrire une note titre Test texte Bonjour',
    "Est-ce que tu peux m'écrire une liste titre Test texte Bonjour",
    'Tu veux bien créer une liste titre Recette texte Farine et eau',
])
def test_direct_creation(text):
    assert _CREATE.search(text)


@pytest.mark.parametrize('text,kind', [
    ('Peu tu me lire la liste Courses', 'read'),
    ("Alice, s'il te plaît, lis ma liste Jardin", 'read'),
    ("Est-ce que tu peux m'afficher la note Projet", 'read'),
    ('Tu veux bien me montrer mes notes', 'list'),
    ('Liste mes listes', 'list'),
    ('Peux-tu me remplacer le texte de la liste Courses par Du pain', 'update'),
    ("J'aimerais que tu modifies ma liste Courses avec le texte Du lait", 'update'),
])
def test_direct_operation(text,kind):
    assert operation_kind(text) == kind


@pytest.mark.parametrize('text', [
    'Si je dis crée une liste Courses, que fais-tu ?',
    'Par exemple, crée une liste Courses avec Du pain',
    'Il a dit "Crée une liste Courses"',
    '"Peux-tu créer une liste Courses"',
    'Ne crée pas une liste Courses',
    'Comment créer une liste Courses ?',
    'Je lis à voix haute : lis la liste Courses',
    'Pour tester, la phrase serait : modifie ma liste Courses',
    'Si tu pouvais lister mes notes, ce serait pratique',
    '"Liste mes listes"',
    'Ne lis pas ma liste Courses',
    'Lis la liste "Courses',
])
def test_reported_or_nonrequests_are_not_structural_commands(text):
    assert not _CREATE.search(text)
    assert operation_kind(text) is None


def cite(text):
    return {'turn': 0, 'quote': text}


def test_list_values_preserved_without_invented_formatting():
    text='Crée une liste titre Courses texte "lait,  pain et pommes"'
    raw={'intent':'create_note', 'title':cite('Courses'), 'body':cite('lait,  pain et pommes')}
    result=validate_intent(raw,[text])
    assert result['status']=='ready'
    assert result['target']=={'title':'Courses','body':'lait,  pain et pommes'}
    raw['body']=cite('- lait\n- pain\n- pommes')
    assert validate_intent(raw,[text])['status']=='clarify'
    assert 'texte simple' in payload_for_intent([text])['messages'][0]['content']


def test_list_update_still_requires_full_body_not_partial_append():
    text='Modifie la liste "Courses" avec le texte "Du lait", ajoute seulement du beurre'
    raw={'intent':'update','title':cite('Courses'),'body':cite('Du lait')}
    assert validate_operation(raw,[text],'update')['status']=='clarify'


def test_quoted_stop_in_list_body_is_data():
    text='Crée une liste titre Dialogue texte "stop et annule"'
    raw={'intent':'create_note','title':cite('Dialogue'),'body':cite('stop et annule')}
    assert validate_intent(raw,[text])['status']=='ready'
