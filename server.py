import socketio
import eventlet
from random import randrange
from tile_groups import honor, numeric, bonus

sio = socketio.Server()
app = socketio.WSGIApp(sio)

# TODO: use uuids instead of sids
# - generate and return uuid to client when new client joins game
players = {}
player_sids = []
game_tiles = []
current_player_idx = 0

def init_tiles():
    for tile_set in [*honor, *numeric, *bonus]:
        for i in range(tile_set['count']):
            for tile_type in tile_set['types']:
                game_tiles.append({
                    'suit': tile_set['suit'],
                    'type': tile_type
                });

def deal_tiles():
    for sid in player_sids:
        player_tiles = players[sid]['tiles']

        for i in range(14):
            random_idx = randrange(len(game_tiles))
            if random_idx != len(game_tiles) - 1:
                game_tiles[random_idx], game_tiles[-1] \
                    = game_tiles[-1], game_tiles[random_idx]

            player_tiles.append(game_tiles.pop())

        sio.emit('update_tiles', player_tiles, sid)

# notify player to start turn
def start_turn():
    sio.emit('start_turn', room=player_sids[current_player_idx])

# player notifies server to end their turn and start next player's turn
@sio.on('end_turn')
def end_turn():
    current_player_idx = (current_player_idx + 1) % 4
    start_turn()

def update_opponents():
    for sid in player_sids:
        opponents = list(map(lambda sid: { 'name': players[sid]['name'] },
                             list(filter(lambda other_sid: other_sid != sid, player_sids))))
        print(f'sending update_opponents event to sid={sid} with opponents={opponents}')
        sio.emit('update_opponents', opponents, room=sid)

@sio.on('connect')
def connect(sid, environ):
    print('connect ', sid)

@sio.on('text_message')
def message(sid, msg):
    username = players[sid]['name']
    sio.emit('text_message', f'{username}: {msg}', room='game')
    print(f'{username} says: {msg}')

@sio.on('enter_game')
def enter_game(sid, username):
    print(f'{sid} joined game as {username}')
    sio.enter_room(sid, 'game')

    players[sid] = {
        'name': username,
        'tiles': [],
        'isCurrentTurn': False,
    }
    player_sids.append(sid)

    sio.emit('text_message', f'{username} joined the game', room='game')

    update_opponents()

    # if enough players, start game
    if len(players) == 4:
        init_tiles()
        deal_tiles()
        start_turn()

@sio.on('leave_game')
def leave_game(sid):
    username = sio.get_session(sid)['username']
    print(f'{sid} left game as {username}')
    player_sids.remove(sid)
    del players[sid]
    sio.leave_room(sid, 'game')

@sio.on('disconnect')
def disconnect(sid):
    # on page reload, remove players from game pool
    if sid in players:
        player_sids.remove(sid)
        del players[sid]
    print('disconnect ', sid)

if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)

