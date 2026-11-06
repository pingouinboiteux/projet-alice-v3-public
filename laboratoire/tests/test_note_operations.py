"""Fictional local quotations only: no model, notes or memory access."""
import json
from pathlib import Path
import sys
from unittest.mock import Mock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from note_operations import operation_kind,validate_operation,interpret_operation

def cite(text,turn=0):return {'turn':turn,'quote':text}

@pytest.mark.parametrize('text,kind',[
    ('Lis la note "Courses"','read'),('Alice peux-tu lire ma note "Jardin" ?','read'),
    ('Affiche-moi la note "Projet"','read'),('Liste mes notes','list'),
    ('Montre toutes les notes','list'),('Modifie la note "Courses" avec le texte "Du lait"','update'),
    ('Remplace le texte de la note "Courses" par "Du pain"','update')])
def test_explicit_operation(text,kind):assert operation_kind(text)==kind

@pytest.mark.parametrize('text',[
    'Ne lis pas ma note','Comment modifier la note Courses ?',
    'Il a dit "Lis la note Courses"','"Modifie la note Courses"',
    'Si je modifie la note Courses, que se passe-t-il ?',
    'Bonjour','Lis la note "guillemet incomplet'])
def test_no_implicit_operation(text):assert operation_kind(text) is None

def test_exact_read_and_list():
    assert validate_operation({'intent':'read','title':cite('Courses')},['Lis la note "Courses"'],'read')['title']=='Courses'
    assert validate_operation({'intent':'list'},['Liste mes notes'],'list')['status']=='ready'

def test_exact_update_preserves_spaces_and_quotes():
    text='Modifie la note "Courses" avec le texte « Garder  deux espaces et dire stop »'
    result=validate_operation({'intent':'update','title':cite('Courses'),'body':cite('Garder  deux espaces et dire stop')},[text],'update')
    assert result['status']=='ready' and '  ' in result['body']

def test_recent_body_correction_keeps_title_and_rejects_old_body():
    turns=['Modifie la note "Courses" avec le texte "Du lait"',
           'Finalement remplace le texte par "Du pain"']
    raw={'intent':'update','title':cite('Courses'),'body':cite('Du lait')}
    assert validate_operation(raw,turns,'update')['status']=='clarify'
    raw['body']=cite('Du pain',1)
    assert validate_operation(raw,turns,'update')['status']=='ready'

@pytest.mark.parametrize('suffix',['renomme la note','supprime la note','ajoute seulement du beurre'])
def test_unsupported_mutations_rejected(suffix):
    text='Modifie la note "Courses" avec le texte "Du lait", '+suffix
    raw={'intent':'update','title':cite('Courses'),'body':cite('Du lait')}
    assert validate_operation(raw,[text],'update')['status']=='clarify'

def test_invented_and_ambiguous_citations_fail_closed():
    raw={'intent':'read','title':cite('Secret')}
    assert validate_operation(raw,['Lis la note "Courses"'],'read')['status']=='clarify'
    raw['title']=cite('Courses')
    assert validate_operation(raw,['Lis la note "Courses", oui Courses'],'read')['status']=='clarify'

def test_cancel_cannot_be_revived_by_yes():
    raw={'intent':'read','title':cite('Courses')}
    assert validate_operation(raw,['Lis la note "Courses"','Annule'],'read')['status']=='cancel'
    assert validate_operation(raw,['Lis la note "Courses"','Annule','Oui'],'read')['status']=='clarify'

def test_new_operation_cannot_reuse_old_request():
    assert validate_operation({'intent':'read','title':cite('Courses')},
        ['Lis la note "Courses"','Liste mes notes'],'read')['status']=='clarify'

@pytest.mark.parametrize('title',['$:/system','x'*81,'titre\x00'])
def test_unsupported_title(title):
    assert validate_operation({'intent':'read','title':cite(title)},['Lis la note "'+title+'"'],'read')['status']=='clarify'

@pytest.mark.parametrize('source',['twitch','discord','system',None])
def test_external_source_never_calls_model(source):
    session=Mock()
    assert interpret_operation(session,['Liste mes notes'],'list',source)['status']=='clarify'
    session.ask.assert_not_called()

def test_model_schema_and_duplicate_keys_rejected():
    session=Mock()
    session.ask.return_value=('{"intent":"list","intent":"read"}',0,{})
    assert interpret_operation(session,['Liste mes notes'],'list')['status']=='clarify'
    session.ask.return_value=(json.dumps({'intent':'read','title':cite('Courses')}),0,{})
    assert interpret_operation(session,['Lis la note "Courses"'],'read','voice')['status']=='ready'

@pytest.mark.parametrize('turns',[
    ['Lis la note "Courses'],['Il a dit "Lis la note Courses"'],
    ['Lis la note "Courses"','Annule','Oui']])
def test_invalid_sources_rejected_before_model(turns):
    session=Mock()
    assert interpret_operation(session,turns,'read')['status']=='clarify'
    session.ask.assert_not_called()
