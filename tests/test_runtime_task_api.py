"""Kiểm thử API tạo và hủy task runtime."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.models.runtime import RuntimeTaskCreateRequest
from api.routes import runtime as runtime_routes
from api.services import runtime as runtime_service
from src.robot_dispatch_v2 import TaskPriority


class FakeDispatcher:
    """Dispatcher giả ghi nhận lệnh tạo và hủy task."""

    def __init__(self) -> None:
        """Khởi tạo bộ nhớ lời gọi rỗng."""
        self.enqueue_kwargs: dict | None = None
        self.canceled_uid: str | None = None

    # ─────────────────────────────────────────────────────────────────────────
    def enqueue_manual_task(self, **kwargs) -> str:
        """Ghi nhận payload task thủ công và trả UID cố định."""
        self.enqueue_kwargs = kwargs
        return "session:manual-1"

    # ─────────────────────────────────────────────────────────────────────────
    def cancel_task(self, task_uid: str) -> bool:
        """Ghi nhận UID được yêu cầu hủy."""
        self.canceled_uid = task_uid
        return False


# ─────────────────────────────────────────────────────────────────────────────
def _runtime_camera(*, homography=None):
    """Tạo camera runtime giả có calibration 1920x1080."""
    return SimpleNamespace(
        id="camera-1",
        name="Camera 1",
        calibration_image_size=(1920, 1080),
        homography=homography,
    )


# ─────────────────────────────────────────────────────────────────────────────
def _create_request(*, x: int = 960, y: int = 540) -> RuntimeTaskCreateRequest:
    """Tạo payload task thủ công hợp lệ dùng chung cho test."""
    return RuntimeTaskCreateRequest(
        camera_id="camera-1",
        target_pixel={"x": x, "y": y},
        priority="high",
    )


# ─────────────────────────────────────────────────────────────────────────────
def test_create_runtime_task_projects_pixel_and_enqueues(monkeypatch) -> None:
    """Kiểm tra pixel được chiếu qua H trước khi đưa vào dispatcher."""
    dispatcher = FakeDispatcher()
    camera = _runtime_camera(
        homography=[
            [0.01, 0.0, -4.8],
            [0.0, -0.005, 5.4],
            [0.0, 0.0, 1.0],
        ]
    )
    monkeypatch.setattr(
        runtime_service.runtime_manager,
        "require_robot_dispatcher",
        lambda: dispatcher,
    )
    monkeypatch.setattr(
        runtime_service.runtime_manager,
        "require_runtime_camera",
        lambda camera_id: camera,
    )

    result = runtime_service.create_runtime_task(_create_request())

    assert result == {"uid": "session:manual-1"}
    assert dispatcher.enqueue_kwargs == {
        "camera_id": "camera-1",
        "camera_name": "Camera 1",
        "target_pixel": (960, 540),
        "goal_pose": {"x": 4.8, "y": 2.7, "theta": 0.0},
        "priority": TaskPriority.HIGH,
    }


# ─────────────────────────────────────────────────────────────────────────────
def test_create_runtime_task_rejects_missing_calibration(monkeypatch) -> None:
    """Kiểm tra task thủ công bị từ chối khi camera chưa có H."""
    monkeypatch.setattr(
        runtime_service.runtime_manager,
        "require_robot_dispatcher",
        lambda: FakeDispatcher(),
    )
    monkeypatch.setattr(
        runtime_service.runtime_manager,
        "require_runtime_camera",
        lambda camera_id: _runtime_camera(),
    )

    with pytest.raises(ValueError, match="chưa có ma trận homography"):
        runtime_service.create_runtime_task(_create_request())


# ─────────────────────────────────────────────────────────────────────────────
def test_create_runtime_task_rejects_pixel_outside_calibration_image(
    monkeypatch,
) -> None:
    """Kiểm tra pixel ngoài ảnh calibration không được gửi tới robot."""
    monkeypatch.setattr(
        runtime_service.runtime_manager,
        "require_robot_dispatcher",
        lambda: FakeDispatcher(),
    )
    monkeypatch.setattr(
        runtime_service.runtime_manager,
        "require_runtime_camera",
        lambda camera_id: _runtime_camera(
            homography=[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        ),
    )

    with pytest.raises(ValueError, match="nằm ngoài ảnh 1920x1080"):
        runtime_service.create_runtime_task(_create_request(x=1920))


# ─────────────────────────────────────────────────────────────────────────────
def test_cancel_runtime_task_delegates_by_uid(monkeypatch) -> None:
    """Kiểm tra service chuyển yêu cầu hủy theo UID cho dispatcher."""
    dispatcher = FakeDispatcher()
    monkeypatch.setattr(
        runtime_service.runtime_manager,
        "require_robot_dispatcher",
        lambda: dispatcher,
    )

    result = runtime_service.cancel_runtime_task(" session:zone-1 ")

    assert result == {"uid": "session:zone-1"}
    assert dispatcher.canceled_uid == "session:zone-1"


# ─────────────────────────────────────────────────────────────────────────────
def test_runtime_task_routes_match_frontend_contract(monkeypatch) -> None:
    """Kiểm tra method, path, status và envelope mà frontend sử dụng."""
    app = FastAPI()
    app.include_router(runtime_routes.router, prefix="/runtime")
    client = TestClient(app)
    monkeypatch.setattr(
        runtime_service,
        "create_runtime_task",
        lambda request: {"uid": "session:manual-1"},
    )
    monkeypatch.setattr(
        runtime_service,
        "cancel_runtime_task",
        lambda task_uid: {"uid": task_uid},
    )

    created = client.post(
        "/runtime/tasks",
        json={
            "camera_id": "camera-1",
            "target_pixel": {"x": 960, "y": 540},
            "priority": "medium",
        },
    )
    canceled = client.post("/runtime/tasks/session%3Atask-1/cancel")

    assert created.status_code == 201
    assert created.json()["data"] == {"uid": "session:manual-1"}
    assert canceled.status_code == 200
    assert canceled.json()["data"] == {"uid": "session:task-1"}
