from . import aioheosplayer


class AioHeosGroup(aioheosplayer.AioHeosPlayer):

    def __init__(self, controller,  group_json):
        group_json["pid"] = group_json["gid"]
        super().__init__(controller, group_json)
        print("Creating group object {} for controller pid {}",self._player_id,self._controller._player_id)

    def recreate_group(self):
        member_ids = []
        for player in self._player_info["players"]:
            if str(player["pid"]) != str(self.player_id):
                member_ids.append(player["pid"])
        self._controller.set_group(self.player_id, member_ids)
