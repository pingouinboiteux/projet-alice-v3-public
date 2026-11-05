from action_context import ActionContext


def test_closed_turns_are_paired_bounded_and_do_not_contain_generated_answers():
    context=ActionContext()
    for i in range(10): context.record(f'demande {i}','open','processed')
    messages=context.messages('SYSTEM')
    assert len(messages)==13 and messages[1]['content']=='demande 4'
    assert all(messages[i]['role']=='assistant' and '"pending_action": false' in messages[i]['content'] for i in range(2,13,2))
    context.record('annule','open','cancelled')
    assert 'cancelled' in context.messages('SYSTEM')[-1]['content']
    context.clear();assert len(context.messages('SYSTEM'))==1
