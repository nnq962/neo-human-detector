from typing import Optional

from pydantic import BaseModel, Field


class UartConfig(BaseModel):
    port: str = "/dev/ttyS4"
    baudrate: int = Field(115200, ge=1)


class UartConfigUpdate(BaseModel):
    port: Optional[str] = None
    baudrate: Optional[int] = Field(None, ge=1)

