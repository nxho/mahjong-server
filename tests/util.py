import random

from collections import Counter

from tests.context import honor, numeric

class TileRack(list):
    """Better string representation of list of tiles"""
    def __repr__(self):
        tiles = {}
        for t in self:
            tile_short = f"{t['suit'][:4]}_{t['type']}"
            if tile_short not in tiles:
                tiles[tile_short] = 0
            tiles[tile_short] += 1

        return str([f'{v} {k}' for k, v in tiles.items()])

class TileSampler():
    """Allocate counter representing 136 tiles in a game, use counter to create valid pongs/chows/pairs"""
    def __init__(self):
        self.samples = Counter()
        for tile_set in [*honor, *numeric]:
            t_suit, t_count = tile_set['suit'], tile_set['count']
            for t_type in tile_set['types']:
                self.samples[(t_suit, t_type)] = t_count

    def pong(self, n=1):
        res = []
        for tile_key in random.sample([key for key, count in self.samples.items() if count >= 3], k=n):
            res += [{
                'suit': tile_key[0],
                'type': tile_key[1],
            } for _ in range(3)]
            self.samples[tile_key] -= 3
        return res

    def kong(self, n=1):
        res = []
        for tile_key in random.sample([key for key, count in self.samples.items() if count == 4], k=n):
            res += [{
                'suit': tile_key[0],
                'type': tile_key[1],
            } for _ in range(4)]
            self.samples[tile_key] -= 4
        return res

    def chow(self, n=1):
        res = []
        numeric_suits = {n['suit'] for n in numeric}
        chow_samples = {key for key, count in self.samples.items() if key[0] in numeric_suits and count >= 1}
        while n > 0:
            for tile_key in random.sample(chow_samples, k=n):
                if all([self.samples[(tile_key[0], tile_key[1] + i)] >= 1 for i in range(3)]):
                    for i in range(3):
                        res.append({
                            'suit': tile_key[0],
                            'type': tile_key[1] + i,
                        })
                        self.samples[(tile_key[0], tile_key[1] + i)] -= 1
                    n -= 1
                else:
                    chow_samples.remove(tile_key)
        return res

    def pair(self):
        res = []
        for tile_key in random.sample([key for key, count in self.samples.items() if count >= 2], k=1):
            res += [{
                'suit': tile_key[0],
                'type': tile_key[1],
            } for _ in range(2)]
            self.samples[tile_key] -= 2
        return res

    def rand_tile(self, n=1):
        res = []
        tile_pool = {key for key, count in self.samples.items() if count > 0}
        while n > 0:
            tile_key = random.sample(tile_pool, k=1)[0]
            if self.samples[tile_key] > 0:
                res.append({
                    'suit': tile_key[0],
                    'type': tile_key[1],
                })
                self.samples[tile_key] -= 1
                n -= 1
            else:
                tile_pool.remove(tile_key)
        return res

