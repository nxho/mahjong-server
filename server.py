import socketio
import eventlet
import functools
import server_logger
import logging
from random import randrange
from tile_groups import honor, numeric, bonus
from cacheclient import MahjongCacheClient

logger = server_logger.init(to_console=False)

sio = socketio.Server(cors_allowed_origins='*')
app = socketio.WSGIApp(sio)

cache = MahjongCacheClient()

'''
Game-specific methods
'''

def init_tiles(room_id):
    room = cache.get_room(room_id)
    game_tiles = room['game_tiles']
    for tile_set in [*honor, *numeric, *bonus]:
        for i in range(tile_set['count']):
            for tile_type in tile_set['types']:
                game_tiles.append({
                    'suit': tile_set['suit'],
                    'type': tile_type
                });

    # Shuffle game tiles
    for i in range(len(game_tiles) - 1, 0, -1):
        j = randrange(i + 1)
        if i != j:
            game_tiles[i], game_tiles[j] = game_tiles[j], game_tiles[i]

    logger.info(f'Initialized game tiles for room_id={room_id}')

def deal_tiles(room_id):
    room = cache.get_room(room_id)
    game_tiles = room['game_tiles']
    player_uuids = room['player_uuids']
    for idx, player_uuid in enumerate(player_uuids):
        player_tiles = room['player_by_uuid']['tiles']

        # first player (dealer) gets 14 tiles, discards a tile to start the game
        num_of_tiles = 14 if idx == 0 else 13
        for _ in range(num_of_tiles):
            player_tiles.append(game_tiles.pop())

        sio.emit('update_tiles', player_tiles, room=player_uuid)
    logger.info(f'Dealt tiles to players for room_id={room_id}')

def start_next_turn(room_id):
    player_uuid = cache.point_to_next_player(room_id)
    logger.info(f'Starting {player_uuid}\'s turn in room_id={room_id}')
    sio.emit('start_turn', room=player_uuid)

def update_opponents(room_id):
    room = cache.get_room(room_id)
    player_uuids = room['player_uuids']
    for player_uuid in player_uuids:
        opponents = list(map(lambda pid: { 'name':  room['player_by_uuid'][pid]['username'] },
                             list(filter(lambda other_pid: other_pid != player_uuid, player_uuids))))
        logger.info(f'Sending update_opponents event to player_uuid={player_uuid} with opponents={opponents} for room_id={room_id}')
        sio.emit('update_opponents', opponents, room=player_uuid)

'''
Decorators for event handlers
'''

def validate_payload_fields(fields):
    """Decorator that checks for existence of fields in the payload passed to an event handler"""
    def _validate_payload_fields(func):
        @functools.wraps(func)
        def wrapper_validate_payload_fields(*args, **kwargs):
            logger.info('asdfsadfasdlkj')

            if len(args) < 2 and ('sid' not in kwargs or 'payload' not in kwargs):
                return
            if len(args) >= 2:
                sid, payload = args[0], args[1]
            else:
                sid = kwargs['sid']
                payload = kwargs['payload']

            if type(payload) != dict:
                logger.error(f'Expected type={dict}, found type={type(payload)}')
                return

            fields_not_present = []
            for f in fields:
                if f not in payload:
                    fields_not_present.append(f)
            if fields_not_present:
                logger.error(f'sid={sid} called event_handler="{func.__name__}" but missing fields={fields_not_present}')
                return

            # all validation passed, run actual event handler
            return func(*args, **kwargs)
        return wrapper_validate_payload_fields
    return _validate_payload_fields

