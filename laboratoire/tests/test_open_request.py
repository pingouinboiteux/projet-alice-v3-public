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

def test_only_approved_open_skips_confirmation_and_requires_public_dns():
    browser=Mock(return_value=True);confirm=Mock(return_value=False)
    actions=Actions(Mock(),browser,confirm,Mock())
    with patch('web_reader.public_addresses',return_value=['8.8.8.8']) as dns:
        actions.execute(Action('open',SITES['youtube']),automatic_open=True)
    dns.assert_called_once_with('www.youtube.com');confirm.assert_not_called();browser.assert_called_once()
    browser.reset_mock()
    actions.execute(Action('search',SITES['google']),automatic_open=True)
    confirm.assert_called_once();browser.assert_not_called()

def test_private_dns_blocks_automatic_open():
    browser=Mock();actions=Actions(Mock(),browser,Mock(),Mock())
    with patch('web_reader.public_addresses',side_effect=ValueError('private')):
        with pytest.raises(ValueError):actions.execute(Action('open','https://example.org/'),automatic_open=True)
    browser.assert_not_called()

def test_new_input_during_dns_prevents_browser_dispatch():
    browser=Mock();confirm=Mock();events=[]
    actions=Actions(Mock(),browser,confirm,Mock())
    def resolve(host):events.append('dns');return ['8.8.8.8']
    def cancelled():events.append('cancel_check');return True
    with patch('web_reader.public_addresses',side_effect=resolve):
        assert actions.execute(Action('open',SITES['youtube']),automatic_open=True,
            cancelled=cancelled)=='Ouverture annulee.'
    assert events==['dns','cancel_check'];browser.assert_not_called();confirm.assert_not_called()
