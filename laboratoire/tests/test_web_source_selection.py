"""Comparison must not turn different contexts into factual agreement/conflict."""
import json
from unittest.mock import Mock

import pytest
from web_source_selection import compare_evidence


@pytest.mark.parametrize('relation', ['consistent', 'conflicting', 'inconclusive'])
@pytest.mark.parametrize('same_conditions', [True, False])
def test_context_gate(relation, same_conditions):
    session = Mock()
    session.ask.return_value = (json.dumps({
        'relation': relation, 'same_conditions': same_conditions}), '', {})
    assert compare_evidence(session, 'validation_question', []) == (
        relation if same_conditions else 'inconclusive')


@pytest.mark.parametrize('proposal', [
    {'relation': 'consistent'},
    {'relation': 'conflicting', 'same_conditions': 'false'},
    {'relation': 'consistent', 'same_conditions': 1},
    {'relation': 'consistent', 'same_conditions': None},
    {'relation': 'unknown', 'same_conditions': True},
    {'relation': 'consistent', 'same_conditions': True, 'extra': True},
    [],
])
def test_malformed_context_is_rejected(proposal):
    session = Mock()
    session.ask.return_value = (json.dumps(proposal), '', {})
    with pytest.raises(ValueError, match='invalid_source_comparison'):
        compare_evidence(session, 'validation_question', [])
