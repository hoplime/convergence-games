from dataclasses import dataclass

from litestar import Controller, get
from litestar.exceptions import NotFoundException
from rapidfuzz import fuzz, process, utils
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import ColumnExpressionArgument

from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.enums import (
    SubmissionStatus,
)
from convergence_games.db.models import (
    ContentWarning,
    Genre,
    System,
)
from convergence_games.db.ocean import Sqid, sink

type SearchableBase = System | Genre | ContentWarning


@dataclass
class SearchResult[T: SearchableBase]:
    name: str
    match: str
    score: float
    result: T


async def search_with_fuzzy_match[T: SearchableBase](
    transaction: AsyncSession,
    model_type: type[T],
    search: str,
    extra_filters: ColumnExpressionArgument[bool] | None = None,
    suggested_on_empty: bool = False,
) -> list[SearchResult[T]]:
    # TODO: Can we directly query for the names (possibly including aliases) and sqids?
    query = select(model_type)

    if issubclass(model_type, System):
        query = query.options(selectinload(model_type.aliases))

    if extra_filters is not None:
        query = query.where(extra_filters)

    if not search:
        if suggested_on_empty:
            assert issubclass(model_type, Genre) or issubclass(model_type, ContentWarning)
            query = query.where(model_type.suggested).order_by(model_type.name)
            all_rows = (await transaction.execute(query)).scalars().all()
            return [
                SearchResult(
                    name=row.name,
                    match=row.name,
                    score=100,
                    result=row,
                )
                for row in all_rows
            ]
        else:
            return []

    all_rows = (await transaction.execute(query)).scalars().all()

    to_match: list[tuple[str, T]] = []
    for row in all_rows:
        to_match.append((row.name, row))
        if isinstance(row, System):
            for alias in row.aliases:
                to_match.append((alias.name, row))

    names_scores_indices = process.extract(
        query=search,
        choices=[name for name, _ in to_match],
        scorer=fuzz.WRatio,
        processor=utils.default_process,
        limit=10,
        score_cutoff=50,
    )

    already_matched_ids: set[int] = set()
    top_results: list[SearchResult[T]] = []

    for _, score, index in names_scores_indices:
        result = to_match[index][1]
        if result.id not in already_matched_ids:
            top_results.append(
                SearchResult(
                    name=result.name,
                    match=to_match[index][0],
                    score=score,
                    result=result,
                )
            )
            already_matched_ids.add(result.id)

    return top_results


class SearchController(Controller):
    path = "/search"

    @get(path="/{name:str}")
    async def get_search(self, name: str) -> Template:
        placeholders: dict[str, str] = {
            "system": "Search for a system...",
            "genre": "Search for genres...",
            "content_warning": "Search for content warnings...",
        }
        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchContainer.html.jinja",
            context={"name": name, "placholder": placeholders.get(name, "Search...")},
        )

    @get(path="/system/results")
    async def get_system_search_results(self, request: Request, transaction: AsyncSession, search: str) -> Template:
        extra_filters = System.submission_status == SubmissionStatus.APPROVED
        if request.user:
            extra_filters = extra_filters | (System.created_by == request.user.id)
        results = await search_with_fuzzy_match(transaction, System, search, extra_filters)

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
    async def get_system_search_selected(self, transaction: AsyncSession, sqid: Sqid) -> Template:
        system = await transaction.get(System, sink(sqid))

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
    async def get_genre_search_results(self, request: Request, transaction: AsyncSession, search: str) -> Template:
        extra_filters = Genre.submission_status == SubmissionStatus.APPROVED
        if request.user:
            extra_filters = extra_filters | (Genre.created_by == request.user.id)
        results = await search_with_fuzzy_match(transaction, Genre, search, extra_filters, suggested_on_empty=True)

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
    async def get_genre_search_selected(self, transaction: AsyncSession, sqid: Sqid) -> Template:
        genre = await transaction.get(Genre, sink(sqid))

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

    @get(path="/content_warning/results")
    async def get_content_warning_search_results(
        self, request: Request, transaction: AsyncSession, search: str
    ) -> Template:
        extra_filters = ContentWarning.submission_status == SubmissionStatus.APPROVED
        if request.user:
            extra_filters = extra_filters | (ContentWarning.created_by == request.user.id)
        results = await search_with_fuzzy_match(
            transaction, ContentWarning, search, extra_filters, suggested_on_empty=True
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

    @get(path="/content_warning/select")
    async def get_content_warning_search_selected(self, transaction: AsyncSession, sqid: Sqid) -> Template:
        content_warning = await transaction.get(ContentWarning, sink(sqid))

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

    @get(path="/content_warning/new")
    async def get_content_warning_search_new(self, selected_name: str) -> Template:
        return HTMXBlockTemplate(
            template_name="components/forms/search_checks/SearchCheckChip.html.jinja",
            context={
                "name": "content_warning",
                "selected_name": selected_name,
                "value": f"new:{selected_name}",
            },
        )
