from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field


class UartConfig(BaseModel):
    port: str = "/dev/ttyS4"
    baudrate: int = Field(115200, ge=1)


class UartConfigUpdate(BaseModel):
    port: Optional[str] = None
    baudrate: Optional[int] = Field(None, ge=1)


class UartTaskAssignRequest(BaseModel):
    """Payload gửi TaskAssign nhị phân trực tiếp để test robot."""

    message_type: Literal["task_assign"]
    robot_id: int = Field(..., ge=0, le=255)
    task_id: int = Field(..., ge=0, le=255)
    x: float = Field(..., ge=-327.68, le=327.67)
    y: float = Field(..., ge=-327.68, le=327.67)
    theta: float = Field(..., ge=-32.768, le=32.767)


class UartTaskCancelRequest(BaseModel):
    """Payload gửi TaskCancel cho task thủ công đang được theo dõi."""

    message_type: Literal["task_cancel"]
    robot_id: int = Field(..., ge=0, le=255)
    task_id: int = Field(..., ge=0, le=255)


# ─────────────────────────────────────────────────────────────────────────────
class UartMoveToPointRequest(BaseModel):
    """Payload yêu cầu robot di chuyển trực tiếp tới một pose đích."""

    message_type: Literal["move_to_point"] = "move_to_point"
    robot_id: int = Field(..., ge=0, le=255)
    move_id: int = Field(..., ge=0, le=255)
    x: float = Field(..., ge=-327.68, le=327.67)
    y: float = Field(..., ge=-327.68, le=327.67)
    theta: float = Field(..., ge=-32.768, le=32.767)


UartMessageRequest = Annotated[
    Union[
        UartTaskAssignRequest,
        UartTaskCancelRequest,
        UartMoveToPointRequest,
    ],
    Field(discriminator="message_type"),
]
