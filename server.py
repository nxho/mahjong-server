import eventlet
import functools
import json
import logging
import os
import socketio
from dotenv import load_dotenv
from pathlib import Path
from random import randrange

import server_logger
from tile_groups import honor, numeric, bonus
from cacheclient import MahjongCacheClient

### Load environment variables from dotenv ###

env_path = Path('.') / '.env'

if os.getenv('MAHJONG_ENV', 'dev') == 'heroku':
    env_path = Path('.') / '.env.heroku'

load_dotenv(dotenv_path=env_path, verbose=True)

config = {}
config['include_bonus'] = os.getenv('INCLUDE_BONUS', 'True') == 'True'
config['to_console'] = os.getenv('TO_CONSOLE', 'False') == 'True'
config['to_file'] = os.getenv('TO_FILE', 'False') == 'True'

#### Server initialization #####

logger = server_logger.init(config['to_console'], config['to_file'])

logger.info(f'Loaded with config: {json.dumps(config, indent=4)}')

cache = MahjongCacheClient()

sio = socketio.Server(cors_allowed_origins='*', async_mode='eventlet')
app = socketio.WSGIApp(sio)

##### Game-specific methods #####

def init_tiles(room_id):
    room = cache.get_room(room_id)
    game_tiles = room['game_tiles']
    tile_sets = [*honor, *numeric]
    if config['include_bonus']:
        tile_sets.append(*bonus)
    for tile_set in tile_sets:
        logger.info(f"Initializing {tile_set['suit']} tiles")
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
        player_tiles = room['player_by_uuid'][player_uuid]['tiles']

        # first player (dealer) gets 14 tiles, discards a tile to start the game
        num_of_tiles = 14 if idx == 0 else 13
        for _ in range(num_of_tiles):
            player_tiles.append(game_tiles.pop())

        sio.emit('update_tiles', player_tiles, room=player_uuid)
    logger.info(f'Dealt tiles to players for room_id={room_id}')

def emit_player_current_state(player_uuid, room_id):
    room = cache.get_room(room_id)
    new_state = room['player_by_uuid'][player_uuid]['currentState']
    sio.emit('update_current_state', new_state, room=player_uuid)
    logger.info(f'Sending state update of new_state={new_state} to player_uuid={player_uuid}')

def start_next_turn(room_id):
    player_uuid = cache.point_to_next_player(room_id)
    start_turn(player_uuid, room_id)

def start_game(room_id):
    room = cache.get_room(room_id)
    player_uuid = room['current_player_uuid']
    room['player_by_uuid'][player_uuid]['isCurrentTurn'] = True
    room['player_by_uuid'][player_uuid]['currentState'] = 'DISCARD_TILE'
    start_turn(player_uuid, room_id)

def start_turn(player_uuid, room_id):
    emit_player_current_state(player_uuid, room_id)
    logger.info(f'Starting {player_uuid}\'s turn in room_id={room_id}')
    sio.emit('start_turn', room=player_uuid)

def update_opponents(room_id):
    room = cache.get_room(room_id)
    for player_uuid in room['player_uuids']:
        update_opponents_for_player(room_id, player_uuid)

def update_opponents_for_player(room_id, player_uuid):
    opponents = cache.get_opponents(room_id, player_uuid)
    logger.info(f'Sending update_opponents event to player_uuid={player_uuid} with opponents={opponents} for room_id={room_id}')
    sio.emit('update_opponents', opponents, room=player_uuid)

##### Decorators for event handlers #####

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

##### Socket.IO event handlers #####

@sio.on('connect')
@log_exception
def connect(sid, environ):
    logger.info(f'Connect sid={sid}')

