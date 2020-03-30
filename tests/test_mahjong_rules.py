import pytest
import random
from collections import Counter

from .context import mahjong_rules

from .util import TileRack, TileSampler

def random_four_pong():
    res = TileRack()
    tile_sampler = TileSampler()

    res += tile_sampler.pong(4)
    res += tile_sampler.pair()

    return res

def random_four_chow():
    res = TileRack()
    tile_sampler = TileSampler()

    res += tile_sampler.chow(4)
    res += tile_sampler.pair()

    return res

def random_two_pong_two_chow():
    res = TileRack()
    tile_sampler = TileSampler()

    res += tile_sampler.pong(2)
    res += tile_sampler.chow(2)
    res += tile_sampler.pair()

    return res

def tile_dict(t_suit, t_type):
    return { 'suit': t_suit, 'type': t_type }

def only_honor_two_pairs_loss():
    res = TileRack()

    res += [tile_dict('wind', 'north') for _ in range(3)]
    res += [tile_dict('wind', 'south') for _ in range(3)]
    res += [tile_dict('wind', 'east') for _ in range(3)]

    res += [tile_dict('dragon', 'red') for _ in range(2)]
    res += [tile_dict('dragon', 'white') for _ in range(2)]
    res += [tile_dict('character', 1)]

    return res

def only_honor_four_of_a_kind_loss():
    res = TileRack()

    res += [tile_dict('wind', 'north') for _ in range(4)]
    res += [tile_dict('wind', 'south') for _ in range(3)]
    res += [tile_dict('wind', 'east') for _ in range(3)]

    res += [tile_dict('dragon', 'red') for _ in range(4)]

    return res

def only_honor_win():
    res = TileRack()

    res += [tile_dict('wind', 'north') for _ in range(3)]
    res += [tile_dict('wind', 'south') for _ in range(3)]
    res += [tile_dict('wind', 'east') for _ in range(3)]

    res += [tile_dict('dragon', 'red') for _ in range(3)]
    res += [tile_dict('dragon', 'white') for _ in range(2)]

    return res

def honor_pair_bamboo_pong():
    res = TileRack()

    res += [tile_dict('wind', 'south') for _ in range(2)]

    nums = {i for i in range(1, 10)}
    for num in random.sample(nums, k=4):
        res += [tile_dict('bamboo', num) for _ in range(3)]

    return res

def ambiguous_pong_chow_1():
    res = TileRack()

    res += [tile_dict('character', 1)]
    res += [tile_dict('character', 2) for _ in range(2)]
    res += [tile_dict('character', 3) for _ in range(3)]
    res += [tile_dict('character', 4) for _ in range(2)]
    res += [tile_dict('character', 5)]
    res += [tile_dict('character', 6)]
    res += [tile_dict('character', 7)]
    res += [tile_dict('character', 8)]

    res += [tile_dict('dragon', 'white') for _ in range(2)]

    return res

def ambiguous_pong_chow_2():
    res = TileRack()

    res += [tile_dict('character', 1) for _ in range(3)]

    res += [tile_dict('character', 2)]
    res += [tile_dict('character', 3) for _ in range(2)]
    res += [tile_dict('character', 4) for _ in range(2)]
    res += [tile_dict('character', 5)]

    res += [tile_dict('character', 6)]
    res += [tile_dict('character', 7)]
    res += [tile_dict('character', 8)]

    res += [tile_dict('dragon', 'white') for _ in range(2)]

    return res

def ambiguous_pong_chow_3():
    res = TileRack()

    res += [tile_dict('character', 2) for _ in range(2)]

    res += [tile_dict('character', 3) for _ in range(2)]
    res += [tile_dict('character', 4) for _ in range(3)]
    res += [tile_dict('character', 5)]
    res += [tile_dict('character', 6)]

    res += [tile_dict('character', 7)]
    res += [tile_dict('character', 8)]
    res += [tile_dict('character', 9)]

    res += [tile_dict('dragon', 'white') for _ in range(2)]

    return res

def ambiguous_pong_chow_4():
    res = TileRack()

    res += [tile_dict('character', 2) for _ in range(1)]
    res += [tile_dict('character', 3) for _ in range(2)]
    res += [tile_dict('character', 4) for _ in range(2)]

    res += [tile_dict('character', 5) for _ in range(1)]

    res += [tile_dict('character', 7)]
    res += [tile_dict('character', 8) for _ in range(4)]
    res += [tile_dict('character', 9)]

    res += [tile_dict('dragon', 'white') for _ in range(2)]

    return res

