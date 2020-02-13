from collections import defaultdict
import random
import string
import server_logger

logger = server_logger.get()

# TODO: leverage this when migrating to Redis(?), we can use the same methods from the socketio listeners, we'll just change the method implementation
# Reasons for doing this (is this justifiable?):
#   - We can implement an in-memory storage while the server is running
#   - Easy migration to Redis
#   - Separation of socketio logic from persistence logic
class MahjongCacheClient:
    def __init__(self):
        self.rooms = defaultdict(lambda: {
            'game_tiles': [],
            'player_by_uuid': {},
            'player_uuids': [],
            'current_player_idx': 0,
            'past_discarded_tiles': [],
            'current_discarded_tile': None,
            'messages': [],
            'claimed_player_uuids': set(),
            'human_player_count': 0,
            'is_game_in_progress': False,
        })

        # User uuid to room id map, useful for rejoining a game
        self.room_id_by_uuid = {}

        # Rooms with < 4 players
        self.open_room_ids = set()

        # Possible player states
        self.states = set([
            'NO_ACTION',
            'DRAW_TILE',
            'DISCARD_TILE',
            'DECLARE_CLAIM',
            'REVEAL_MELD',
            'LOSS',
            'WIN',
        ])

        self.connection_count = 0

    def get_room(self, room_id):
        return self.rooms[room_id]

    def get_room_size(self, room_id):
        return len(self.rooms[room_id]['player_uuids'])

    # TODO: should solve for collisions?
    def generate_room_id(self):
        chars = [c for c in string.ascii_letters + string.digits]
        random.shuffle(chars)
        return ''.join([random.choice(chars) for _ in range(8)])

    def search_for_room(self, player_uuid):
        if player_uuid in self.room_id_by_uuid:
            room_id = self.room_id_by_uuid[player_uuid]
            logger.info(f'Player player_uuid={player_uuid} is already in room_id={room_id}')
            return room_id

        logger.info(f'open_rooms: {self.open_room_ids}')
        for r_id in self.open_room_ids:
            room_size = self.get_room_size(r_id)
            if room_size < 4:
                logger.info(f'Found available room_id={r_id}')
                if room_size == 3:
                    logger.info(f'Room has 3 players already, removing room_id={r_id} from open rooms set')
                    self.open_room_ids.remove(r_id)
                return r_id

        # No available room found, creating new room for player
        logger.info(f'No available rooms, creating new room for player_uuid={player_uuid}')
        new_room_id = self.generate_room_id()
        self.open_room_ids.add(new_room_id)
        return new_room_id

    def get_opponents(self, room_id, player_uuid):
        room = self.get_room(room_id)
        player_idx = room['player_uuids'].index(player_uuid)
        num_of_players = len(room['player_uuids'])
        # Order opponent uuids in order of play
        opponent_uuids = [room['player_uuids'][(player_idx + i) % num_of_players] for i in range(1, num_of_players)]
        return [{
            'name': room['player_by_uuid'][opponent_id]['username'],
            'revealedMelds': room['player_by_uuid'][opponent_id]['revealedMelds'],
            'tileCount': len(room['player_by_uuid'][opponent_id]['tiles']),
            'concealedKongs': room['player_by_uuid'][opponent_id]['concealedKongs'],
            'isCurrentTurn': room['player_by_uuid'][opponent_id]['currentState'] in { 'DRAW_TILE', 'DISCARD_TILE', 'REVEAL_MELD' },
        } for opponent_id in opponent_uuids]

    def add_player(self, room_id, username, player_uuid, isAi=False):
        if player_uuid in self.room_id_by_uuid:
            logger.info(f'Player uuid {player_uuid} is already in room, not re-adding')
            return

        # Add mapping for uuid to room_id, this will be used to search for an ongoing game if player disconnects
        self.room_id_by_uuid[player_uuid] = room_id

        # Retrieve room object
        room = self.get_room(room_id)

        # Initialize player data for uuid
        room['player_by_uuid'][player_uuid] = {
            'username': username,
            'tiles': [],
            'currentState': 'NO_ACTION',
            'declareClaimStartTime': None,
            'declaredMeldType': None,
            'validMeldSubsets': None,
            'revealedMelds': [],
            'newMeld': [],
            'concealedKongs': [],
            'canDeclareKong': False,
            'canDeclareWin': False,
            'isHost': True if not room['player_uuids'] else False,
            'isAi': isAi,
        }

        # Add uuid to list of active players
        room['player_uuids'].append(player_uuid)

        if not isAi:
            room['human_player_count'] += 1

    # TODO: generalize function to "set current player" essentially, can
    #       pass in optional parameter to set a specific player
    def point_to_next_player(self, room_id):
        room = self.get_room(room_id)
        current_player_idx = room['current_player_idx']
        current_player_uuid = room['player_uuids'][current_player_idx]

        room['player_by_uuid'][current_player_uuid]['currentState'] = 'NO_ACTION'

        room['current_player_idx'] = current_player_idx = (current_player_idx + 1) % 4
        current_player_uuid = room['player_uuids'][current_player_idx]

        self.set_next_player(room_id, current_player_uuid, 'DRAW_TILE')

        return current_player_uuid

    def set_next_player(self, room_id, player_uuid, next_state):
        room = self.get_room(room_id)

        room['current_player_idx'] = room['player_uuids'].index(player_uuid)
        room['player_by_uuid'][player_uuid]['currentState'] = next_state

    def set_player_state(self, room_id, player_uuid, new_state):
        self.rooms[room_id]['player_by_uuid'][player_uuid]['currentState'] = new_state

