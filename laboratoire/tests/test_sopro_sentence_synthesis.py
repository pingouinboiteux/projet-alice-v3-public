from unittest.mock import Mock

from sopro_sentence_synthesis import sentence_audio


def test_first_sentence_is_available_before_next_synthesis_without_rewriting():
    model = Mock()
    model.synthesize.side_effect = ['pcm1', 'pcm2']
    reference = object()
    text = 'Une idée peut changer une discussion. Mais il faut aussi la vérifier.'
    iterator = sentence_audio(model, text, reference)
    assert next(iterator) == 'pcm1'
    model.synthesize.assert_called_once_with('Une idée peut changer une discussion.', ref=reference, lang='fr')
    assert list(iterator) == ['pcm2']
    assert ' '.join(c.args[0] for c in model.synthesize.call_args_list) == text
