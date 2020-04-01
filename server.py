import eventlet
import json
import logging
import os
import socketio
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from dotenv import load_dotenv
from operator import itemgetter
from pathlib import Path
from random import randrange

import server_logger
import mahjong_rules
from util.decorators import validate_payload_fields, log_exception
from tile_groups import honor, numeric, bonus
from cacheclient import MahjongCacheClient

# TODO: this is just for testing purposes
from tests.util import TileSampler

### Load environment variables from dotenv ###

env_path = Path('.') / '.env'

if os.getenv('MAHJONG_ENV', 'dev') == 'heroku':
    env_path = Path('.') / '.env.heroku'

load_dotenv(dotenv_path=env_path, verbose=True)

config = {}
config['include_bonus'] = os.getenv('INCLUDE_BONUS', 'True') == 'True'
config['to_console'] = os.getenv('TO_CONSOLE', 'False') == 'True'
config['to_file'] = os.getenv('TO_FILE', 'False') == 'True'
config['max_players_per_game'] = int(os.getenv('MAX_PLAYERS_PER_GAME', '4'))
config['claim_timeout_ms'] = int(os.getenv('CLAIM_TIMEOUT_MS', '5000'))

#### Server initialization #####

logger = server_logger.init(config['to_console'], config['to_file'])

logger.info(f'Loaded with config: {json.dumps(config, indent=4)}')

cache = MahjongCacheClient()

sio = socketio.Server(cors_allowed_origins='*', async_mode='eventlet')
app = socketio.WSGIApp(sio, static_files={ '/': 'index.html' })

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
    # FIXME: remove this when done testing
    # sampler = TileSampler()
    for idx, player_uuid in enumerate(player_uuids):
        player_tiles = room['player_by_uuid'][player_uuid]['tiles']

        # First player (dealer) gets 14 tiles, discards a tile to start the game
        num_of_tiles = 14 if idx == 0 else 13
        for _ in range(num_of_tiles):
            player_tiles.append(game_tiles.pop())
        # FIXME: remove this when done testing
        # if idx == 0:
        #     player_tiles.extend(sampler.kong() + sampler.rand_tile(9))
        # else:
        #     player_tiles.extend(sampler.rand_tile(13))

        # Group similar tiles
        player_tiles.sort(key=itemgetter('suit', 'type'))

        sio.emit('update_tiles', player_tiles, to=player_uuid)
    # FIXME: remove this when done testing
    # room['game_tiles'] = [{ 'suit': k[0], 'type': k[1] } for k, v in sampler.samples.items() for _ in range(v)]
    # logger.info(room['game_tiles'])
    logger.info(f'Dealt tiles to players for room_id={room_id}')

def emit_player_current_state(player_uuid, room_id):
    room = cache.get_room(room_id)
    new_state = room['player_by_uuid'][player_uuid]['currentState']
    sio.emit('update_current_state', new_state, to=player_uuid)
    logger.info(f'Sending state update of new_state={new_state} to player_uuid={player_uuid}')

def start_next_turn(room_id):
    room = cache.get_room(room_id)
    if not room['game_tiles']:
        logger.info(f'No more tiles to draw, end game for room_id={room_id}')
        emit_draw_game_state(room_id)
        return
    player_uuid = cache.point_to_next_player(room_id)
    update_opponents(room_id)
    start_turn(player_uuid, room_id)

def start_turn(player_uuid, room_id):
    emit_player_current_state(player_uuid, room_id)
    logger.info(f'Starting {player_uuid}\'s turn in room_id={room_id}')

def update_opponents(room_id):
    room = cache.get_room(room_id)
    for player_uuid in room['player_uuids']:
        update_opponents_for_player(room_id, player_uuid)

def update_opponents_for_player(room_id, player_uuid):
    opponents = cache.get_opponents(room_id, player_uuid)
    logger.info(f'Sending update_opponents event to player_uuid={player_uuid} with opponents={opponents} for room_id={room_id}')
    sio.emit('update_opponents', opponents, to=player_uuid)

def check_and_update_win_conditions(player_uuid, room_id):
    player = cache.get_room(room_id)['player_by_uuid'][player_uuid]

    can_win = mahjong_rules.can_meld_concealed_hand(player['tiles'], 4 - len(player['revealedMelds']))
    if can_win != player['canDeclareWin']:
        player['canDeclareWin'] = can_win
        sio.emit('update_can_declare_win', can_win, to=player_uuid)

