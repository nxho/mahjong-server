import pytest
from unittest.mock import MagicMock
from .context import server, mahjong_rules

# FIXME: this test is pretty useless, fix this

def mock_check_tiles_against_meld(ranks=[0, 0, 0]):
    return MagicMock(side_effect=ranks)

# By default, we will make p0 the current player, p1-3 are the players claiming discards
def players_for_test(rel_pos=[1, 2, 3]):
    return [{
        'pid': f'p{i + 1}',
        'rel_pos': rel_pos[i],
        'tiles': [],
        'declared_meld': 'WIN',
        'revealed_melds_count': 1,
    } for i in range(3)]

@pytest.mark.parametrize('players, mock_check_tiles_against_meld, expected', [
    (players_for_test([1, 2, 3]), mock_check_tiles_against_meld([3, 2, 3]), 'p1'),
    (players_for_test([1, 2, 3]), mock_check_tiles_against_meld([1, 2, 0]), 'p2'),
    (players_for_test([1, 2, 3]), mock_check_tiles_against_meld([1, 0, 0]), 'p1'),
    (players_for_test([3, 1, 2]), mock_check_tiles_against_meld([0, 3, 2]), 'p2'),
    (players_for_test([3, 1, 2]), mock_check_tiles_against_meld([0, 0, 2]), 'p3'),
    (players_for_test([3, 1, 2]), mock_check_tiles_against_meld([0, 1, 2]), 'p3'),
    (players_for_test([3, 1, 2]), mock_check_tiles_against_meld([0, 0, 0]), None),
])
def test_get_next_player_uuid(players, mock_check_tiles_against_meld, expected):
    mahjong_rules.check_tiles_against_meld = mock_check_tiles_against_meld
    actual = server.get_next_player_uuid(players, {})
    assert actual[0] == expected

