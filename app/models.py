from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, model_validator


class GeneratePredictionRequest(BaseModel):
    prediction_date: date | None = None
    selected_count: int = Field(default=65, ge=60, le=80)


class GenerateDigitPredictionRequest(BaseModel):
    prediction_date: date | None = None


class ReplayPredictionRequest(BaseModel):
    prediction_date: date
    selected_count: int = Field(default=65, ge=60, le=80)


class BacktestRequest(BaseModel):
    selected_count: int = Field(default=65, ge=60, le=80)
    start_date: date | None = None
    end_date: date | None = None
    minimum_training_draws: int = Field(default=365, ge=30, le=2_000)

    @model_validator(mode="after")
    def validate_dates(self) -> "BacktestRequest":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be before or equal to end_date")
        return self


class DigitBacktestRequest(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    minimum_training_draws: int = Field(default=365, ge=30, le=2_000)

    @model_validator(mode="after")
    def validate_dates(self) -> "DigitBacktestRequest":
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must be before or equal to end_date")
        return self