def check_for_concealed_kong(player_uuid, room_id):
    player = cache.get_room(room_id)['player_by_uuid'][player_uuid]

    can_declare_kong = False
    for idx in range(len(player['tiles'])):
        if mahjong_rules.can_meld_kong(
            tiles=[t for j, t in enumerate(player['tiles']) if j != idx],
            discarded_tile=player['tiles'][idx]
        ):
            can_declare_kong = True
            break

    if can_declare_kong != player['canDeclareKong']:
        player['canDeclareKong'] = can_declare_kong
        sio.emit('update_can_declare_kong', can_declare_kong, to=player_uuid)

def emit_server_message(text, to, skip_sid=[]):
    sio.emit('text_message', {
        'msgType': 'SERVER_MSG',
        'msgText': text,
    }, to=to, skip_sid=skip_sid)

def emit_player_message(text, to, skip_sid=[]):
    sio.emit('text_message', {
        'msgType': 'PLAYER_MSG',
        'msgText': text,
    }, to=to, skip_sid=skip_sid)

##### Socket.IO event handlers #####

@sio.on('connect')
@log_exception
def connect(sid, environ):
    logger.info(f'Connect sid={sid}')

@sio.on('ready')
@validate_payload_fields(['player-uuid'])
@log_exception
def ready(sid, payload):
    player_uuid = payload['player-uuid']
    with sio.session(sid) as session:
        cache.connection_count += 1
        username = f'guest{cache.connection_count}'
        session['username'] = username

        if player_uuid not in cache.room_id_by_uuid:
            sio.enter_room(sid, 'lobby')
            emit_server_message(f'{username} has entered the lobby', to='lobby', skip_sid=sid)
            emit_server_message(f'You have entered the lobby as "{username}"', to=sid)

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

# TODO: Change back to retrieve_game_data or something
@sio.on('rejoin_game')
@validate_payload_fields(['player-uuid'])
@log_exception
def get_existing_game_data(sid, payload):
    player_uuid = payload['player-uuid']
    logger.info('Checking for game in progress')
    response_payload = {}
    if player_uuid in cache.room_id_by_uuid:
        room_id = cache.room_id_by_uuid[player_uuid]
        room = cache.get_room(room_id)
        logger.info(f'Found game in progress, rejoining active room_id={room_id}')

        save_session_data(sid, player_uuid, room_id)
        update_opponents_for_player(room_id, player_uuid)

        player = room['player_by_uuid'][player_uuid]
        response_payload = {
            'roomId': room_id,
            'username': player['username'],
            'tiles': player['tiles'],
            'currentState': player['currentState'],
            'discardedTile': room['current_discarded_tile'],
            'revealedMelds': player['revealedMelds'],
            'newMeld': player['newMeld'],
            'canDeclareWin': player['canDeclareWin'],
            'isGameOver': player['currentState'] in {'WIN', 'LOSS'},
            'concealedKongs': player['concealedKongs'],
            'pastDiscardedTiles': room['past_discarded_tiles'],
            'isHost': player['isHost'],
            'isGameInProgress': room['is_game_in_progress'],
        }
    else:
        logger.info('No game in progress')
    return response_payload

@sio.on('reemit_events')
@log_exception
def reemit_events(sid):
    """As it stands, this function is called from the client side once the client has loaded initial data.
       By this time, client should have rendered page."""
    with sio.session(sid) as session:
        room_id = session['room_id']
        player_uuid = session['player_uuid']
        player = cache.get_room(room_id)['player_by_uuid'][player_uuid]

        emit_declare_claim_with_timer(player_uuid, player)
        emit_player_valid_meld_subsets(player_uuid, player)

