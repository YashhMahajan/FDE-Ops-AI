from pydantic import BaseModel, ConfigDict


class FrozenModel(BaseModel):
    """Base for immutable domain models. Unknown fields are rejected, never silently dropped."""

    model_config = ConfigDict(frozen=True, extra="forbid")
