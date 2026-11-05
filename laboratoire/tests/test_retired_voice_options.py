"""Retired voice recipes must fail before any worker is started."""
import pytest
from validation_sopro_resonance import arguments


@pytest.mark.parametrize('old',[
    '--production','--acoustic-trace','--semantic-control','--solver-check',
    '--reference-check','--reproduce-d','--candidate-d','--rng-trace',
])
def test_retired_recipe_cannot_be_selected(old):
    with pytest.raises(SystemExit):arguments([old])
    with pytest.raises(SystemExit):arguments(['--original-options',old])


def test_native_reference_is_explicit_and_fps_exception_is_not_implicit():
    with pytest.raises(SystemExit):arguments([])
    assert not arguments(['--original-options']).allow_game_no_fps
    assert arguments(['--original-options','--allow-game-no-fps']).allow_game_no_fps