@sio.on('enter_game')
@validate_payload_fields(['username', 'player_uuid'])
@log_exception
def enter_game(sid, payload):
    new_username = payload['username']
    player_uuid = payload['player_uuid']
    room_id = payload['room_id'] if 'room_id' in payload else None
    should_create_room = payload['should_create_room'] if 'should_create_room' in payload else False

    if should_create_room:
        logger.info(f'Generating new room id for player_uuid={player_uuid} as host')
        room_id = cache.generate_room_id()
        cache.open_room_ids.add(room_id)

    if not room_id:
        # No room provided by client, search for next available room
        logger.info(f'No room provided by player_uuid={player_uuid}, searching for next available room')
        room_id = cache.search_for_room(player_uuid)

    if cache.get_room_size(room_id) == 4:
        logger.info(f'Player with player_uuid={player_uuid} and player_name={username} tried to join room with already 4 players room_id={room_id}')
        return

    # Player is by default assigned to room 'lobby' when not associated with a game
    username = sio.get_session(sid)['username']
    if new_username:
        # Only replace username if the username provided is non-empty
        old_username, username = username, new_username

        emit_server_message(f"{old_username} changed their name to \"{username}\"", to='lobby', skip_sid=sid)
        emit_server_message(f"You changed your name from \"{old_username}\" to \"{username}\"", to=sid)

    # Leave lobby room
    emit_server_message(f'{username} left the lobby', to='lobby', skip_sid=sid)
    emit_server_message(f'You left the lobby', to=sid)
    sio.leave_room(sid, 'lobby')

    # Add player into game data
    cache.add_player(room_id, username, player_uuid)

    save_session_data(sid, player_uuid, room_id)

    sio.emit('update_room_id', room_id, to=sid)

    update_opponents(room_id)

    # Announce message to chatroom
    emit_server_message(f'{username} joined the game', to=room_id, skip_sid=sid)
    emit_server_message(f'You joined the game', to=sid)

    selected_keys = { 'username', 'isHost' }
    player = cache.get_room(room_id)['player_by_uuid'][player_uuid]
    sio.emit('update_player', { k: player[k] for k in selected_keys if k in player }, to=sid)

def get_sio_with_handlers(username, player_uuid, room_id, cache):
    sio = socketio.Client()

    @sio.event
    def update_current_state(current_state):
        logger.info(f"AI {username} received update_current_state event")

        if current_state == 'DISCARD_TILE':
            player = cache.get_room(room_id)['player_by_uuid'][player_uuid]
            rand_idx = randrange(len(player['tiles']))
            sio.emit('end_turn', {
                'discarded_tile': player['tiles'][rand_idx],
            })
        elif current_state == 'DRAW_TILE':
            sio.emit('draw_tile')

    @sio.event
    def declare_claim_with_timer(payload):
        logger.info(f"AI {username} received declare_claim_with_timer event")
        sio.emit('update_claim_state', {
            'declared_meld': None,
        })

    server_url = 'http://localhost:5000'
    if os.getenv('MAHJONG_ENV', 'dev') == 'heroku':
        # FIXME: don't specify this explicitly in code
        server_url = 'https://mahjong-server-dev.herokuapp.com'

    sio.connect(server_url)

    sio.emit('ai_join_game', {
        'username': username,
        'player_uuid': player_uuid,
        'room_id': room_id,
    })

    return sio

def generate_ai_players(room_id, num_of_ai):
    ai_clients = []
    for i in range(num_of_ai):
        ai_player_uuid = uuid.uuid4().hex
        ai_player_username = f'AI-Player-{i}'
        ai_clients.append(get_sio_with_handlers(ai_player_username, ai_player_uuid, room_id, cache))

        cache.add_player(room_id, ai_player_username, ai_player_uuid)

@sio.on('ai_join_game')
@log_exception
def ai_join_game(sid, payload):
    username = payload['username']
    player_uuid = payload['player_uuid']
    room_id = payload['room_id'] if 'room_id' in payload else None

    save_session_data(sid, player_uuid, room_id)

    '''
    sio.emit('update_room_id', room_id, to=sid)

    update_opponents(room_id)
    '''

    # Announce message to chatroom
    emit_server_message(f'{username} joined the game', to=room_id, skip_sid=sid)

    '''
    selected_keys = { 'username', 'isHost' }
    player = cache.get_room(room_id)['player_by_uuid'][player_uuid]
    sio.emit('update_player', { k: player[k] for k in selected_keys if k in player }, to=sid)
    '''

