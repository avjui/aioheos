from . import aioheosplayer


class AioHeosGroup(aioheosplayer.AioHeosPlayer):

    def __init__(self, controller,  group_json):
        group_json["pid"] = group_json["gid"]
        super().__init__(controller, group_json)
        print("Creating group object {} for controller pid {}",self._player_id,self._controller._player_id)