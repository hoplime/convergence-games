from collections.abc import Callable
from types import UnionType
from typing import (
    Any,
    ClassVar,
    Generic,
    Literal,
    LiteralString,
    Self,
    TypeAlias,
    TypeVar,
    get_args,
    overload,
)

from pydantic import BaseModel

from convergence_games.db.enums import Role
from convergence_games.db.models import Event, Game, User

OBJECT_T = TypeVar("OBJECT_T")
ACTION_T = TypeVar("ACTION_T", bound=str)
ALL: TypeAlias = Literal["all"]

type Scope[OBJECT_T] = tuple[Event | ALL, OBJECT_T | ALL]
type ActionPermission[OBJECT_T] = Callable[[User, OBJECT_T | ALL], bool] | bool


class BaseActionChecker(BaseModel, Generic[OBJECT_T, ACTION_T]):
    __valid_actions__: ClassVar[LiteralString | UnionType | None] = None

    @classmethod
    def all(cls) -> Self:
        model_fields = cls.model_fields
        return cls(**dict.fromkeys(model_fields, True))

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        super().__pydantic_init_subclass__(**kwargs)

        if not hasattr(cls, "__valid_actions__"):
            raise ValueError("The __valid_actions__ attribute must be defined")

        if cls.__valid_actions__ is None:
            return

        # We need to check that the list of defined permissions is exhaustive
        # for the given list of verbs allowed
        valid_actions: set[str] = set(get_args(cls.__valid_actions__))
        field_actions: set[str] = set(cls.model_fields.keys())
        if valid_actions != field_actions:
            raise ValueError(f"Invalid actions set: {field_actions}. Must be {valid_actions}")

    def check_action_permission(self, user: User, obj_value: OBJECT_T | ALL, action: ACTION_T) -> bool:
        p: ActionPermission[OBJECT_T] = getattr(self, action)
        if isinstance(p, bool):
            return p
        return p(user, obj_value)


USER_ACTIONS: TypeAlias = Literal["update", "delete"]


class UserActionChecker(BaseActionChecker[User, USER_ACTIONS]):
    __valid_actions__ = USER_ACTIONS

    update: ActionPermission[User] = False
    delete: ActionPermission[User] = False


GAME_ACTIONS: TypeAlias = Literal["update", "approve"]


class GameActionChecker(BaseActionChecker[Game, GAME_ACTIONS]):
    __valid_actions__ = GAME_ACTIONS

    update: ActionPermission[Game] = False
    approve: ActionPermission[Game] = False


EVENT_ACTIONS: TypeAlias = Literal["update", "delete", "manage_submissions"]


class EventActionChecker(BaseActionChecker[Event, EVENT_ACTIONS]):
    __valid_actions__ = EVENT_ACTIONS

    update: ActionPermission[Event] = False
    delete: ActionPermission[Event] = False
    manage_submissions: ActionPermission[Event] = False


class RolePermissionSet(BaseModel):
    user: UserActionChecker = UserActionChecker()
    game: GameActionChecker = GameActionChecker()
    event: EventActionChecker = EventActionChecker()


ROLE_PERMISSIONS: dict[Role | None, RolePermissionSet] = {
    Role.OWNER: RolePermissionSet(
        user=UserActionChecker.all(),
        game=GameActionChecker.all(),
        event=EventActionChecker.all(),
    ),
    Role.MANAGER: RolePermissionSet(
        user=UserActionChecker(
            update=False,
            delete=False,
        ),
        game=GameActionChecker(
            update=True,
            approve=True,
        ),
        event=EventActionChecker(
            update=False,
            delete=False,
            manage_submissions=True,
        ),
    ),
    None: RolePermissionSet(
        user=UserActionChecker(
            update=lambda u, user: user != "all" and u.id == user.id,
            delete=False,
        ),
        game=GameActionChecker(
            update=lambda u, game: game != "all" and u.id == game.gamemaster_id,
            approve=False,
        ),
        event=EventActionChecker(
            update=False,
            delete=False,
        ),
    ),
}


@overload
def user_has_permission(user: User, obj_type: Literal["user"], scope: Scope[User], action: USER_ACTIONS) -> bool: ...


@overload
def user_has_permission(user: User, obj_type: Literal["game"], scope: Scope[Game], action: GAME_ACTIONS) -> bool: ...


@overload
def user_has_permission(user: User, obj_type: Literal["event"], scope: Scope[Event], action: EVENT_ACTIONS) -> bool: ...


def user_has_permission(user: User, obj_type: LiteralString, scope: Scope, action: LiteralString) -> bool:
    event, obj_value = scope
    roles = [
        user_event_role.role
        for user_event_role in user.event_roles
        if (user_event_role.event_id is None) or (event != "all" and user_event_role.event_id == event.id)
    ] + [None]

    for role in roles:
        role_permissions = ROLE_PERMISSIONS.get(role)
        if role_permissions is None:
            continue
        action_checker: BaseActionChecker | None = getattr(role_permissions, obj_type)

        if action_checker is None:
            raise ValueError(f"Invalid object type: {obj_type}")
        if action_checker.check_action_permission(user, obj_value, action):
            return True

    return False