@sio.event
@validate_payload_fields(['player-uuid'])
@log_exception
def get_existing_game_data(sid, payload):
    player_uuid = payload['player-uuid']
    logger.info('Checking for game in progress')
    response_payload = {}
    if player_uuid in cache.room_id_by_uuid:
        room_id = cache.room_id_by_uuid[player_uuid]
        room = cache.get_room(room_id)
        logger.info(f'Found game in progress, active room_id={room_id}')
        response_payload = {
            'roomId': room_id,
            **room['player_by_uuid'][player_uuid]
        }
    else:
        logger.info('No game in progress')
    return response_payload

@sio.event
def get_possible_states(sid):
    states = list(cache.states)
    logger.info(f'Returning possible states={states}')
    return {
        'states': states,
    }

def save_session_data(sid, player_uuid, room_id):
    with sio.session(sid) as session:
        # Store socket id to user's uuid, subsequent events will use the socket id to determine user's uuid
        session['player_uuid'] = player_uuid
        logger.info(f"Saved player_uuid={player_uuid} to sid={sid}'s session")

        # Create room with user's uuid, so events can be emitted to a uuid vs a socket id
        sio.enter_room(sid, player_uuid)
        logger.info(f'Entered individual room for player_uuid={player_uuid}')

        session['room_id'] = room_id
        logger.info(f"Saved room_id={room_id} to sid={sid}'s session")

        sio.enter_room(sid, room_id)
        logger.info(f'Entered game room with room_id={room_id}')

@sio.on('rejoin_game')
@validate_payload_fields(['player_uuid', 'room_id'])
@log_exception
def rejoin_game(sid, payload):
    player_uuid = payload['player_uuid']
    room_id = payload['room_id']
    save_session_data(sid, player_uuid, room_id)
    update_opponents_for_player(room_id, player_uuid)

    room = cache.get_room(room_id)
    if room['discarded_tiles']:
        sio.emit('update_discarded_tile', room['discarded_tiles'][-1], room=sid)

@sio.on('enter_game')
@validate_payload_fields(['username', 'player_uuid'])
@log_exception
def enter_game(sid, payload):
    username = payload['username']
    player_uuid = payload['player_uuid']
    room_id = payload['room_id'] if 'room_id' in payload else None

    if not room_id:
        # No room provided by client, search for next available room
        logger.info(f'No room provided by player_uuid={player_uuid}, searching for next available room')
        room_id = cache.search_for_room(player_uuid)

    save_session_data(sid, player_uuid, room_id)

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
        start_game(room_id)

@sio.event
@log_exception
def draw_tile(sid):
    with sio.session(sid) as session:
        room_id = session['room_id']
        player_uuid = session['player_uuid']
        room = cache.get_room(room_id)
        player = room['player_by_uuid'][player_uuid]

        # Draw tile, add on server side, send tile to player using separate event type
        drawn_tile = room['game_tiles'].pop()
        player['tiles'].append(drawn_tile)
        sio.emit('extend_tiles', drawn_tile, room=sid)

        player['currentState'] = 'DISCARD_TILE'
        emit_player_current_state(player_uuid, room_id)

# Player notifies server to end their turn and start next player's turn
@sio.on('end_turn')
@validate_payload_fields(['discarded_tile'])
@log_exception
def end_turn(sid, payload):
    discarded_tile = payload['discarded_tile']

    with sio.session(sid) as session:
        room_id = session['room_id']
        player_uuid = session['player_uuid']
        room = cache.get_room(room_id)
        player = room['player_by_uuid'][player_uuid]

        username = player['username']
        logger.info(f'{username} discarded {discarded_tile}')

        player_tiles = player['tiles']
        if discarded_tile not in player_tiles:
            logger.error(f"discarded_tile={discarded_tile} does not exist in player_uuid={player_uuid}'s tiles")
            return

        # Add to discarded tiles history
        room['discarded_tiles'].append(discarded_tile)

        # Remove from player tiles
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

        msg_to_send = f'{username}: {msg}'
        room['messages'].append(msg_to_send)
        sio.emit('text_message', msg_to_send, room=room_id)
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

