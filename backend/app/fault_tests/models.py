"""Bounded hypothetical fault inputs; no changes to the optimizer request schema."""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class ChoppedImpulse(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    test_type: Literal['chopped_impulse']
    chop_mode: Literal['front', 'tail']
    chop_time_us: float = Field(gt=0, le=100000)
    shunt_r_ohm: float = Field(ge=0.5, le=10000)
    shunt_l_uh: float = Field(ge=0, le=10000)
    title: str = Field(default='', max_length=120)

    @field_validator('chop_time_us', 'shunt_r_ohm', 'shunt_l_uh', mode='before')
    @classmethod
    def numeric_input(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('Fault values must be numbers, not booleans or numeric strings.')
        return value


class StageFailure(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    test_type: Literal['stage_failure']
    failure_mode: Literal['uncharged_conducting', 'bypassed']
    stage_indices: list[StrictInt] = Field(min_length=1, max_length=30)
    remaining_charge_fraction: float = Field(default=0, ge=0, le=1)
    title: str = Field(default='', max_length=120)

    @field_validator('remaining_charge_fraction', mode='before')
    @classmethod
    def numeric_input(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError('The remaining charge fraction must be a number.')
        return value

    @model_validator(mode='after')
    def stage_selection(self):
        if any(type(n) is not int or not 1 <= n <= 30 for n in self.stage_indices):
            raise ValueError('Selected stages must be whole stage numbers from 1 to 30.')
        if len(set(self.stage_indices)) != len(self.stage_indices):
            raise ValueError('Select each stage once.')
        if self.failure_mode == 'bypassed' and self.remaining_charge_fraction != 0:
            raise ValueError('A bypassed stage is excluded from the pulse. Its contribution fraction must be zero.')
        return self


FaultRequest = Annotated[Union[ChoppedImpulse, StageFailure], Field(discriminator='test_type')]
