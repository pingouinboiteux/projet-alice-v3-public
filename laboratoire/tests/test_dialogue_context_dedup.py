from dialogue_context_dedup import compact_recent_archives

def user(text):return {'role':'user','content':text}
def assistant(text):return {'role':'assistant','content':text}

def test_whole_exchange_is_present_once_without_mutating_either_input():
    messages=[user('Pour ce soir seulement.'),assistant('Quel plat ?'),user('Une salade.')]
    archive={'id':'validation_one','date':'2025-01-01','messages':messages}
    history=messages+[assistant('D accord.')]
    result=compact_recent_archives([archive],history,'validation_one')
    assert result==[{'id':'validation_one','date':'2025-01-01',
        'echange_deja_present_dans_historique_recent':{'premier_message':1,'nombre_messages':3}}]
    assert archive['messages']==messages and len(history)==4

def test_partial_overlap_retains_scope_and_missing_context():
    messages=[user('Uniquement pour dimanche.'),assistant('Que veux-tu ?'),user('Du calme.')]
    archive={'id':'validation_one','messages':messages}
    assert compact_recent_archives([archive],messages[1:],'validation_one')==[archive]

def test_same_words_from_other_speaker_or_different_order_are_not_duplicates():
    archive={'id':'validation_one','messages':[user('Oui'),assistant('Je note.')]}
    assert compact_recent_archives([archive],[assistant('Oui'),user('Je note.')],'validation_one')==[archive]
    assert compact_recent_archives([archive],list(reversed(archive['messages'])),'validation_one')==[archive]

def test_only_matching_archive_is_removed():
    a={'id':'validation_a','messages':[user('A'),assistant('B')]}
    b={'id':'validation_b','messages':[user('C')]}
    result=compact_recent_archives([a,b],[user('D'),*a['messages']],'validation_a')
    assert result[0]['echange_deja_present_dans_historique_recent']['premier_message']==2
    assert result[1]==b

def test_other_occurrences_with_identical_words_are_kept_in_full():
    messages=[user('Demain je pars.')]
    old={'id':'validation_old','date':'2025-01-01','messages':messages}
    assert compact_recent_archives([old],messages,'validation_current')==[old]
    assert compact_recent_archives([old],messages,None)==[old]
