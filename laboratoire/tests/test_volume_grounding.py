import pytest
from volume_grounding import explicit_volume_values,supports_volume

@pytest.mark.parametrize('text,value',[
    ('Regle le volume a 35 %',35),('Passe a trente-cinq pour cent',35),
    ('Mets a zéro',0),('Mets a cent pour cent',100),
    ('Soixante et onze pour cent',71),('quatre-vingt-dix-neuf pour cent',99),
    ('quatre-vingts pour cent',80),('vingt et un pour cent',21),
    ('nonante-deux pour cent',92),('au maximum',100),('a la moitie',50),
])
def test_explicit_levels(text,value):
    assert explicit_volume_values(text)=={value}

@pytest.mark.parametrize('text,value',[
    ('Remets le son du PC maintenant',100),('Baisse un peu le son',0),
    ('trente pour cent',100),('quatre-vingt-dix pour cent',20),
    ('quatre-vingt-dix pour cent',4),('1000',100),('2.5',5),('-10',10),
    ('Je souhaite un son plus clair',1),('trente pour cent',True),
    ('cent cinquante pour cent',100),('cent mille',100),('deux virgule cinq',5),
    ('moins dix',10),('1 000 pour cent',0),('1 000 pour cent',1),
])
def test_invented_or_partial_values_are_rejected(text,value):
    assert not supports_volume(text,value)
