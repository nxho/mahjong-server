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

def deal_tiles():
    game_tiles = cache.game_tiles
    player_sids = cache.player_sids
    for sid in player_sids:
        player_tiles = cache.get_player_tiles(sid)
        for i in range(14):
            random_idx = randrange(len(game_tiles))
            if random_idx != len(game_tiles) - 1:
                game_tiles[random_idx], game_tiles[-1] = game_tiles[-1], game_tiles[random_idx]

            player_tiles.append(game_tiles.pop())

        sio.emit('update_tiles', player_tiles, sid)
    print('Dealt tiles to players')

# Notify player to start turn
def start_turn(sid):
    sio.emit('start_turn', room=sid)

# Player notifies server to end their turn and start next player's turn
@sio.on('end_turn')
def end_turn(sid):
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
    print('disconnect ', sid)

if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)

