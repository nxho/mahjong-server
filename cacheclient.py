# TODO: leverage this when migrating to Redis(?), we can use the same methods from the socketio listeners, we'll just change the method implementation
# Reasons for doing this (is this justifiable?):
#   - We can implement an in-memory storage while the server is running
#   - Easy migration to Redis
#   - Separation of socketio logic from persistence logic
class MahjongCacheClient:
    def __init__(self):
        self.players = {}
        # TODO: use uuids instead of sids
        # - Generate and return uuid to client when new client joins game
        self._player_sids = []
        self.game_tiles = []
        self.current_player_idx = 0

    @property
    def game_tiles(self):
        return self._game_tiles

    @game_tiles.setter
    def game_tiles(self, game_tiles):
        self._game_tiles = game_tiles

    @property
    def player_sids(self):
        return self._player_sids

    @player_sids.setter
    def player_sids(self, player_sids):
        self._player_sids = player_sids

    def add_player(self, sid, username):
        self.players[sid] = {
            'name': username,
            'tiles': [],
            'isCurrentTurn': False,
        }
        self.player_sids.append(sid)

    def remove_player(self, sid):
        print(f'Removing {sid} data')
        if sid in self.players:
            self.player_sids.remove(sid)
            del self.players[sid]

    def get_player_name(self, sid):
        return self.players[sid]['name']

    def get_player_tiles(self, sid):
        return self.players[sid]['tiles']

    def get_current_player_sid(self):
        return self.player_sids[self.current_player_idx]

    def inc_current_player_idx(self):
        self.current_player_idx = (self.current_player_idx + 1) % 4