@sio.on('start_game')
@log_exception
def start_game(sid):
    with sio.session(sid) as session:
        room_id = session['room_id']
        player_uuid = session['player_uuid']

        num_of_players = cache.get_room_size(room_id)
        room = cache.get_room(room_id)
        isHost = room['player_by_uuid'][player_uuid]['isHost']
        if not isHost:
            logger.warn(f'Received "start_game" event from non-host player with player_uuid={player_uuid}, not starting game')

        logger.info(f'Received "start_game" event from host player with player_uuid={player_uuid}, initializing game elements')

        if num_of_players < config['max_players_per_game']:
            num_of_ai = config['max_players_per_game'] - num_of_players
            logger.info(f"Only {num_of_players} player{'s' if num_of_players > 1 else ''} detected, generating {num_of_ai} AI player{'s' if num_of_ai > 1 else ''} for room_id={room_id}")

            generate_ai_players(room_id, num_of_ai)
            # FIXME: remove return statement once ai is implemented
            # return

        logger.info(f'Sufficient players in room, starting game for room_id={room_id}')
        init_tiles(room_id)
        deal_tiles(room_id)

        # player_uuid = room['player_uuids'][room['current_player_idx']]

        # Check if player can win, and emit event if they can
        check_and_update_win_conditions(player_uuid, room_id)

        # Check for concealed kong for current hand and emit data to client if applicable
        check_for_concealed_kong(player_uuid, room_id)

        cache.set_next_player(room_id, player_uuid, 'DISCARD_TILE')

        update_opponents(room_id)

        start_turn(player_uuid, room_id)

        # Mark game as in progress
        room['is_game_in_progress'] = True
        sio.emit('update_player', {
            'isGameInProgress': room['is_game_in_progress'],
        }, to=room_id)

@sio.on('draw_tile')
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
        player['tiles'].sort(key=itemgetter('suit', 'type'))
        sio.emit('extend_tiles', drawn_tile, to=sid)

        player['currentState'] = 'DISCARD_TILE'

        # Check win conditions for current hand
        check_and_update_win_conditions(player_uuid, room_id)

        # Check for concealed kong for current hand and emit data to client if applicable
        check_for_concealed_kong(player_uuid, room_id)

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
        if room['current_discarded_tile']:
            room['past_discarded_tiles'].append(room['current_discarded_tile'])
        room['current_discarded_tile'] = discarded_tile

        # Remove from player tiles
        player_tiles.remove(discarded_tile)

        # Update this player's tiles
        # sio.emit('update_tiles', player_tiles, to=sid)

        # Update discarded tile for all players in room 
        sio.emit('update_discarded_tile', discarded_tile, to=room_id)

        # Update opponent data for all players
        # TODO: should be optimized so that we only update the one opponent for 3 other players
        #       OR on the client side we can decide what needs to be updated? overall we shouldn't
        #       cause unnecessary renders
        update_opponents(room_id)

        # Give other players 2 seconds to decide to claim tile
        for pid in room['player_uuids']:
            if pid != player_uuid:
                cache.set_player_state(room_id, pid, 'DECLARE_CLAIM')

                emit_player_current_state(pid, room_id)
                emit_declare_claim_with_timer(pid, room['player_by_uuid'][pid])
            else:
                cache.set_player_state(room_id, pid, 'NO_ACTION')
                emit_player_current_state(pid, room_id)

def emit_declare_claim_with_timer(pid, player):
    if player['currentState'] != 'DECLARE_CLAIM':
        logger.debug(f"declare_claim_with_timer event will not be emitted due to state={player['currentState']}, player_uuid={pid}, player_name={player['username']}")
        return

    # The start time will only exist on a client page reload
    startTime = player['declareClaimStartTime']

    # If it exists, send start time to client so client can determine how much time has already passed
    formattedStartTime = f"{startTime.isoformat(timespec='milliseconds')}Z" if startTime else None

    # Let client know to start timer
    logger.debug(f"Initiating claim timer for player name={player['username']}")
    sio.emit('declare_claim_with_timer', {
        'startTime': formattedStartTime,
        'msDuration': config['claim_timeout_ms'],
    }, to=pid)

