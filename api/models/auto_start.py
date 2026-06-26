from typing import Optional

from pydantic import BaseModel


class AutoStartConfig(BaseModel):
    auto_start: bool = False


class AutoStartConfigUpdate(BaseModel):
    auto_start: Optional[bool] = None
