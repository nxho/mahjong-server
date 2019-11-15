from collections import defaultdict
import random
import string
import server_logger

logger = server_logger.get()

class Room:
    """Interface containing methods for common player/room interactions"""
    def __init__(self, room):
        self.room = room

    def remove_player(self, player_uuid):
        del room['player_by_uuid'][player_uuid]
        room['player_uuids'].remove(player_uuid)

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
            'current_player_uuid': None,
            'discarded_tiles': [],
            'messages': [],
        })

        # User uuid to room id map
        self.room_id_by_uuid = {}

        # Rooms with < 4 players
        self.open_room_ids = set()

        # Possible player states
        self.states = set([
            'DRAW_TILE',
            'DISCARD_TILE',
            'CAN_CLAIM_TILE',
            'NO_ACTION',
            'LOSS',
            'WIN',
        ])

    def get_room(self, room_id):
        return self.rooms[room_id]

    def get_room_obj(self, room_id):
        # TODO: is this a use case for context manager e.g. when using Redis?
        # because behind the scenes we want to initialize a Room obj, and then finally
        # when we're done updating the object, we want to submit the updates to Redis
        return Room(self.rooms[room_id])

    def get_room_size(self, room_id):
        return len(self.rooms[room_id]['player_uuids'])

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
        return list(map(lambda pid: { 'name':  room['player_by_uuid'][pid]['username'] },
                        list(filter(lambda other_pid: other_pid != player_uuid, room['player_uuids']))))

    def add_player(self, room_id, username, player_uuid):
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
            'isCurrentTurn': False,
            'currentState': 'NO_ACTION',
        }

        # Add uuid to list of active players
        room['player_uuids'].append(player_uuid)

        if not room['current_player_uuid']:
            room['current_player_uuid'] = player_uuid

    def point_to_next_player(self, room_id):
        room = self.get_room(room_id)
        current_player_uuid = room['current_player_uuid']

        room['player_by_uuid'][current_player_uuid]['isCurrentTurn'] = False
        room['player_by_uuid'][current_player_uuid]['current_state'] = 'NO_ACTION'

        current_player_idx = room['current_player_idx'] = (room['current_player_idx'] + 1) % 4
        current_player_uuid = room['current_player_uuid'] = room['player_uuids'][current_player_idx]

        room['player_by_uuid'][current_player_uuid]['isCurrentTurn'] = True
        room['player_by_uuid'][current_player_uuid]['current_state'] = 'DRAW_TILE'

        return current_player_uuid

