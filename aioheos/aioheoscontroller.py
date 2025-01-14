#!/usr/bin/env python3
""" Heos python lib """

import asyncio
import json
import logging
import sys
from concurrent.futures import CancelledError

from . import aioheosgroup
from . import aioheosplayer
from . import aioheosupnp

_LOGGER = logging.getLogger(__name__)

HEOS_PORT = 1255

GET_PLAYERS = 'player/get_players'
GET_PLAYER_INFO = 'player/get_player_info'
GET_PLAY_STATE = 'player/get_play_state'
SET_PLAY_STATE = 'player/set_play_state'
GET_MUTE_STATE = 'player/get_mute'
SET_MUTE_STATE = 'player/set_mute'
GET_VOLUME = 'player/get_volume'
SET_VOLUME = 'player/set_volume'
GET_NOW_PLAYING_MEDIA = 'player/get_now_playing_media'
GET_QUEUE = 'player/get_queue'
CLEAR_QUEUE = 'player/clear_queue'
PLAY_NEXT = 'player/play_next'
PLAY_PREVIOUS = 'player/play_previous'
PLAY_QUEUE = 'player/play_queue'
TOGGLE_MUTE = 'player/toggle_mute'

GET_GROUPS = 'group/get_groups'
SET_GROUP = 'group/set_group'

BROWSE = 'browser/browse'

EVENT_PLAYER_VOLUME_CHANGED = 'event/player_volume_changed'
EVENT_PLAYER_STATE_CHANGED = 'event/player_state_changed'
EVENT_PLAYERS_CHANGED = 'event/players_changed'
EVENT_PLAYER_NOW_PLAYING_CHANGED = 'event/player_now_playing_changed'
EVENT_PLAYER_NOW_PLAYING_PROGRESS = 'event/player_now_playing_progress'
EVENT_PLAYER_QUEUE_CHANGED = 'event/player_queue_changed'

EVENT_USER_CHANGED = 'event/user_changed'
EVENT_SOURCES_CHANGED = 'event/sources_changed'
EVENT_GROUPS_CHANGED = 'event/groups_changed'
EVENT_GROUP_VOLUME_CHANGED = 'event/group_volume_changed'
EVENT_REPEAT_MODE_CHANGED = "event/repeat_mode_changed"
EVENT_SHUTTLE_MODE_CHANGED = "event/shuffle_mode_changed"

SYSTEM_PRETTIFY = 'system/prettify_json_response'
SYSTEM_REGISTER_FOR_EVENTS = 'system/register_for_change_events'
SYSTEM_SIGNIN = 'system/sign_in'
SYSTEM_SIGNOUT = 'system/sign_out'

BROWSE_MUSIC_SOURCES = 'browse/get_music_sources'
BROWSE_SEARCH = 'browse/search'
BROWSE_BROWSE = 'browse/browse'
BROWSE_SEARCH_CRITERIA = 'browse/get_search_criteria'
BROWSE_PLAY_STREAM = 'browse/play_stream'

SOURCE_LIST = {
    1: "Pandora",
    2: "Rhapsody",
    3: "TuneIn",
    4: "Spotify",
    5: "Deezer",
    6: "Napster",
    7: "iHeartRadio",
    8: "Sirius XM",
    9: "Soundcloud",
    10: "Tidal",
    11: "Future service",
    13: "Amazon Music",
    14: "Future service",
    15: "Moodmix",
    17: "Future service",
    18: "QQMusic"
}


class AioHeosException(Exception):
    """ AioHeosException class """

    # pylint: disable=super-init-not-called
    def __init__(self, message):
        self.message = message


