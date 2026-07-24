import struct
from unittest.mock import Mock

import pytest

from src.robot_dispatch_v2.datatypes import (
    Ack,
    AckReasonCode,
    AckResultCode,
    MessageBase,
    MessageType,
    MoveToPoint,
)
from uart_v2.uart_manager import UartManagerV2


# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("result_code", "reason_code"),
    [
        (AckResultCode.ACCEPTED, AckReasonCode.NONE),
        (AckResultCode.REJECTED, AckReasonCode.ROBOT_ERROR),
    ],
)
def test_ack_round_trip(result_code: int, reason_code: int) -> None:
    """Kiểm tra ACK mới giữ nguyên reference ID và kết quả sau encode/decode."""
    message = Ack(
        robot_id=3,
        acked_type=MessageType.MOVE_TO_POINT,
        reference_id=234,
        result_code=result_code,
        reason_code=reason_code,
    )

    decoded = MessageBase.decode_any(message.encode())

    assert decoded == message
    assert len(message.to_payload()) == struct.calcsize(Ack.FORMAT) == 6


# ─────────────────────────────────────────────────────────────────────────────
def test_move_to_point_round_trip() -> None:
    """Kiểm tra MoveToPoint khôi phục đúng move ID và pose sau encode/decode."""
    message = MoveToPoint(
        robot_id=2,
        move_id=200,
        x=1.23,
        y=-4.56,
        theta=1.57,
    )

    decoded = MessageBase.decode_any(message.encode())

    assert decoded == message
    assert len(message.to_payload()) == struct.calcsize(MoveToPoint.FORMAT) == 9


# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("result_code", "expected"),
    [
        (AckResultCode.ACCEPTED, True),
        (AckResultCode.REJECTED, False),
    ],
)
def test_send_with_retry_uses_ack_result(
    monkeypatch: pytest.MonkeyPatch,
    result_code: int,
    expected: bool,
) -> None:
    """Kiểm tra transport phân biệt ACK chấp nhận và ACK từ chối."""
    manager = UartManagerV2()
    message = MoveToPoint(
        robot_id=2,
        move_id=200,
        x=1.23,
        y=-4.56,
        theta=1.57,
    )
    ack = Ack(
        robot_id=message.robot_id,
        acked_type=MessageType.MOVE_TO_POINT,
        reference_id=message.move_id,
        result_code=result_code,
        reason_code=(
            AckReasonCode.NONE
            if result_code == AckResultCode.ACCEPTED
            else AckReasonCode.ROBOT_ERROR
        ),
    )
    manager._handle_received_message(ack)
    monkeypatch.setattr(manager, "send_message", Mock(return_value=True))

    acknowledged = manager.send_with_retry(
        message,
        reference_id=message.move_id,
        timeout=0.01,
        max_retries=1,
    )

    assert acknowledged is expected
