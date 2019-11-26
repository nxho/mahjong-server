import pytest
from unittest.mock import MagicMock
from context import server, mahjong_rules

# FIXME: highest_rank() no longer exists, fix this test to use new function

def mock_rank(ranks=[0, 0, 0]):
    return MagicMock(side_effect=ranks)

# By default, we will make p0 the current player, p1-3 are the players claiming discards
def players_for_test(rel_pos=[1, 2, 3]):
    return [{ 'pid': f'p{i + 1}', 'rel_pos': rel_pos[i], 'tiles': [] } for i in range(3)]

@pytest.mark.parametrize('players, mock_rank, expected', [
    (players_for_test([1, 2, 3]), mock_rank([3, 2, 3]), 'p1'),
    (players_for_test([1, 2, 3]), mock_rank([1, 2, 0]), 'p2'),
    (players_for_test([1, 2, 3]), mock_rank([1, 0, 0]), 'p1'),
    (players_for_test([3, 1, 2]), mock_rank([0, 3, 2]), 'p2'),
    (players_for_test([3, 1, 2]), mock_rank([0, 0, 2]), 'p3'),
    (players_for_test([3, 1, 2]), mock_rank([0, 1, 2]), 'p3'),
    (players_for_test([3, 1, 2]), mock_rank([0, 0, 0]), None),
])
def test_get_next_player_uuid(players, mock_rank, expected):
    mahjong_rules.highest_rank = mock_rank
    actual = server.get_next_player_uuid(players, {})
    assert actual == expected

