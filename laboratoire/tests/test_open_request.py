from unittest.mock import Mock,patch
import pytest
from open_request import decide_open,targets
from action_policy import Action,Actions,SITES,parse

def session():
    value=Mock();value.ask.return_value=(' {"decision":"execute"}',0,{})
    return value

@pytest.mark.parametrize('text,url',[('ouvre le site secret','https://invented.org/'),
    ('ouvre youtube et google',SITES['youtube']),('ouvre https://example.org/',SITES['youtube']),
    ('Ouvre https://127.0.0.1/','https://127.0.0.1/'),('ouvre "youtube',SITES['youtube'])])
def test_ungrounded_or_ambiguous_destination_never_calls_model(text,url):
    model=session();assert decide_open(model,text,url)=='clarify';model.ask.assert_not_called()

@pytest.mark.parametrize('text',['"ouvre youtube"',"'ouvre youtube'",'N ouvre pas youtube' .replace('N ','N\''),'Ne pas ouvrir YouTube'])
def test_quotes_and_direct_negation_do_not_execute(text):
    model=session();assert decide_open(model,text,SITES['youtube'])!='execute';model.ask.assert_not_called()

def test_site_can_be_quoted_as_argument_and_external_source_denied():
    model=session();assert decide_open(model,'Peux-tu ouvrir "YouTube" ?',SITES['youtube'])=='execute'
    model.reset_mock();assert decide_open(model,'ouvre youtube',SITES['youtube'],'twitch')=='clarify'
    model.ask.assert_not_called()

def test_url_containing_site_name_is_not_a_second_destination():
    assert targets('Ouvre https://example.org/youtube')=={'https://example.org/youtube'}
    assert targets('Ouvre google.fr')==set()
    assert targets('Ouvre Wikipédia')=={SITES['wikipedia']}

def test_sentence_period_and_quoted_literal_url_are_distinguished():
    assert parse('Ouvre https://example.org/guide.').value=='https://example.org/guide'
    assert targets('Ouvre https://example.org/guide.')=={'https://example.org/guide'}
    assert targets('Ouvre «https://example.org/guide.»')=={'https://example.org/guide.'}

@pytest.mark.parametrize('text',['Pour tester, la phrase serait : peux-tu ouvrir YouTube ?',
    'Je lis a voix haute : ouvre Twitch.','Ne fais rien : je dis seulement ouvre Google.'])
def test_reported_order_never_reaches_model_even_if_router_suggests_open(text):
    model=session();url=next(iter(targets(text)))
    assert decide_open(model,text,url)!='execute';model.ask.assert_not_called()

@pytest.mark.parametrize('raw',['{}',' {"decision":"execute","decision":"discuss"}',
    '{"decision":"execute","extra":1}','not json'])
def test_bad_classification_never_executes(raw):
    model=session();model.ask.return_value=(raw,0,{})
    assert decide_open(model,'ouvre youtube',SITES['youtube'])=='clarify'

@pytest.mark.parametrize('kind', ['open', 'search'])
@pytest.mark.parametrize('automatic', [False, True])
def test_personal_browser_refused_even_if_previously_approved(kind, automatic):
    browser=Mock();confirm=Mock(return_value=True)
    actions=Actions(Mock(),browser,confirm,Mock())
    with patch('web_reader.public_addresses') as dns:
        reply=actions.execute(Action(kind,SITES['youtube']),automatic_open=automatic)
    assert 'navigateur personnel desactivee' in reply
    dns.assert_not_called();confirm.assert_not_called();browser.assert_not_called()
