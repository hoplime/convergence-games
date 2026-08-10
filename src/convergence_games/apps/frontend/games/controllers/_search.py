from litestar import Controller, get
from litestar.di import Provide
from litestar.exceptions import NotFoundException

from convergence_games.db.models import (
    ContentWarning,
    Genre,
    System,
)
from convergence_games.lib.ocean import Sqid, sink
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate, Template

from ..services import SearchService, provide_search_service


class SearchController(Controller):
    path = "/search"
    dependencies = {"search_service": Provide(provide_search_service)}

    @get(path="/{name:str}")
    async def get_search(self, name: str) -> Template:
        field_name = name.replace("-", "_")
        placeholders: dict[str, str] = {
            "system": "Search for a system...",
            "genre": "Search for genres...",
            "content_warning": "Search for content warnings...",
        }
        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchContainer.html.jinja",
            context={"name": field_name, "placholder": placeholders.get(field_name, "Search...")},
        )

    @get(path="/system/results")
    async def get_system_search_results(self, request: Request, search_service: SearchService, search: str) -> Template:
        results = await search_service.search_visible_to_user(System, search, request.user.id if request.user else None)

        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchResultsList.html.jinja",
            context={
                "name": "system",
                "results": results,
                "search": search,
                "mode": "select",
            },
        )

    @get(path="/system/select")
    async def get_system_search_selected(self, search_service: SearchService, sqid: Sqid) -> Template:
        system = await search_service.get_by_id(System, sink(sqid))

        if not system:
            raise NotFoundException(detail="System not found")

        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchSelected.html.jinja",
            context={
                "name": "system",
                "selected_name": system.name,
                "value": sqid,
            },
        )

    @get(path="/system/new")
    async def get_system_search_new(self, selected_name: str) -> Template:
        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchSelected.html.jinja",
            context={
                "name": "system",
                "selected_name": selected_name,
                "value": f"new:{selected_name}",
            },
        )

    @get(path="/genre/results")
    async def get_genre_search_results(self, request: Request, search_service: SearchService, search: str) -> Template:
        results = await search_service.search_visible_to_user(
            Genre, search, request.user.id if request.user else None, suggested_on_empty=True
        )

        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchResultsList.html.jinja",
            context={
                "name": "genre",
                "results": results,
                "search": search,
                "mode": "checks",
            },
        )

    @get(path="/genre/select")
    async def get_genre_search_selected(self, search_service: SearchService, sqid: Sqid) -> Template:
        genre = await search_service.get_by_id(Genre, sink(sqid))

        if not genre:
            raise NotFoundException(detail="Genre not found")

        return HTMXBlockTemplate(
            template_name="components/forms/search_checks/SearchCheckChip.html.jinja",
            context={
                "name": "genre",
                "selected_name": genre.name,
                "value": sqid,
            },
        )

    @get(path="/genre/new")
    async def get_genre_search_new(self, selected_name: str) -> Template:
        return HTMXBlockTemplate(
            template_name="components/forms/search_checks/SearchCheckChip.html.jinja",
            context={
                "name": "genre",
                "selected_name": selected_name,
                "value": f"new:{selected_name}",
            },
        )

    @get(path="/content-warning/results")
    async def get_content_warning_search_results(
        self, request: Request, search_service: SearchService, search: str
    ) -> Template:
        results = await search_service.search_visible_to_user(
            ContentWarning, search, request.user.id if request.user else None, suggested_on_empty=True
        )

        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchResultsList.html.jinja",
            context={
                "name": "content_warning",
                "results": results,
                "search": search,
                "mode": "checks",
            },
        )

    @get(path="/content-warning/select")
    async def get_content_warning_search_selected(self, search_service: SearchService, sqid: Sqid) -> Template:
        content_warning = await search_service.get_by_id(ContentWarning, sink(sqid))

        if not content_warning:
            raise NotFoundException(detail="Content warning not found")

        return HTMXBlockTemplate(
            template_name="components/forms/search_checks/SearchCheckChip.html.jinja",
            context={
                "name": "content_warning",
                "selected_name": content_warning.name,
                "value": sqid,
            },
        )

    @get(path="/content-warning/new")
    async def get_content_warning_search_new(self, selected_name: str) -> Template:
        return HTMXBlockTemplate(
            template_name="components/forms/search_checks/SearchCheckChip.html.jinja",
            context={
                "name": "content_warning",
                "selected_name": selected_name,
                "value": f"new:{selected_name}",
            },
        )
