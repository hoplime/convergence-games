from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import UnionType
from typing import (
    Any,
    ClassVar,
    Generic,
    Literal,
    LiteralString,
    Protocol,
    Self,
    TypeAlias,
    TypedDict,
    TypeVar,
    get_args,
    get_origin,
    overload,
)

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Role(Enum):
    ADMIN = "admin"
    USER = "user"


@dataclass
class User:
    id: int
    roles: list[Role]


@dataclass
class Game:
    id: int


@dataclass
class Group:
    id: int


@dataclass
class Event:
    id: int


OBJECT_T = TypeVar("OBJECT_T")
ACTION_T = TypeVar("ACTION_T", bound=str)

type ActionPermission[OBJECT_T] = Callable[[User, OBJECT_T | None], bool] | bool


class BaseActionChecker(BaseModel, Generic[OBJECT_T, ACTION_T]):
    __valid_actions__: ClassVar[UnionType | None] = None

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

    def check(self, user: User, obj: OBJECT_T | None, action: ACTION_T) -> bool:
        p: ActionPermission[OBJECT_T] = getattr(self, action)
        if isinstance(p, bool):
            return p
        return p(user, obj)


USER_ACTIONS: TypeAlias = Literal["create", "read", "update", "delete"]


class UserActionChecker(BaseActionChecker[User, USER_ACTIONS]):
    __valid_actions__ = USER_ACTIONS

    create: ActionPermission[User] = False
    read: ActionPermission[User] = False
    update: ActionPermission[User] = False
    delete: ActionPermission[User] = False


GAME_ACTIONS: TypeAlias = Literal["create", "read", "update", "delete"]


class GameActionChecker(BaseActionChecker[Game, GAME_ACTIONS]):
    __valid_actions__ = GAME_ACTIONS

    create: ActionPermission[Game] = False
    read: ActionPermission[Game] = False
    update: ActionPermission[Game] = False
    delete: ActionPermission[Game] = False


GROUP_ACTIONS: TypeAlias = Literal["create", "read", "update", "delete"]


class GroupActionChecker(BaseActionChecker[Group, GROUP_ACTIONS]):
    __valid_actions__ = GROUP_ACTIONS

    create: ActionPermission[Group] = False
    read: ActionPermission[Group] = False
    update: ActionPermission[Group] = False
    delete: ActionPermission[Group] = False


EVENT_ACTIONS: TypeAlias = Literal["create", "read", "update", "delete"]


class EventActionChecker(BaseActionChecker[Event, EVENT_ACTIONS]):
    __valid_actions__ = EVENT_ACTIONS

    create: ActionPermission[Event] = False
    read: ActionPermission[Event] = False
    update: ActionPermission[Event] = False
    delete: ActionPermission[Event] = False


class RolePermissionSet(BaseModel):
    user: UserActionChecker = UserActionChecker()
    game: GameActionChecker = GameActionChecker()
    group: GroupActionChecker = GroupActionChecker()
    event: EventActionChecker = EventActionChecker()


ROLE_PERMISSIONS: dict[Role, RolePermissionSet] = {
    Role.ADMIN: RolePermissionSet(
        user=UserActionChecker(
            create=True,
            read=True,
            update=True,
            delete=True,
        ),
    ),
    Role.USER: RolePermissionSet(
        user=UserActionChecker(
            create=False,
            read=True,
            update=lambda user, obj: obj is not None and user.id == obj.id,
            delete=False,
        ),
    ),
}


@overload
def user_has_permission(user: User, obj_type: Literal["user"], obj_value: User, action: USER_ACTIONS) -> bool: ...


@overload
def user_has_permission(user: User, obj_type: Literal["game"], obj_value: Game, action: GAME_ACTIONS) -> bool: ...


@overload
def user_has_permission(user: User, obj_type: Literal["group"], obj_value: Group, action: GROUP_ACTIONS) -> bool: ...


@overload
def user_has_permission(user: User, obj_type: Literal["event"], obj_value: Event, action: EVENT_ACTIONS) -> bool: ...


def user_has_permission(
    user: User, obj_type: LiteralString, obj_value: User | Game | Group | Event, action: LiteralString
) -> bool:
    user_roles = user.roles
    for role in user_roles:
        role_permissions = ROLE_PERMISSIONS.get(role)
        if role_permissions is None:
            continue
        obj_permissions: BaseActionChecker | None = getattr(role_permissions, obj_type)
        if obj_permissions is None:
            raise ValueError(f"Invalid object type: {obj_type}")
        return obj_permissions.check(user, obj_value, action)
    return False


if __name__ == "__main__":
    admin_user = User(1, [Role.ADMIN])
    user_user = User(2, [Role.USER])

    print(f"{user_has_permission(admin_user, "user", admin_user, "update")=}")
    print(f"{user_has_permission(admin_user, "user", user_user, "update")=}")
    print(f"{user_has_permission(user_user, "user", user_user, "update")=}")
    print(f"{user_has_permission(user_user, "user", admin_user, "update")=}")