@sio.on('declare_claim_start')
@validate_payload_fields(['declareClaimStartTime'])
@log_exception
def declare_claim_start(sid, payload):
    start_time = payload['declareClaimStartTime']
    with sio.session(sid) as session:
        room_id = session['room_id']
        player_uuid = session['player_uuid']
        room = cache.get_room(room_id)
        player = room['player_by_uuid'][player_uuid]

        if not player['declareClaimStartTime']:
            converted_start_time = datetime.fromisoformat(start_time[:-1])
            logger.debug(f"startTime not set, setting declareClaimStartTime={converted_start_time} for player={player['username']}")
            player['declareClaimStartTime'] = converted_start_time

def get_next_player_uuid(players, discarded_tile):
    pids_by_rank = defaultdict(list)
    for p in players:
        is_next_player = p['rel_pos'] == 1
        rank = mahjong_rules.check_tiles_against_meld(
            p['tiles'],
            discarded_tile,
            p['declared_meld'],
            p['revealed_melds_count'],
            is_chow_allowed=is_next_player)
        logger.info(f"pid={p['pid']} received rank={rank} after verifying claim {p['declared_meld']}")
        pids_by_rank[rank].append((p['pid'], p['rel_pos'], p['declared_meld']))
    for i in range(3, 0, -1):
        if i in pids_by_rank:
            ranked_pids = pids_by_rank[i]
            if i == 3 and len(ranked_pids) > 1:
                tup = min(ranked_pids, key=itemgetter(1))
                return tup[0], tup[2]
            else:
                # Start turn of first element in pids_by_rank[i]
                tup = ranked_pids[0]
                return tup[0], tup[2]
    return None, None

# Player notifies server if they want to claim the tile or not
@sio.on('update_claim_state')
@log_exception
def update_claim_state(sid, payload):
    declared_meld = payload['declared_meld'] if 'declared_meld' in payload else None

    with sio.session(sid) as session:
        room_id = session['room_id']
        player_uuid = session['player_uuid']
        room = cache.get_room(room_id)
        player = room['player_by_uuid'][player_uuid]

        if player['currentState'] != 'DECLARE_CLAIM':
            logger.error(f"Received invalid claim update from player_uuid={player_uuid} with username={player['username']}")
            return

        startTime = player['declareClaimStartTime']
        if startTime:
            ms_elasped = int((datetime.utcnow() - startTime) / timedelta(microseconds=1)) // 1000
            logger.debug(f'update_claim_state: {ms_elasped}ms elapsed since startTime={startTime}')

        logger.info(f"Received claim with meld={declared_meld} from player_uuid={player_uuid} with username={player['username']}")

        if player_uuid not in room['claimed_player_uuids']:
            room['claimed_player_uuids'].add(player_uuid)
            player['currentState'] = 'NO_ACTION'
            player['declaredMeldType'] = declared_meld

            logger.info(f"New claim with meld={declared_meld} from player_uuid={player_uuid} with username={player['username']}, emitting new_state={player['currentState']} to client")

            emit_player_current_state(player_uuid, room_id)

        # All three other players at this point have updated their state after the 2 second window
        if len(room['claimed_player_uuids']) == 3:

            logger.info(f'Gathered all claims from players, get new order of play')

            # TODO: move this entire section into a different function, e.g. find_next_player?
            # Gather relative positions for each player
            players = []
            current_player_idx = room['current_player_idx']
            for pidx, pid in enumerate(room['player_uuids']):
                player = room['player_by_uuid'][pid]
                if player['declaredMeldType']:
                    players.append({
                        'pid': pid,
                        'tiles': player['tiles'],
                        'declared_meld': player['declaredMeldType'],
                        'rel_pos': (pidx - current_player_idx) % 4,
                        'revealed_melds_count': len(player['revealedMelds']),
                    })

                # Clear player data related to declaring claims on discards
                player['declareClaimStartTime'] = None
                player['declaredMeldType'] = None

            # Clear set of player uuids that submitted claim
            room['claimed_player_uuids'].clear()

            # Get next player according to submitted claims
            discarded_tile = room['current_discarded_tile']
            next_pid, meld_type = get_next_player_uuid(players, discarded_tile)
            if next_pid:
                # Remove most recently discarded tile
                room['current_discarded_tile'] = None

                # End game here, if player has won by claiming discard
                if meld_type == 'WIN':
                    logger.info(f'player_uuid={next_pid} won by claiming discard, emitting winning game state')

                    emit_winning_game_state(next_pid, room_id)
                    return

                logger.info(f'player_uuid={next_pid} needs to meld {meld_type}')

                # Start turn of this player id
                cache.set_next_player(room_id, next_pid, 'REVEAL_MELD')
                valid_tile_sets = mahjong_rules.get_valid_tile_sets(
                    room['player_by_uuid'][next_pid]['tiles'],
                    discarded_tile,
                    meld_type)

                next_player = room['player_by_uuid'][next_pid]
                next_player['validMeldSubsets'] = valid_tile_sets

                # Set declaredMeldType to save state in case page is reloaded, but needs to be cleared once the player completes the meld
                next_player['declaredMeldType'] = meld_type # TODO: save state some other way
                next_player['newMeld'] = [discarded_tile]

                # Give player ability to win even if they claimed with different meld type
                check_and_update_win_conditions(next_pid, room_id)

                # Update current discarded tile
                sio.emit('update_discarded_tile', None, to=room_id)

                # Update discarded tile history
                sio.emit('update_player', {
                    'pastDiscardedTiles': room['past_discarded_tiles'],
                }, to=room_id)

                # Update opponents for each player (mainly to update isCurrentTurn)
                update_opponents(room_id)

                # Finally enable player to reveal meld
                emit_player_current_state(next_pid, room_id)
                emit_player_valid_meld_subsets(next_pid, next_player)
            else:
                # By default, no one was able to claim the discard, so start the next turn
                start_next_turn(room_id)

