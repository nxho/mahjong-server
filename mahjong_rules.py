import copy
from collections import defaultdict, Counter

from Constants import HONOR_SUITS, NUMERIC_SUITS, SETS_NEEDED_TO_WIN 

def get_tile_for_kong(tiles):
    tile_counter = Counter()

    for t in tiles:
        tile_counter[(t['suit'], t['type'])] += 1

    for k, v in tile_counter.items():
        if v == 4:
            return { 'suit': k[0], 'type': k[1] }

    return None

def get_valid_tile_sets(tiles, discarded_tile, target_meld):
    if target_meld == 'PUNG':
        return [[{
            'suit': discarded_tile['suit'],
            'type': discarded_tile['type'],
        } for _ in range(2)]]
    elif target_meld == 'KONG':
        return [[{
            'suit': discarded_tile['suit'],
            'type': discarded_tile['type'],
        } for _ in range(3)]]
    elif target_meld == 'CHOW':
        return [[{'suit': tup[0], 'type': tup[1]} for tup in chow_subset] for chow_subset in get_valid_chow_subsets(tiles, discarded_tile)]

    return None

def check_tiles_against_meld(tiles, discarded_tile, target_meld, table_sets=[], is_chow_allowed=True):
    if target_meld == 'WIN':
        tiles_with_discarded_tile = tiles + [discarded_tile]
        target_set_count = SETS_NEEDED_TO_WIN - len(table_sets)
        if can_meld_concealed_hand(tiles_with_discarded_tile, target_set_count):
            return 3
    elif target_meld == 'PUNG':
        if can_meld_pung(tiles, discarded_tile):
            return 2
    elif target_meld == 'KONG':
        if can_meld_kong(tiles, discarded_tile):
            return 2
    elif target_meld == 'CHOW':
        if is_chow_allowed and can_meld_chow(tiles, discarded_tile):
            return 1
    return 0

def can_meld_kong(tiles, discarded_tile):
    return len([t for t in tiles if t == discarded_tile]) >= 3

def can_meld_pung(tiles, discarded_tile):
    return len([t for t in tiles if t == discarded_tile]) >= 2

def can_meld_chow(tiles, discarded_tile):
    dt_suit, dt_type = discarded_tile['suit'], discarded_tile['type']
    if dt_suit not in NUMERIC_SUITS:
        return False

    chow_subsets = get_valid_chow_subsets(tiles, discarded_tile)
    return len(chow_subsets) > 0

def get_valid_chow_subsets(tiles, discarded_tile):
    # Convert from list of dicts to set of tuples
    tiles_set = {(t['suit'], t['type']) for t in tiles if t['suit'] in NUMERIC_SUITS}

    # Generate all tile "pairs" that would result in a chow with the discarded tile
    return [tiles_subset for tiles_subset in get_all_chow_subsets(discarded_tile) if tiles_subset <= tiles_set]

def get_all_chow_subsets(tile):
    for offsets in [(-2, -1), (-1, 1), (1, 2)]:
        res = {(tile['suit'], tile['type'] + o) for o in offsets}
        if all([1 <= r[1] <= 9 for r in res]):
            yield res

def can_meld_concealed_hand(tiles, target_set_count=4):
    """Returns True if the given tiles can make the desired number of melds. This ignores special mahjong hands."""
    set_count = 0
    pair = 0

    # Create normal counter objects for both honor and numeric tiles
    honor_counter = Counter()
    numeric_counter = Counter()

    for t in tiles:
        t_suit, t_type = t['suit'], t['type']
        if t_suit in HONOR_SUITS:
            honor_counter[(t_suit, t_type)] += 1
        else:
            numeric_counter[(t_suit, t_type)] += 1

    print('preprocessing - honor_counter:', honor_counter)

    # Try to make melds from honor tiles
    for h_key, h_count in honor_counter.items():
        if h_count == 3:
            set_count += 1
        elif h_count == 2 and not pair:
            pair += 1
        else:
            print(f'Hand not eligible for win, found count={h_count} for honor tile={h_key}')
            return False

    print('set_count post-honor:', set_count)
    print('pair post-honor:', pair)

    print('preprocessing - numeric_counter:', numeric_counter)

    # Prepare inputs:
    #   * Split Counter dicts into respective suits
    #   * Gather possible pair keys for each suit

    # Split counter objects by suit, we're looking for both pongs and chows
    counter_by_suit = defaultdict(Counter)
    possible_pairs_by_suit = defaultdict(list)
    for k, n_count in numeric_counter.items():
        n_suit, n_type = k
        counter_by_suit[n_suit][n_type] = n_count
        if n_count >= 2:
            # Each tile with a count >= is a pair candidate
            possible_pairs_by_suit[n_suit].append(n_type)

    print('preprocessing - counter_by_suit:', counter_by_suit)
    print('preprocessing - possible_pairs_by_suit:', possible_pairs_by_suit)

    for suit_key in NUMERIC_SUITS:
        # Skip empty counters
        if not counter_by_suit[suit_key]:
            continue

        current_suit_counter = counter_by_suit[suit_key]
        possible_pairs = possible_pairs_by_suit[suit_key]

        print(f'now processing {suit_key} tiles', current_suit_counter, possible_pairs)

        # Try resolving melds without picking a pair
        potential_count = resolve_melds(current_suit_counter)
        if potential_count:
            set_count += potential_count
            continue

        # If a pair has not been chosen thus far, for each possible pair, resolve chows/pongs
        if not pair:
            for p_key in possible_pairs:
                # If choosing current possible pair, results in empty counter, resolve pair and break
                if is_pair(current_suit_counter, p_key):
                    pair += 1
                    break
                potential_count = resolve_melds(current_suit_counter, p_key)
                if potential_count:
                    set_count += potential_count
                    pair += 1
                    break

    return pair == 1 and set_count == target_set_count

def is_pair(counter, pair_key):
    return pair_key in counter and counter[pair_key] == 2 and len(counter) == 1

def resolve_melds(counter, pair_key=None):
    print(f'resolve_melds: counter={counter} pair_key={pair_key}')
    counter_copy = copy.deepcopy(counter)
    if pair_key is not None:
        counter_copy[pair_key] -= 2
        # TODO: change all == 0 to <= 0?
        if counter_copy[pair_key] <= 0:
            del counter_copy[pair_key]

    chow_count = resolve_chows(counter_copy)
    counter_copy = +counter_copy # clear zero/neg counts

    print(f'post-resolve_chows chow_count:{chow_count}, counter_copy:{counter_copy}')

    # Short-circuit, if counter is empty after resolving chows
    if not counter_copy:
        return chow_count

    pong_count = resolve_pongs(counter_copy)
    counter_copy = +counter_copy # clear zero/neg counts

    print(f'post-resolve_pongs pong_count:{pong_count}, counter_copy:{counter_copy}')

    # We still have items in counter after trying to create both chows and pongs, return 0 for failure
    if counter_copy:
        return 0

    return chow_count + pong_count

def resolve_chows(counter):
    set_count = 0
    i = 1
    while i <= 7 and counter:
        if i in counter and counter[i] in {1, 2, 4}:
            if all([j in counter for j in range(i, i + 3)]):
                set_count += 1
                for j in range(i, i + 3):
                    counter[j] -= 1
                    if counter[j] <= 0:
                        del counter[j]
            else:
                return 0
        else:
            i += 1
    return set_count

def resolve_pongs(counter):
    set_count = 0
    for n_tile_key, n_count in counter.items():
        if n_count == 3:
            set_count += 1
            counter[n_tile_key] -= 3
        else:
            return 0
    return set_count

