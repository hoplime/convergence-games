from dataclasses import dataclass

from rapidfuzz import fuzz, process, utils
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import ColumnExpressionArgument

from convergence_games.db.enums import SubmissionStatus
from convergence_games.db.models import (
    ContentWarning,
    Genre,
    System,
)

type SearchableBase = System | Genre | ContentWarning


@dataclass
class SearchResult[T: SearchableBase]:
    name: str
    match: str
    score: float
    result: T


class SearchService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def fuzzy_search[T: SearchableBase](
        self,
        model_type: type[T],
        search: str,
        extra_filters: ColumnExpressionArgument[bool] | None = None,
        *,
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
                all_rows = (await self._session.execute(query)).scalars().all()
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

        all_rows = (await self._session.execute(query)).scalars().all()

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

    async def search_visible_to_user[T: SearchableBase](
        self,
        model_type: type[T],
        search: str,
        user_id: int | None,
        *,
        suggested_on_empty: bool = False,
    ) -> list[SearchResult[T]]:
        extra_filters = model_type.submission_status == SubmissionStatus.APPROVED
        if user_id is not None:
            extra_filters = extra_filters | (model_type.created_by == user_id)
        return await self.fuzzy_search(model_type, search, extra_filters, suggested_on_empty=suggested_on_empty)

    async def get_by_id[T: SearchableBase](self, model_type: type[T], id_: int) -> T | None:
        return await self._session.get(model_type, id_)


async def provide_search_service(transaction: AsyncSession) -> SearchService:
    return SearchService(transaction)