def ambiguous_pong_chow_5():
    res = TileRack()

    res += [tile_dict('character', 2) for _ in range(4)]
    res += [tile_dict('character', 3) for _ in range(2)]
    res += [tile_dict('character', 4) for _ in range(2)]

    res += [tile_dict('character', 5) for _ in range(2)]
    res += [tile_dict('character', 6)]
    res += [tile_dict('character', 7)]

    res += [tile_dict('dragon', 'white') for _ in range(2)]

    return res

def pong_chow_numeric_pair():
    res = TileRack()

    res += [tile_dict('dragon', 'white') for _ in range(3)]

    res += [tile_dict('character', 2) for _ in range(2)]
    res += [tile_dict('character', 2)]
    res += [tile_dict('character', 3) for _ in range(2)]
    res += [tile_dict('character', 4) for _ in range(2)]

    res += [tile_dict('character', 5) for _ in range(2)]
    res += [tile_dict('character', 6)]
    res += [tile_dict('character', 7)]

    return res

def idk():
    res = TileRack()

    res += [tile_dict('character', 2) for _ in range(3)]
    res += [tile_dict('character', 3) for _ in range(3)]
    res += [tile_dict('character', 4) for _ in range(3)]

    res += [tile_dict('bamboo', 2) for _ in range(2)]

    res += [tile_dict('dots', 7) for _ in range(2)]

    return res

def single_pair_in_suit():
    res = TileRack()

    res += [tile_dict('character', 2) for _ in range(3)]
    res += [tile_dict('character', 3) for _ in range(3)]
    res += [tile_dict('character', 4) for _ in range(3)]

    res += [tile_dict('bamboo', 2) for _ in range(3)]

    res += [tile_dict('dots', 7) for _ in range(2)]

    return res

@pytest.fixture(autouse=True)
def run_around_tests():
    print('\n----- BEGIN -----')
    yield
    print('----- END -----')

@pytest.mark.parametrize('tiles, expected', [
    (only_honor_two_pairs_loss(), False),
    (only_honor_four_of_a_kind_loss(), False),
    (only_honor_win(), True),
    (honor_pair_bamboo_pong(), True),
    (ambiguous_pong_chow_1(), True),
    (ambiguous_pong_chow_2(), True),
    (ambiguous_pong_chow_3(), True),
    (ambiguous_pong_chow_4(), True),
    (ambiguous_pong_chow_5(), True),
    (pong_chow_numeric_pair(), True),
    (idk(), False),
    (single_pair_in_suit(), True),
    (random_four_pong(), True),
    (random_four_chow(), True),
    (random_two_pong_two_chow(), True),
], ids=[
    'all honor pongs and 1 numeric and two pairs, loss',
    'all honor 2 pongs and 2 four-of-a-kind, loss',
    'all honor 4 pongs 1 pair, win',
    '1 honor pair 4 bamboo pongs, win',
    'ambiguous_pong_chow_1, win',
    'ambiguous_pong_chow_2, win',
    'ambiguous_pong_chow_3, win',
    'ambiguous_pong_chow_4, win',
    'ambiguous_pong_chow_5, win',
    'honor pong, numeric pair and numeric chow mix, win',
    'numeric chow/pong/pair mix, win',
    'numeric chow/pong/pair mix, win',
    'random four pongs 1 pair, win',
    'random four chows 1 pair, win',
    'random two chows two pongs 1 pair, win',
    # need more loss scenarios
])
def test_can_meld_concealed_hand(tiles, expected):
    """This test only verifies 14-tile concealed hands. Kongs and revealed sets should be verified in a separate function."""
    actual = mahjong_rules.can_meld_concealed_hand(tiles)
    assert actual == expected

def numeric_pair_chow_1():
    res = TileRack()

    res += [tile_dict('character', 2) for _ in range(2)]
    res += [tile_dict('character', 3)]
    res += [tile_dict('character', 4)]
    res += [tile_dict('character', 5)]

    return res

@pytest.mark.parametrize('tiles, target_set_count, expected', [
    (numeric_pair_chow_1(), 1, True),
])
def test_can_meld_concealed_hand_with_melds(tiles, target_set_count, expected):
    """This test only verifies 14-tile concealed hands. Kongs and revealed sets should be verified in a separate function."""
    actual = mahjong_rules.can_meld_concealed_hand(tiles, target_set_count)
    assert actual == expected

def chow_case_1():
    res = TileRack()
    tile_sampler = TileSampler()

    chow = tile_sampler.chow()
    res += chow[:2]

    return res, chow[2]

@pytest.mark.parametrize('tiles, discarded_tile, expected', [
    (*chow_case_1(), True),
])
def test_can_meld_chow(tiles, discarded_tile, expected):
    actual = mahjong_rules.can_meld_chow(tiles, discarded_tile)
    assert actual == expected