def emit_player_valid_meld_subsets(player_uuid, player):
    if player['currentState'] != 'REVEAL_MELD':
        logger.debug(f"valid_tile_sets_for_meld event will not be emitted due to state={player['currentState']}, player_uuid={player_uuid}, player_name={player['username']}")
        return
    sio.emit('valid_tile_sets_for_meld', {
        'validMeldSubsets': player['validMeldSubsets'],
        'newMeld': player['newMeld'],
        'newMeldTargetLength': 4 if player['declaredMeldType'] == 'KONG' else 3,
    }, to=player_uuid)

@sio.on('complete_new_meld')
@validate_payload_fields(['new_meld'])
@log_exception
def complete_new_meld(sid, payload):
    new_meld = payload['new_meld']
    new_meld_len = len(new_meld)

    with sio.session(sid) as session:
        room_id = session['room_id']
        player_uuid = session['player_uuid']
        player = cache.get_room(room_id)['player_by_uuid'][player_uuid]

        logger.info(f"Received request from player_uuid={player_uuid}, player_name={player['username']} to add new_meld={new_meld} to revealed_melds={player['revealedMelds']}")

        discarded_tile = player['newMeld'][0]

        # Update player's revealedMelds
        player['revealedMelds'].append(sorted(new_meld, key=itemgetter('suit', 'type')))
        player['newMeld'].clear()
        player['declaredMeldType'] = None # FIXME: declaredMeldType needs to be cleared to ensure clean state before next round of claiming

        # Update player's tiles
        new_meld.remove(discarded_tile)
        for t in new_meld:
            player['tiles'].remove(t)

        player['currentState'] = 'DISCARD_TILE'
        if new_meld_len == 4:
            # Meld was a KONG, player needs to draw a replacement tile
            player['currentState'] = 'DRAW_TILE'

        emit_player_current_state(player_uuid, room_id)

@sio.on('declare_concealed_kong')
@log_exception
def declare_concealed_kong(sid):
    with sio.session(sid) as session:
        room_id = session['room_id']
        player_uuid = session['player_uuid']

        player = cache.get_room(room_id)['player_by_uuid'][player_uuid]

        # Remove kong from tiles and add to list of concealed kongs
        tile_for_kong = mahjong_rules.get_tile_for_kong(player['tiles'])
        if not tile_for_kong:
            logger.error(f"No valid tile available for concealed kong for player with player_uuid={player_uuid}, player_name={player_name}")
            return

        player['tiles'] = [t for t in player['tiles'] if t != tile_for_kong]
        player['concealedKongs'].append([dict(tile_for_kong) for _ in range(4)])
        player['currentState'] = 'DRAW_TILE'

        # TODO: Should be able to consolidate into one generic update event that should allow us to update
        #       an arbitrary number of fields on the player
        sio.emit('update_tiles', player['tiles'], to=player_uuid)
        sio.emit('update_concealed_kongs', player['concealedKongs'], to=player_uuid)
        sio.emit('update_current_state', player['currentState'], to=player_uuid)