def log_exception(func):
    """Decorator that captures exceptions in event handlers and passes them to the logger"""
    @functools.wraps(func)
    def wrapper_log_exception(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            logger.exception(f'Exception occured in event_handler={func.__name__}')
    return wrapper_log_exception

'''
Socket.IO event handlers
'''

@sio.on('connect')
@log_exception
def connect(sid, environ):
    logger.info(f'Connect sid={sid}')
    qs_dict = {k: v for k, v in [s.split('=') for s in environ['QUERY_STRING'].split('&')]}
    if 'mahjong-player-uuid' in qs_dict:
        player_uuid = qs_dict['mahjong-player-uuid']
        logger.info('Checking for game in progress')
        if player_uuid in cache.room_id_by_uuid:
            room_id = cache.room_id_by_uuid[player_uuid]
            room = cache.get_room(room_id)
            logger.info(f'Found game in progress, active room_id={room_id}')
            sio.emit('pull_existing_game_data', { 'room_id': room_id, **room['player_by_uuid'][player_uuid] }, room=sid)
        else:
            logger.info('No game in progress')
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
@sio.on('enter_game')
@validate_payload_fields(['username', 'player_uuid'])
@log_exception
def enter_game(sid, payload):
    logger.info(payload)
    username = payload['username']
    player_uuid = payload['player_uuid']
    room_id = payload['room_id'] if 'room_id' in payload else None
    with sio.session(sid) as session:
        # Store socket id to user's uuid, subsequent events will use the socket id to determine user's uuid
        session['player_uuid'] = player_uuid
        logger.info(f"Saved player_uuid={player_uuid} to sid={sid}'s session")

        # Create room with user's uuid, so events can be emitted to a uuid vs a socket id
        sio.enter_room(sid, player_uuid)
        logger.info(f'Created individual room for player_uuid={player_uuid}')

        if not room_id:
            # No room provided by client, search for next available room
            logger.info(f'No room provided by player_uuid={player_uuid}, searching for next available room')
            room_id = cache.search_for_room(player_uuid)

            session['room_id'] = room_id
            logger.info(f"Saved room_id={room_id} to sid={sid}'s session")
            sio.enter_room(sid, room_id)
            logger.info(f'Entered game with room_id={room_id}')

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
            logger.info(f'Enough players have joined, starting game for room_id={room_id}')
            init_tiles(room_id)
            deal_tiles(room_id)
            start_next_turn(room_id)

# Player notifies server to end their turn and start next player's turn
@sio.on('end_turn')
@validate_payload_fields(['discarded_tile'])
@log_exception
def end_turn(sid, payload):
    discarded_tile = payload['discarded_tile']
    logger.info(f'{cache.get_player_name(sid)} discarded {discarded_tile}')

    with sio.session(sid) as session:
        room_id = session['room_id']
        player_uuid = session['player_uuid']
        room = cache.get_room(room_id)

        player_tiles = room['player_by_uuid'][player_uuid]['tiles']
        if discarded_tile not in player_tiles:
            logger.error(f"discarded_tile={discarded_tile} does not exist in player_uuid={player_uuid}'s tiles")
            return

        player_tiles.remove(discarded_tile)

        # Update this player's tiles
        sio.emit('update_tiles', player_tiles, room=sid)

        # Update discarded tile for all players in room 
        sio.emit('update_discarded_tile', discarded_tile, room=room_id)

        # Start next player's turn
        start_next_turn(room_id)

@sio.on('text_message')
@validate_payload_fields(['message'])
@log_exception
def message(sid, payload):
    with sio.session(sid) as session:
        msg = payload['message']
        room_id = session['room_id']
        player_uuid = session['player_uuid']
        room = cache.get_room(room_id)
        username = room['player_by_uuid'][player_uuid]['username']
        sio.emit('text_message', f'{username}: {msg}', room=room_id)
        logger.info(f'{username} says: {msg}')

@sio.on('leave_game')
@log_exception
def leave_game(sid):
    with sio.session(sid) as session:
        room_id = session['room_id']
        room = cache.get_room_obj(room_id)
        room.remove_player(session['player_uuid'])
        sio.leave_room(room_id)
        del session['room_id']
        logger.info(f'Player {player_uuid} left room_id={room_id}')

@sio.on('disconnect')
@log_exception
def disconnect(sid):
    logger.info(f'Disconnect sid={sid}')

if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)

