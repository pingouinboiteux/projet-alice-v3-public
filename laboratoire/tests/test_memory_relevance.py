import json
from unittest.mock import Mock
import pytest
from memory_relevance import select_relevant


@pytest.mark.parametrize('ids', [[True], [-1], [8], [0,0]])
def test_model_cannot_reference_an_unprovided_source(ids):
    session=Mock()
    session.ask.return_value=(json.dumps({'ids':ids}),0,{})
    with pytest.raises(ValueError):
        select_relevant(session,'Quel est mon animal ?',['Mon chat se nomme Pixel.'])


def test_abstention_produces_no_memory():
    session=Mock()
    session.ask.return_value=('{"ids":[]}',0,{})
    assert select_relevant(session,'Quel est mon domicile ?',['Je travaille a Dijon.'])==[]