@sio.on('declare_win')
@log_exception
def declare_win(sid):
    with sio.session(sid) as session:
        room_id = session['room_id']
        player_uuid = session['player_uuid']
        player = cache.get_room(room_id)['player_by_uuid'][player_uuid]
        player_name = player['username']

        logger.info(f"Player player_uuid={player_uuid}, player_name={player_name} declaring win")

        if player['currentState'] != 'DISCARD_TILE':
            logger.info(f"Player player_uuid={player_uuid}, player_name={player_name} declaring win")
            return

        num_of_melds = len(player['revealedMelds']) + len(player['concealedKongs'])
        if mahjong_rules.can_meld_concealed_hand(player['tiles'], 4 - num_of_melds):
            logger.info(f"Win attempt succeeded for player_uuid={player_uuid}, player_name={player_name}")

            emit_winning_game_state(player_uuid, room_id)
        else:
            logger.info(f"Win attempt failed for player_uuid={player_uuid}, player_name={player_name}")

def reduce_tiles_to_melds(player):
    num_of_melds = len(player['revealedMelds']) + len(player['concealedKongs'])
    return mahjong_rules.get_melds(player['tiles'], num_of_melds)

def emit_winning_game_state(winning_player_uuid, room_id):
    room = cache.get_room(room_id)

    winning_player = room['player_by_uuid'][winning_player_uuid]
    remaining_melds = reduce_tiles_to_melds(winning_player)
    winning_hand = remaining_melds + winning_player['revealedMelds'] + winning_player['concealedKongs']

    # FIXME: not the best way to do this, but this works because UI expects a
    # list of melds for revealedMelds data structure
    winning_player['revealedMelds'] = winning_hand
    winning_player['tiles'] = []
    update_opponents(room_id)

    for pid in room['player_uuids']:
        if pid == winning_player_uuid:
            room['player_by_uuid'][pid]['currentState'] = 'WIN'
        else:
            room['player_by_uuid'][pid]['currentState'] = 'LOSS'
        emit_player_current_state(pid, room_id)

    logger.info(f'Sending end_game event to all players in room_id={room_id}')
    sio.emit('end_game', to=room_id)

def emit_draw_game_state(room_id):
    room = cache.get_room(room_id)

    for pid in room['player_uuids']:
        room['player_by_uuid'][pid]['currentState'] = 'DRAW'
        emit_player_current_state(pid, room_id)

    logger.info(f'Sending end_game event to all players in room_id={room_id}')
    sio.emit('end_game', to=room_id)

@sio.on('text_message')
@validate_payload_fields(['message'])
@log_exception
def message(sid, payload):
    with sio.session(sid) as session:
        msg = payload['message']
        room_id = 'lobby'
        username = session['username']
        if 'room_id' in session:
            room_id = session['room_id']
            player_uuid = session['player_uuid']
            room = cache.get_room(room_id)
            username = room['player_by_uuid'][player_uuid]['username']

        # Emit to room, skip sender
        emit_player_message(f'{username}: {msg}', to=room_id, skip_sid=sid)

        # Emit to sender
        emit_player_message(f'You: {msg}', to=sid)

        logger.info(f'{username} says: {msg}')

@sio.on('leave_game')
@log_exception
def leave_game(sid):
    with sio.session(sid) as session:
        room_id = session['room_id']
        player_uuid = session['player_uuid']
        room = cache.get_room(room_id)

        # Remove player_uuid to room_id mapping
        del cache.room_id_by_uuid[player_uuid]

        # Remove player_uuid from socketio data
        sio.leave_room(sid, room_id)
        del session['room_id']

        logger.info(f'Player {player_uuid} left room_id={room_id}')

        # Free up space by deleting room data once the room is empty
        if cache.get_room_size(room_id) == 0:
            logger.info(f'Room room_id={room_id} is now empty, delete room data')
            del cache.rooms[room_id]

@sio.on('disconnect')
@log_exception
def disconnect(sid):
    logger.info(f'Disconnect sid={sid}')

if __name__ == '__main__':
    eventlet.wsgi.server(eventlet.listen(('', 5000)), app)

