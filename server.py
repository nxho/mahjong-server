import socketio
import eventlet
from random import randrange
from tile_groups import honor, numeric, bonus
from cacheclient import MahjongCacheClient

sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio)

cache = MahjongCacheClient()

def init_tiles():
    game_tiles = []
    for tile_set in [*honor, *numeric, *bonus]:
        for i in range(tile_set['count']):
            for tile_type in tile_set['types']:
                game_tiles.append({
                    'suit': tile_set['suit'],
                    'type': tile_type
                });
    cache.game_tiles = game_tiles
    print('Initialized game tiles')

def draw_tile():
    game_tiles = cache.game_tiles
    random_idx = randrange(len(game_tiles))
    if random_idx != len(game_tiles) - 1:
        game_tiles[random_idx], game_tiles[-1] = game_tiles[-1], game_tiles[random_idx]
    return game_tiles.pop()

def deal_tiles():
    game_tiles = cache.game_tiles
    player_sids = cache.player_sids
    for idx, sid in enumerate(player_sids):
        player_tiles = cache.get_player_tiles(sid)

        # first player (dealer) gets 14 tiles, discards a tile to start the game
        num_of_tiles = 14 if idx == 0 else 13
        for _ in range(num_of_tiles):
            player_tiles.append(draw_tile())

        sio.emit('update_tiles', player_tiles, sid)
    print('Dealt tiles to players')

# Notify player to start turn
def start_turn(sid):
    print(f'Starting {sid}\'s turn')
    sio.emit('start_turn', room=sid)

# Player notifies server to end their turn and start next player's turn
@sio.on('end_turn')
def end_turn(sid, discarded_tile):
    print(f'{cache.get_player_name(sid)} discarded {discarded_tile}')

    player_tiles = cache.get_player_tiles(sid)

    if discarded_tile not in player_tiles:
        print(f'ERROR: discarded_tile={discarded_tile} does not exist in sid={sid} tiles')
        return

    player_tiles.remove(discarded_tile)

    # Update sid's player tiles
    sio.emit('update_tiles', player_tiles, room=sid)

    # Update all sid's discarded tile
    sio.emit('update_discarded_tile', discarded_tile, room='game')

    # Point to next player
    cache.inc_current_player_idx()
    start_turn(cache.get_current_player_sid())

def update_opponents():
    player_sids = cache.player_sids
    for sid in player_sids:
        opponents = list(map(lambda sid: { 'name': cache.get_player_name(sid) },
                             list(filter(lambda other_sid: other_sid != sid, player_sids))))
        print(f'sending update_opponents event to sid={sid} with opponents={opponents}')
        sio.emit('update_opponents', opponents, room=sid)

@sio.on('connect')
def connect(sid, environ):
    print('connect ', sid)

@sio.on('text_message')
def message(sid, msg):
    username = cache.get_player_name(sid)
    sio.emit('text_message', f'{username}: {msg}', room='game')
    print(f'{username} says: {msg}')

@sio.on('enter_game')
def enter_game(sid, username):
    print(f'{sid} joined game as {username}')
    sio.enter_room(sid, 'game')

    cache.add_player(sid, username)

    sio.emit('text_message', f'{username} joined the game', room='game')

    update_opponents()

    # If enough players, start game
    if len(cache.players) == 4:
        print('Enough players have joined, starting game')
        init_tiles()
        deal_tiles()
        start_turn(cache.get_current_player_sid())

@sio.on('leave_game')
def leave_game(sid):
    username = sio.get_session(sid)['username']
    print(f'{sid} left game as {username}')
    cache.remove_player(sid)
    sio.leave_room(sid, 'game')

@sio.on('disconnect')
def disconnect(sid):
    # On page reload, remove players from game pool
    cache.remove_player(sid)
    # Also, just reset player_idx to 0 to reset game
    cache.current_player_idx = 0
    print('disconnect ', sid)

if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)

