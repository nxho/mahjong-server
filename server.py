import socketio
import eventlet
import functools
from random import randrange
from tile_groups import honor, numeric, bonus
from cacheclient import MahjongCacheClient

sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio)

cache = MahjongCacheClient()

'''
Game-specific methods
'''

def init_tiles(room_id):
    game_tiles = get_game_tiles(room_id)
    for tile_set in [*honor, *numeric, *bonus]:
        for i in range(tile_set['count']):
            for tile_type in tile_set['types']:
                game_tiles.append({
                    'suit': tile_set['suit'],
                    'type': tile_type
                });
    print('Initialized game tiles')

def draw_tile(room_id):
    game_tiles = cache.get_game_tiles(room_id)
    random_idx = randrange(len(game_tiles))
    if random_idx != len(game_tiles) - 1:
        game_tiles[random_idx], game_tiles[-1] = game_tiles[-1], game_tiles[random_idx]
    return game_tiles.pop()

def deal_tiles(room_id):
    room_data = cache.get_room(room_id)
    game_tiles = room_data['game_tiles']
    player_uuids = room_data['player_uuid']
    for idx, sid in enumerate(player_uuids):
        player_tiles = cache.get_player_tiles()

        # first player (dealer) gets 14 tiles, discards a tile to start the game
        num_of_tiles = 14 if idx == 0 else 13
        for _ in range(num_of_tiles):
            player_tiles.append(draw_tile(sid))

        sio.emit('update_tiles', player_tiles, sid)
    print('Dealt tiles to players')

# Notify player to start turn
def start_turn(sid):
    print(f'Starting {sid}\'s turn')
    sio.emit('start_turn', room=sid)

def update_opponents(room_id):
    room = cache.get_room(room_id)
    player_uuids = room['player_uuids']
    for player_uuid in player_uuids:
        opponents = list(map(lambda pid: { 'name':  room['player_by_uuid'][pid]['username'] },
                             list(filter(lambda other_pid: other_pid != player_uuid, player_uuids))))
        print(f'sending update_opponents event to player_uuid={player_uuid} with opponents={opponents}')
        sio.emit('update_opponents', opponents, room=player_uuid)

'''
Decorators for event handlers
'''

def validate_payload_fields(fields):
    """Decorator that checks for existence of fields in the payload passed to an event handler"""
    def _validate_payload_fields(func):
        @functools.wraps(func)
        def wrapper_validate_payload_fields(*args, **kwargs):
            if len(args) < 2 and ('sid' not in kwargs or 'payload' not in kwargs):
                return
            if len(args) >= 2:
                sid, payload = args[0], args[1]
            else:
                sid = kwargs['sid']
                payload = kwargs['payload']

            if type(payload) != dict:
                print(f'ERROR: expected type={dict}, found type={type(payload)}')
                return

            fields_not_present = []
            for f in fields:
                if f not in payload:
                    fields_not_present.append(f)
            if fields_not_present:
                print(f'ERROR: sid={sid} called event_handler="{func.__name__}" but missing fields={fields_not_present}')
                return

            # all validation passed, run actual event handler
            return func(args, kwargs)
        return wrapper_validate_payload_fields
    return _validate_payload_fields

'''
Socket.IO event handlers
'''

@sio.on('connect')
def connect(sid, environ):
    print(f'sio: connect {sid}')
    qs_dict = {k: v for k, v in [s.split('=') for s in environ['QUERY_STRING'].split('&')]}
    if 'mahjong-player-uuid' in qs_dict:
        player_uuid = qs_dict['mahjong-player-uuid']
        print('Checking for game in progress')
        if player_uuid in cache.room_id_by_uuid:
            room_id = cache.room_id_by_uuid[player_uuid]
            room = cache.get_room(room_id)
            print(f'Found game in progress, active room_id={room_id}')
            sio.emit('pull_existing_game_data', { 'room_id': room_id, **room['player_by_uuid'][player_uuid] }, room=sid)
        else:
            print('No game in progress')
            sio.emit('pull_existing_game_data', {}, room=sid)

'''
This event handler handles 3 different scenarios:
    - User is rejoining, this event handler is called automatically when frontend page loads
    - User specifies room id to join
        - If room id exists, and player does not exist in room, player is added to room
        - If room id exists and player is in room, player is not added
    - User does not specify room id
        - Random open room is picked for user to join

Maybe I should separate out concerns, latter half of this function is ensuring that other clients know about
players that have just joined
'''
@validate_payload_fields(['username', 'player_uuid'])
@sio.on('enter_game')
def enter_game(sid, payload):
    username = payload['username']
    player_uuid = payload['player_uuid']
    room_id = payload['room_id'] if 'room_id' in payload else None
    with sio.session(sid) as session:
        # Store socket id to user's uuid, subsequent events will use the socket id to determine user's uuid
        session['player_uuid'] = player_uuid
        print(f"Saved player_uuid={player_uuid} to sid={sid}'s session")

        # Create room with user's uuid, so events can be emitted to a uuid vs a socket id
        sio.enter_room(sid, player_uuid)
        print(f'Created individual room for player_uuid={player_uuid}')

        if room_id is None:
            # No room provided by client, search for next available room
            room_id = cache.search_for_room(player_uuid)

        session['room_id'] = room_id
        print(f"Saved room_id={room_id} to sid={sid}'s session")
        sio.enter_room(sid, room_id)
        print(f'Entered game with room_id={room_id}')

    sio.emit('update_room_id', room_id, room=sid)

    # Add player into game data
    cache.add_player(room_id, username, player_uuid)

    # Update opponents for all room members
    update_opponents(room_id)

    # Announce message to chatroom
    sio.emit('text_message', f'{username} joined the game', room=room_id)

    # If enough players, start game
    num_of_players = cache.get_room_size(room_id)
    if num_of_players == 4:
        print('Enough players have joined, starting game')
        init_tiles(sid)
        deal_tiles(sid)
        start_turn(cache.get_current_player_sid())

# Player notifies server to end their turn and start next player's turn
@validate_payload_fields(['discarded_tile'])
@sio.on('end_turn')
def end_turn(sid, payload):
    discarded_tile = payload['discarded_tile']
    print(f'{cache.get_player_name(sid)} discarded {discarded_tile}')

    player_tiles = cache.get_player_tiles(sid)

    if discarded_tile not in player_tiles:
        print(f'ERROR: discarded_tile={discarded_tile} does not exist in sid={sid} tiles')
        return

    player_tiles.remove(discarded_tile)

    # Update sid's player tiles
    sio.emit('update_tiles', player_tiles, room=sid)

    # Update all sid's discarded tile
    sio.emit('update_discarded_tile', discarded_tile, room=get_room_id(sid))

    # Point to next player
    cache.inc_current_player_idx(sid)
    start_turn(cache.get_current_player_sid(sid))

@validate_payload_fields(['message'])
@sio.on('text_message')
def message(sid, payload):
    with sio.session(sid) as session:
        msg = payload['message']
        room_id = session['room_id']
        username = session['username']
        sio.emit('text_message', f'{username}: {msg}', room=room_id)
        print(f'{username} says: {msg}')

@sio.on('leave_game')
def leave_game(sid):
    with sio.session(sid) as session:
        room_id = session['room_id']
        room = cache.get_room_obj(room_id)
        room.remove_player(session['player_uuid'])
        sio.leave_room(room_id)
        del session['room_id']
        print(f'Player {player_uuid} left room_id={room_id}')

@sio.on('disconnect')
def disconnect(sid):
    print(f'sio: disconnect {sid}')

if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)

