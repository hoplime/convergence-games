from typing import Annotated, Callable, Literal, cast

from litestar.datastructures import UploadFile
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from convergence_games.db.enums import (
    GameActivityRequirement,
    GameClassification,
    GameCoreActivity,
    GameCrunch,
    GameEquipmentRequirement,
    GameKSP,
    GameRoomRequirement,
    GameTableSizeRequirement,
    GameTone,
)
from convergence_games.lib.ocean import Sqid, sink


# region Submit Game Form
class NewValue[T](BaseModel):
    value: T


type SqidOrNew[T] = int | NewValue[T]


def make_sqid_or_new_validator[T](new_value_type: type[T]) -> Callable[[str], SqidOrNew[T]]:
    new_value_type_adapter = TypeAdapter(new_value_type)

    def sqid_or_new_validator(value: str) -> SqidOrNew[T]:
        if value.startswith("new:"):
            return NewValue(value=new_value_type_adapter.validate_python(value.removeprefix("new:")))
        return sink(cast(Sqid, value))

    return sqid_or_new_validator


NoneToEmpty = BeforeValidator(lambda value: "" if value is None else value)
MaybeListValidator = BeforeValidator(lambda value: value if isinstance(value, list) else [value])
IntFlagValidator = BeforeValidator(lambda value: sum(map(int, value)) if isinstance(value, list) else int(value))
SqidOrNewStr = Annotated[SqidOrNew[str], BeforeValidator(make_sqid_or_new_validator(str))]
SqidInt = Annotated[int, BeforeValidator(sink)]


