from litestar import Controller, get

from convergence_games.db.ocean import Sqid


class EventProfileController(Controller):
    path = "/event/{event_sqid:str}/profile"

    @get(path="/")
    async def get_my_event_profile(self, event_sqid: Sqid) -> str:
        return f"My Event Profile Page for event {event_sqid}"