class AioHeosController(object):  # pylint: disable=too-many-public-methods,too-many-instance-attributes
    """ Asynchronous Heos class """

    def __init__(self, loop, host=None, username=None, password=None, verbose=False, new_device_callback=None):
        self._host = host
        self._loop = loop
        self._username = username
        self._pwd = password
        self._need_login = self._username is not None
        self._new_device_callback = new_device_callback
        self._players = None
        self._groups = None

        self._verbose = verbose
        self._player_id = None
        self._upnp = aioheosupnp.AioHeosUpnp(loop=loop, verbose=verbose)
        self._reader = None
        self._writer = None
        self._subscribtion_task = None

        self._favourites = []
        self._favourites_sid = None
        self._music_sources = None

    @asyncio.coroutine
    def ensure_player(self):
        """ ensure player """
        # timeout after 10 sec
        self.request_players()
        for _ in range(0, 20):
            if self.player_id is None:
                yield from asyncio.sleep(0.5)
            else:
                return

    @asyncio.coroutine
    def ensure_group(self):
        """ ensure player """
        # timeout after 10 sec
        self.request_groups()
        for _ in range(0, 20):
            if self._groups is None:
                yield from asyncio.sleep(0.5)
            else:
                return

    @asyncio.coroutine
    def ensure_login(self):
        """ ensure login """
        # timeout after 20 sec
        self.login()
        for _ in range(0, 20):
            if self._need_login:
                yield from asyncio.sleep(0.5)
            else:
                return

    @asyncio.coroutine
    def ensure_favourites_loaded(self):
        """ ensure favourites loaded """
        # timeout after 20 sec
        for _ in range(0, 20):
            if self._favourites is None:
                yield from asyncio.sleep(0.5)
            else:
                return

    @staticmethod
    def _url_to_addr(url):
        import re
        addr = re.search('https?://([^:/]+)[:/].*$', url)
        if addr:
            return addr.group(1)
        else:
            return None

    @asyncio.coroutine
    def connect(self, host=None, port=HEOS_PORT, callback=None):
        """ setup proper connection """
        if host is not None:
            self._host = host

        # discover
        if not self._host:
            url = yield from self._upnp.discover()
            self._host = self._url_to_addr(url)

        # connect
        if self._verbose:
            _LOGGER.debug('[I] Connecting to {}:{}'.format(self._host, port))
        yield from self._connect(self._host, port)

        # please, do not prettify json
        self.register_pretty_json(False)
        # and get events
        self.register_for_change_events()

        # setup subscription loop
        if self._subscribtion_task is None:
            self._subscribtion_task = self._loop.create_task(
                self._async_subscribe(callback))
        # request for players
        yield from self.ensure_player()
        yield from self.ensure_group()
        if self._need_login:
            yield from self.ensure_login()
            self.request_music_sources()

    @asyncio.coroutine
    def _connect(self, host, port=HEOS_PORT):
        """ connect """
        while True:
            try:
                # pylint: disable=line-too-long
                self._reader, self._writer = yield from asyncio.open_connection(host, port, loop=self._loop)
                return
            except TimeoutError:
                _LOGGER.exception('[E] Connection timed out, will try {}:{} again...'.format(self._host, port))
            except Exception:  # pylint: disable=bare-except
                _LOGGER.exception('[E] %s', sys.exc_info()[0])

            yield from asyncio.sleep(5.0)

    def send_command(self, command, message=None):
        """ send command """
        msg = 'heos://' + command
        if message:
            if 'pid' in message.keys() and message['pid'] is None:
                message['pid'] = self.player_id
            msg += '?' + '&'.join("{}={}".format(key, val) for (key, val) in message.items())
        msg += '\r\n'
        if self._verbose:
            _LOGGER.debug(msg)
        self._writer.write(msg.encode('ascii'))

    @staticmethod
    def _parse_message(message):
        """ parse message """
        if message != None and len(message) > 0:
            result = {}
            for elem in message.split('&'):
                _LOGGER.debug("_parse_message Elem: %s %s", elem, elem.split('='))
                parts = elem.split('=')
                if len(parts) == 2:
                    result[parts[0]] = parts[1]
                elif len(parts) == 1:
                    result[parts[0]] = True
                else:
                    _LOGGER.warning("No parts found in {}".format(message))
            return result
        else:
            return {}

    def _handle_error(self, message):
        eid = message['eid']
        if eid == "2":
            pid = message['pid']
            player = self.get_player(pid)
            player.play_state = None
            raise AioHeosException("Player {} is offline".format(pid))
        else:
            raise AioHeosException(message)

    def _dispatcher(self, command, message, payload):
        """ call parser functions """
        # if self._verbose:
        if self._verbose:
            _LOGGER.debug('DISPATCHER')
            _LOGGER.debug("%s %s %s", command, message, payload)
        callbacks = {
            GET_PLAYERS: self._parse_players,
            GET_GROUPS: self._parse_groups,
            SET_GROUP: self._parse_set_group,
            GET_PLAY_STATE: self._parse_play_state,
            SET_PLAY_STATE: self._parse_play_state,
            GET_MUTE_STATE: self._parse_mute_state,
            SET_MUTE_STATE: self._parse_mute_state,
            GET_VOLUME: self._parse_volume,
            SET_VOLUME: self._parse_volume,
            GET_NOW_PLAYING_MEDIA: self._parse_now_playing_media,
            EVENT_PLAYER_VOLUME_CHANGED: self._parse_player_volume_changed,
            EVENT_GROUP_VOLUME_CHANGED: self._parse_group_volume_changed,
            EVENT_PLAYER_STATE_CHANGED: self._parse_player_state_changed,
            EVENT_PLAYERS_CHANGED: self._parse_players_changed,
            EVENT_PLAYER_NOW_PLAYING_CHANGED: self._parse_player_now_playing_changed,
            EVENT_PLAYER_NOW_PLAYING_PROGRESS: self._parse_player_now_playing_progress,
            EVENT_GROUPS_CHANGED: self._parse_groups_changed,
            SYSTEM_SIGNIN: self._parse_system_signin,
            BROWSE_MUSIC_SOURCES: self._parse_browse_music_source,
            BROWSE_BROWSE: self._parse_browse_browse,
        }
        commands_ignored = (
            SYSTEM_PRETTIFY,
            SYSTEM_REGISTER_FOR_EVENTS,
            EVENT_PLAYER_QUEUE_CHANGED,
            EVENT_SOURCES_CHANGED,
            EVENT_USER_CHANGED,
            EVENT_SHUTTLE_MODE_CHANGED,
            EVENT_REPEAT_MODE_CHANGED
        )
        if command in callbacks.keys():
            callbacks[command](payload, message)
        elif command in commands_ignored:
            if self._verbose:
                _LOGGER.debug('[I] command "{}" is ignored.'.format(command))
        else:
            _LOGGER.warning('[W] command "{}" is not handled.'.format(command))

    def _parse_command(self, data):
        """ parse command """
        try:
            data_heos = data['heos']
            command = data_heos['command']
            message = {}
            if 'message' in data_heos:
                if data_heos['message'].startswith('command under process'):
                    return None
                message = self._parse_message(data_heos['message'])
            if 'result' in data_heos.keys() and data_heos['result'] == 'fail':
                self._handle_error(message)
            if 'payload' in data.keys():
                self._dispatcher(command, message, data['payload'])
            elif 'message' in data_heos.keys():
                self._dispatcher(command, message, None)
            elif 'command' in data_heos.keys():
                self._dispatcher(command, None, None)
            else:
                raise AioHeosException('No message or payload in reply. payload {}'.format(data))
        # pylint: disable=bare-except
        except AioHeosException as exc:
            raise exc
        except Exception:
            _LOGGER.exception("Unexpected error for msg '%s'", data)
            raise AioHeosException('Problem parsing command.')

        return None

    @asyncio.coroutine
    def _callback_wrapper(self, callback):  # pylint: disable=no-self-use
        if callback:
            try:
                yield from callback()
            except Exception:  # pylint: disable=bare-except
                pass

    @asyncio.coroutine
    def _async_subscribe(self, callback=None):  # pylint: disable=too-many-branches
        """ event loop """
        while True:
            if self._reader is None:
                yield from asyncio.sleep(0.1)
                continue
            msg = ""
            try:
                msg = yield from self._reader.readline()
            except TimeoutError:
                _LOGGER.exception('[E] Connection got timed out, try to reconnect...')
                yield from self._connect(self._host)
            except ConnectionResetError:
                _LOGGER.exception('[E] Peer reset our connection, try to reconnect...')
                yield from self._connect(self._host)
            except (GeneratorExit, CancelledError):
                print('[I] Cancelling event loop...')
                return
            except Exception:  # pylint: disable=bare-except
                _LOGGER.exception('[E] Ignoring %s', sys.exc_info()[0])
            if msg:
                if self._verbose:
                    _LOGGER.debug(msg.decode())
                # simplejson doesnt need to decode from byte to ascii
                data = json.loads(msg.decode())
                if self._verbose:
                    _LOGGER.debug('DATA:')
                    _LOGGER.debug(data)
                try:
                    self._parse_command(data)
                except AioHeosException as exc:
                    _LOGGER.exception('[E] Failed in parse excepton')
                    if self._verbose:
                        _LOGGER.debug('MSG %s', msg)
                        _LOGGER.debug('MSG decoded %s', msg.decode())
                        _LOGGER.debug('MSG json %s', data)
                    continue
            if callback:
                if self._verbose:
                    _LOGGER.debug('TRIGGER CALLBACK')
                self._loop.create_task(self._callback_wrapper(callback))

    def new_device_callback(self, callback):
        self._new_device_callback = callback

    def close(self):
        """ close """
        _LOGGER.info('[I] Closing down...')
        if self._subscribtion_task:
            self._subscribtion_task.cancel()

    def register_for_change_events(self):
        """ register for change events """
        self.send_command(SYSTEM_REGISTER_FOR_EVENTS, {'enable': 'on'})

    def register_pretty_json(self, enable=False):
        """ register for pretty json """
        set_enable = 'off'
        if enable is True:
            set_enable = 'on'
        self.send_command(SYSTEM_PRETTIFY, {'enable': set_enable})

    def request_players(self):
        """ get players """
        self.send_command(GET_PLAYERS)

    def login(self):
        """ login """
        self.send_command(SYSTEM_SIGNIN, {'un': self._username, 'pw': self._pwd})

    def _parse_players(self, payload, message):
        self._players_json = payload
        self._player_id = self._players_json[0]['pid']
        if self._players is None:
            self._players = []

        for player in self._players_json:
            old_player = self.get_player(player['pid'])
            if old_player is None:
                new_player = aioheosplayer.AioHeosPlayer(self, player)
                self._players.append(new_player)
                if self._new_device_callback is not None:
                    self._new_device_callback(new_player)
            else:
                old_player.player_info = player

    def _parse_groups(self, payload, message):
        self._groups_json = payload

        if self._groups is None:
            self._groups = []

        group_copy = self._groups
        for group in self._groups_json:
            old_group = self.get_group(group['gid'])
            if old_group is None:
                new_group = aioheosgroup.AioHeosGroup(self, group)
                self._groups.append(new_group)
                if self._new_device_callback is not None:
                    self._new_device_callback(new_group)
            else:
                old_group.player_info = group
                group_copy.remove(group)

        for remove_group in group_copy:
            # Make group offline
            remove_group.play_state = None

    def _parse_set_group(self, payload, message):
        self.request_groups()

    def _parse_system_signin(self, payload, message):
        self._need_login = False

    def get_players(self):
        """ get players array """
        return self._players

    def get_groups(self):
        """ get groups array """
        return self._groups

    def get_player(self, pid):
        """ get player from array """
        for player in self._players:
            _LOGGER.debug(
                "Compare player and pids %s %s %s %s", player.player_id, pid, type(player.player_id), type(pid))
            if player.player_id == pid:
                return player

    def get_group(self, pid):
        """ get group from array """
        for group in self._groups:
            if group.player_id == pid:
                return group

    @property
    def player_id(self):
        """ get player id """
        return self._player_id

    def request_player_info(self, pid):
        """ request player info """
        self.send_command(GET_PLAYER_INFO, {'pid': pid})

    def request_play_state(self, pid):
        """ request play state """
        self.send_command(GET_PLAY_STATE, {'pid': pid})

    def _parse_play_state(self, payload, message):
        self.get_player(message['pid']).play_state = message['state']
        if self.get_group(message['pid']) is not None:
            self.get_group(message['pid']).play_state = message['state']

    def request_mute_state(self, pid):
        """ request mute state """
        self.send_command(GET_MUTE_STATE, {'pid': pid})

    def _parse_mute_state(self, payload, message):
        self._mute_state = message['state']

    def request_volume(self, pid):
        """ request volume """
        self.send_command(GET_VOLUME, {'pid': pid})

    def set_volume(self, volume_level, pid):
        """ set volume """
        if volume_level > 100:
            volume_level = 100
        if volume_level < 0:
            volume_level = 0
        self.send_command(SET_VOLUME, {'pid': pid,
                                       'level': volume_level})

    def _parse_volume(self, payload, message):
        self.get_player(message['pid']).volume = float(message['level'])
        if self.get_group(message['pid']) is not None:
            self.get_group(message['pid']).volume = float(message['level'])

    def _set_play_state(self, state, pid=None):
        """ set play state """
        if state not in ('play', 'pause', 'stop'):
            AioHeosException('Not an accepted play state {}.'.format(state))

        self.send_command(SET_PLAY_STATE, {'pid': pid if (pid is not None) else self.player_id,
                                           'state': state})

    def stop(self, pid=None):
        """ stop player """
        self._set_play_state('stop', pid)

    def play(self, pid=None):
        """ play """
        self._set_play_state('play', pid)

    def pause(self, pid=None):
        """ pause """
        self._set_play_state('pause', pid)

    def request_now_playing_media(self, pid=None):
        """ get playing media """
        self.send_command(GET_NOW_PLAYING_MEDIA, {'pid': pid if (pid is not None) else self.player_id})

    def _parse_now_playing_media(self, payload, message):
        player = self.get_player(message["pid"])
        player.reset_now_playing()
        if 'artist' in payload.keys():
            player.media_artist = payload['artist']
        if 'album' in payload.keys():
            player.media_album = payload['album']
        if 'song' in payload.keys():
            player.media_title = payload['song']
        if 'image_url' in payload.keys():
            player.media_image_url = payload['image_url']
        if 'mid' in payload.keys():
            player.media_id = payload['mid']
        if 'sid' in payload.keys():
            player._sid = payload['sid']
            if self._music_sources is not None:
                source_obj = self._music_sources.get(player._sid, {'name': 'unknown'})
                _LOGGER.debug("SOURCE %s", source_obj)
                player._source_name = source_obj['name']
        if 'qid' in payload.keys():
            player._qid = payload['qid']
        if self._verbose:
            _LOGGER.debug("_parse_now_playing_media %s", vars(player))

    def get_favourites(self):
        """ get duration """
        return self._favourites

    def request_queue(self, pid):
        """ request queue """
        self.send_command(GET_QUEUE, {'pid': pid})

    def clear_queue(self, pid):
        """ clear queue """
        self.send_command(CLEAR_QUEUE, {'pid': pid})

    def request_play_next(self, pid):
        """ play next """
        self.send_command(PLAY_NEXT, {'pid': pid})

    def _parse_play_next(self, payload, message):
        """ parse play next """
        pass

    def request_play_previous(self, pid):
        """ play prev """
        self.send_command(PLAY_PREVIOUS, {'pid': pid})

    def play_queue(self, pid, qid):
        """ play queue """
        self.send_command(PLAY_QUEUE, {'pid': pid,
                                       'qid': qid})

    def play_stream(self, pid, sid, mid):
        """ play play_stream """
        self.send_command(BROWSE_PLAY_STREAM, {'pid': pid,
                                               'mid': mid,
                                               'sid': sid})

    def play_favourite(self, pid, mid):
        """ play play_favourite """
        self.send_command(BROWSE_PLAY_STREAM, {'pid': pid,
                                               'mid': mid,
                                               'sid': self._favourites_sid})

    def request_groups(self):
        """ get groups """
        self.send_command(GET_GROUPS)

    def set_group(self, leader_pid, member_pids):
        """ set group """
        list = str(leader_pid)
        for member in member_pids:
            list = list + "," + str(member)
        self.send_command(SET_GROUP, {'pid': list})

    def toggle_mute(self, pid):
        """ toggle mute """
        self.send_command(TOGGLE_MUTE, {'pid': pid})

    def set_mute(self, pid, mute):
        """ set mute """
        self.send_command(SET_MUTE_STATE, {'pid': pid, 'state': 'on' if mute else 'off'})

    def request_music_sources(self):
        """ get music sources """
        self.send_command(BROWSE_MUSIC_SOURCES, {'range': '0,29'})

    def request_browse_source(self, sid):
        """ browse source """
        self.send_command(BROWSE, {'sid': sid, 'range': '0,29'})

    def play_content(self, content, content_type='audio/mpeg'):
        """ play content """
        self._loop.create_task(self._upnp.play_content(content, content_type))
        # asyncio.wait([task])

    def _parse_player_volume_changed(self, payload, message):
        player = self.get_player(message["pid"])
        player.mute = message['mute']
        player.volume = float(message['level'])

    def _parse_group_volume_changed(self, payload, message):
        group = self.get_group(message["gid"])
        if group is not None:
            group.mute = message['mute']
            group.volume = float(message['level'])

    def _parse_player_state_changed(self, payload, message):
        player = self.get_player(message["pid"])
        player.play_state = message['state']
        group = self.get_group(message["pid"])
        if group is not None:
            group.play_state = message['state']

    def _parse_groups_changed(self, payload, message):
        self.request_groups()

    def _parse_players_changed(self, payload, message):
        self.request_players()

    def _parse_player_now_playing_changed(self, payload, message):  # pylint: disable=invalid-name
        """ event / now playing changed, request what changed. """
        self.request_now_playing_media()

    def _parse_player_now_playing_progress(self, payload, message):  # pylint: disable=invalid-name
        player = self.get_player(message["pid"])
        player.current_position = int(message['cur_pos'])
        player.duration = int(message['duration'])

    def _parse_browse_music_source(self, payload, message):  # pylint: disable=invalid-name
        _LOGGER.debug("_parse_browse_music_source {}".format(payload))
        self._music_sources = {}

        for source in payload:
            self._music_sources[source['sid']] = source
            _LOGGER.debug("Source: %s", source)
            if source['name'] == 'TuneIn':
                _LOGGER.debug("TuneIn %s", source)
            elif source['name'] == 'Favorites':
                _LOGGER.debug("Favorites %s", source)
                self._favourites_sid = source['sid']
                self.send_command(BROWSE_BROWSE, {"sid": source['sid']})

    def _parse_browse_browse(self, payload, message):  # pylint: disable=invalid-name
        _LOGGER.debug("BROWSE_BROWSE fav sid <{}>, input sid <{}>".format(self._favourites_sid, message['sid']))
        if str(message['sid']) == str(self._favourites_sid):
            _LOGGER.debug("Favorites: %s", payload)
            self._favourites = payload

    def get_music_sources(self):
        source_names = []
        for source in self._music_sources.values():
            source_names.append(source['name'])
        for source in self._favourites:
            source_names.append("Favorites__" + source['name'])

        return source_names