class SubmitGameForm(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)  # Required for UploadFile

    # Stuff that's used for Game
    title: Annotated[str, Field(min_length=1, max_length=100, title="Title")]
    system: Annotated[SqidOrNewStr, Field(title="System")]
    tagline: Annotated[str, Field(min_length=10, max_length=140, title="Tagline"), NoneToEmpty] = ""
    description: Annotated[str, Field(title="Description"), NoneToEmpty] = ""

    image: Annotated[
        list[UploadFile | SqidInt], MaybeListValidator
    ] = []  # TODO: Or typeof existing image in the database

    genre: Annotated[list[SqidOrNewStr], MaybeListValidator, Field(title="Genres")]
    tone: Annotated[GameTone, Field(title="Tone")]
    content_warning: Annotated[list[SqidOrNewStr], MaybeListValidator, Field(title="Content Warnings")] = []
    crunch: Annotated[GameCrunch, Field(title="Complexity")]
    core_activity: Annotated[GameCoreActivity, IntFlagValidator, Field(title="Core Activities")] = GameCoreActivity.NONE
    player_count_minimum_more: int | None = None
    player_count_minimum: Annotated[int, Field(ge=1, title="Minimum Players")]
    player_count_optimum_more: int | None = None
    player_count_optimum: Annotated[int, Field(ge=1, title="Optimum Players")]
    player_count_maximum_more: int | None = None
    player_count_maximum: Annotated[int, Field(ge=1, title="Maximum Players")]
    classification: Annotated[GameClassification, Field(title="Age Suitability & Classification")]
    ksp: Annotated[GameKSP, IntFlagValidator, Field(title="Bonuses")] = GameKSP.NONE

    # Stuff that's used for GameRequirement
    times_to_run: Annotated[int, Field(title="Times to Run")] = 1
    available_time_slot: Annotated[list[SqidInt], MaybeListValidator, Field(title="Available Time Slots")]
    scheduling_notes: Annotated[str, Field(title="Scheduling Notes"), NoneToEmpty] = ""
    table_size_requirement: Annotated[
        GameTableSizeRequirement, IntFlagValidator, Field(title="Table Size Requirements")
    ] = GameTableSizeRequirement.NONE
    table_size_notes: Annotated[str, Field(title="Table Size Notes"), NoneToEmpty] = ""
    equipment_requirement: Annotated[
        GameEquipmentRequirement, IntFlagValidator, Field(title="Equipment Requirements")
    ] = GameEquipmentRequirement.NONE
    equipment_notes: Annotated[str, Field(title="Equiment Notes"), NoneToEmpty] = ""
    activity_requirement: Annotated[GameActivityRequirement, IntFlagValidator, Field(title="Activity Requirements")] = (
        GameActivityRequirement.NONE
    )
    activity_notes: Annotated[str, Field(title="Activity Notes"), NoneToEmpty] = ""
    room_requirement: Annotated[GameRoomRequirement, IntFlagValidator, Field(title="Room Requirements")] = (
        GameRoomRequirement.NONE
    )
    room_notes: Annotated[str, Field(title="Room Notes"), NoneToEmpty] = ""

    agree_to_code_of_conduct: Annotated[
        Literal["on"] | None, Field(title="Agree to Code of Conduct", validate_default=True)
    ] = None
    agree_to_use_safety_tools: Annotated[
        Literal["on"] | None, Field(title="Agree to Use Safety Tools", validate_default=True)
    ] = None
    agree_to_hygiene: Annotated[Literal["on"] | None, Field(title="Agree to Hygiene", validate_default=True)] = None
    no_content_warnings_needed: Annotated[
        Literal["on"] | None, Field(title="No Content Warnings Needed", validate_default=True)
    ] = None

    @property
    def player_count_minimum_prop(self) -> int:
        return max(self.player_count_minimum, self.player_count_minimum_more or 0)

    @property
    def player_count_optimum_prop(self) -> int:
        return max(self.player_count_optimum, self.player_count_optimum_more or 0)

    @property
    def player_count_maximum_prop(self) -> int:
        return max(self.player_count_maximum, self.player_count_maximum_more or 0)

    @field_validator("player_count_optimum", mode="after")
    @classmethod
    def validate_player_count_optimum(cls, value: int, info: ValidationInfo) -> int:
        minimum = max(info.data["player_count_minimum"], info.data["player_count_minimum_more"] or 0)
        optimum = max(value, info.data["player_count_optimum_more"] or 0)
        if optimum < minimum:
            raise PydanticCustomError("", "Optimum player count must be greater than or equal to minimum player count.")
        return value

    @field_validator("player_count_maximum", mode="after")
    @classmethod
    def validate_player_count_maximum(cls, value: int, info: ValidationInfo) -> int:
        optimum = max(info.data["player_count_optimum"], info.data["player_count_optimum_more"] or 0)
        maximum = max(value, info.data["player_count_maximum_more"] or 0)
        if maximum < optimum:
            raise PydanticCustomError("", "Maximum player count must be greater than or equal to optimum player count.")
        return value

    @field_validator("available_time_slot", mode="after")
    @classmethod
    def validate_enough_time_slots_selected(cls, value: list[SqidInt], info: ValidationInfo) -> list[SqidInt]:
        if len(value) < info.data["times_to_run"]:
            raise PydanticCustomError("", "You must select at least as many time slots as times to run.")
        return value

    @field_validator("agree_to_code_of_conduct", mode="after")
    @classmethod
    def validate_agree_to_code_of_conduct(cls, value: bool) -> bool:
        if not value:
            raise PydanticCustomError("", "You must agree to the Code of Conduct.")
        return value

    @field_validator("agree_to_use_safety_tools", mode="after")
    @classmethod
    def validate_agree_to_use_safety_tools(cls, value: bool) -> bool:
        if not value:
            raise PydanticCustomError("", "You must agree to use the X-Card and Open Table Policy.")
        return value

    @field_validator("agree_to_hygiene", mode="after")
    @classmethod
    def validate_agree_to_hygiene(cls, value: bool) -> bool:
        if not value:
            raise PydanticCustomError("", "You must agree to meet convention hygiene expectations.")
        return value

    @field_validator("no_content_warnings_needed", mode="after")
    @classmethod
    def validate_no_content_warnings_needed(
        cls, value: Literal["on"] | None, info: ValidationInfo
    ) -> Literal["on"] | None:
        content_warnings = info.data.get("content_warning", [])
        if not content_warnings and not value:
            raise PydanticCustomError(
                "",
                "You must either add at least one content warning or confirm that none are needed.",
            )
        return value


# endregion