def pong_case_1():
    res = []
    tile_sampler = TileSampler()

    pong = tile_sampler.pong()
    res += pong[:2]

    return res, pong[2]

@pytest.mark.parametrize('tiles, discarded_tile, expected', [
    (*pong_case_1(), True),
])
def test_can_meld_pung(tiles, discarded_tile, expected):
    actual = mahjong_rules.can_meld_pung(tiles, discarded_tile)
    assert actual == expected

'''
def mahjong_case_1():
    tiles = random_two_pong_two_chow()
    return tiles[:-1], tiles[-1]

def no_rank_case_1():
    tile_sampler = TileSampler()
    return tile_sampler.rand_tile(), *tile_sampler.rand_tile()

@pytest.mark.parametrize('tiles, discarded_tile, expected', [
    (*mahjong_case_1(), 3),
    (*pong_case_1(), 2),
    (*chow_case_1(), 1),
    (*no_rank_case_1(), 0),
])
def test_highest_rank(tiles, discarded_tile, expected):
    actual = mahjong_rules.highest_rank(tiles, discarded_tile)
    assert actual == expected
'''

def chow_two_subsets():
    res = []

    res += [tile_dict('character', 2) for _ in range(3)]
    res += [tile_dict('character', 3) for _ in range(3)]
    res += [tile_dict('character', 5) for _ in range(3)]

    return res, tile_dict('character', 4)

@pytest.mark.parametrize('tiles, discarded_tile, target_meld, expected', [
    (*chow_two_subsets(), 'CHOW', 2),
])
def test_get_valid_tile_sets(tiles, discarded_tile, target_meld, expected):
    valid_tile_sets = mahjong_rules.get_valid_tile_sets(tiles, discarded_tile, target_meld)

    assert len(valid_tile_sets) == expected

def honor_1():
    res = TileRack()

    res += [tile_dict('wind', 'south')]
    res += [tile_dict('wind', 'north')]
    res += [tile_dict('wind', 'south')]
    res += [tile_dict('dragon', 'white')]
    res += [tile_dict('wind', 'south')]
    res += [tile_dict('wind', 'north')]
    res += [tile_dict('dragon', 'white')]
    res += [tile_dict('wind', 'north')]

    return res

def honor_1_melded():
    res = []

    res.append([tile_dict('wind', 'north') for _ in range(3)])
    res.append([tile_dict('wind', 'south') for _ in range(3)])

    res.append([tile_dict('dragon', 'white') for _ in range(2)])

    return res

def num_chow_pung_1():
    res = TileRack()

    res += [tile_dict('character', 3) for _ in range(1)]
    res += [tile_dict('character', 4) for _ in range(1)]
    res += [tile_dict('character', 8) for _ in range(4)]
    res += [tile_dict('character', 7)]
    res += [tile_dict('character', 5) for _ in range(1)]
    res += [tile_dict('character', 9)]
    res += [tile_dict('dragon', 'white') for _ in range(2)]

    return res

def num_chow_pung_1_ans():
    res = []

    res.append([
        tile_dict('character', 3),
        tile_dict('character', 4),
        tile_dict('character', 5),
    ])

    res.append([
        tile_dict('character', 8),
        tile_dict('character', 8),
        tile_dict('character', 8),
    ])

    res.append([
        tile_dict('character', 7),
        tile_dict('character', 8),
        tile_dict('character', 9),
    ])

    res.append([tile_dict('dragon', 'white') for _ in range(2)])

    return res

def num_chow_pung_2():
    res = TileRack()

    res += [tile_dict('character', 5)]
    res += [tile_dict('character', 3)]
    res += [tile_dict('character', 4)]
    res += [tile_dict('character', 4)]
    res += [tile_dict('character', 5)]
    res += [tile_dict('character', 5)]
    res += [tile_dict('character', 3)]
    res += [tile_dict('character', 4)]
    res += [tile_dict('character', 3)]
    res += [tile_dict('dragon', 'white') for _ in range(2)]

    return res

@pytest.mark.parametrize('tiles, num_of_target_melds, expected', [
    (num_chow_pung_1(), 3, num_chow_pung_1_ans()),
    # (num_chow_pung_2(), 3, []), # FIXME: this has two answers technically
    (honor_1(), 2, honor_1_melded()) # 2 melds plus the eye
])
def test_get_melds(tiles, num_of_target_melds, expected):
    ans = mahjong_rules.get_melds(tiles, num_of_target_melds)

    counter = Counter()
    for meld in ans:
        counter[tuple([(t['suit'], t['type']) for t in meld])] += 1

    for meld in expected:
        counter[tuple([(t['suit'], t['type']) for t in meld])] -= 1

    assert not +counter

