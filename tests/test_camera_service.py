import tempfile
import unittest
from pathlib import Path

import yaml

from api.models.camera import (
    CalibrationApplyRequest,
    CalibrationPreviewRequest,
    CameraCreate,
    CameraUpdate,
)
from api.services import camera as camera_service
from api.services import config_store


class CameraServiceTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self._tmpdir.name) / "config.yaml"
        self.config_path.write_text("cameras: []\n", encoding="utf-8")

        self._old_config_path = config_store.CONFIG_PATH
        self._old_notify = config_store._notify_config_saved
        self._old_upsert = camera_service.mediamtx_service.upsert_camera_path
        self._old_delete = camera_service.mediamtx_service.delete_camera_path

        config_store.CONFIG_PATH = str(self.config_path)
        config_store._notify_config_saved = lambda config: None
        camera_service.mediamtx_service.delete_camera_path = lambda *args, **kwargs: None

    def tearDown(self):
        config_store.CONFIG_PATH = self._old_config_path
        config_store._notify_config_saved = self._old_notify
        camera_service.mediamtx_service.upsert_camera_path = self._old_upsert
        camera_service.mediamtx_service.delete_camera_path = self._old_delete
        self._tmpdir.cleanup()

    def _read_config(self):
        return yaml.safe_load(self.config_path.read_text(encoding="utf-8"))

    # ─────────────────────────────────────────────────────────────────────────
    def _calibration_request(
        self,
        *,
        accept_warning: bool = False,
    ) -> CalibrationApplyRequest:
        """Tạo request calibration bốn điểm dùng chung cho các test."""
        return CalibrationApplyRequest(
            image_size={"width": 1920, "height": 1080},
            accept_warning=accept_warning,
            points=[
                {
                    "id": "p1",
                    "pixel": {"u": 100, "v": 100},
                    "world": {"x": 0, "y": 0},
                    "robot_id": 1,
                },
                {
                    "id": "p2",
                    "pixel": {"u": 1800, "v": 100},
                    "world": {"x": 10, "y": 0},
                    "robot_id": 1,
                },
                {
                    "id": "p3",
                    "pixel": {"u": 1800, "v": 980},
                    "world": {"x": 10, "y": 5},
                    "robot_id": 1,
                },
                {
                    "id": "p4",
                    "pixel": {"u": 100, "v": 980},
                    "world": {"x": 0, "y": 5},
                    "robot_id": 1,
                },
            ],
        )

    def test_create_camera_syncs_mediamtx_after_config_is_saved(self):
        observed_ids = []

        def fake_upsert(camera: dict):
            saved = self._read_config()
            observed_ids.append(camera["id"])
            self.assertIn(
                camera["id"],
                [saved_camera["id"] for saved_camera in saved["cameras"]],
            )

        camera_service.mediamtx_service.upsert_camera_path = fake_upsert

        created = camera_service.create_camera(
            CameraCreate(
                name="Camera 1",
                stream={"source": "rtsp://example.local/1"},
                zones=[],
            )
        )

        self.assertEqual(observed_ids, [created["id"]])

    def test_update_camera_syncs_mediamtx_after_config_is_saved(self):
        self.config_path.write_text(
            """
cameras:
- id: cam1
  name: Camera 1
  enabled: true
  stream:
    source: rtsp://example.local/old
    protocol: tcp
    on_demand: true
  zones: []
""".lstrip(),
            encoding="utf-8",
        )
        observed_sources = []

        def fake_upsert(camera: dict):
            saved = self._read_config()
            observed_sources.append(camera["stream"]["source"])
            self.assertEqual(
                saved["cameras"][0]["stream"]["source"],
                "rtsp://example.local/new",
            )

        camera_service.mediamtx_service.upsert_camera_path = fake_upsert

        camera_service.update_camera(
            "cam1",
            CameraUpdate(stream={"source": "rtsp://example.local/new"}),
        )

        self.assertEqual(observed_sources, ["rtsp://example.local/new"])

    # ─────────────────────────────────────────────────────────────────────────
    def test_update_camera_replaces_goal_pose_with_service_point(self):
        """Kiểm tra API chỉ lưu điểm phục vụ pixel và xóa goal pose cũ."""
        self.config_path.write_text(
            """
cameras:
- id: cam1
  name: Camera 1
  enabled: true
  stream:
    source: rtsp://example.local/1
    protocol: tcp
    on_demand: true
  zones:
  - id: zone1
    name: Zone 1
    goal_pose: {x: 1.0, y: 2.0, theta: 0.5}
    points: [[1, 2], [3, 4], [5, 6]]
""".lstrip(),
            encoding="utf-8",
        )

        camera_service.update_camera(
            "cam1",
            CameraUpdate(
                zones=[
                    {
                        "id": "zone1",
                        "name": "Zone 1",
                        "service_point": [320, 240],
                        "points": [[1, 2], [3, 4], [5, 6]],
                    }
                ],
            ),
        )

        saved_zone = self._read_config()["cameras"][0]["zones"][0]
        self.assertNotIn("goal_pose", saved_zone)
        self.assertEqual(saved_zone["service_point"], [320, 240])

    # ─────────────────────────────────────────────────────────────────────────
    def test_update_camera_rejects_new_zone_without_service_point(self):
        """Kiểm tra API không lưu zone mới khi chưa chọn điểm phục vụ."""
        initial_config = """
cameras:
- id: cam1
  name: Camera 1
  enabled: true
  stream:
    source: rtsp://example.local/1
    protocol: tcp
    on_demand: true
  zones: []
""".lstrip()
        self.config_path.write_text(initial_config, encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "phải có service_point"):
            camera_service.update_camera(
                "cam1",
                CameraUpdate(
                    zones=[
                        {
                            "name": "Zone mới",
                            "service_point": None,
                            "points": [[1, 2], [3, 4], [5, 6]],
                        }
                    ],
                ),
            )

        self.assertEqual(
            self.config_path.read_text(encoding="utf-8"),
            initial_config,
        )

    # ─────────────────────────────────────────────────────────────────────────
    def test_calibration_preview_does_not_modify_config(self):
        """Kiểm tra preview calibration không ghi thay đổi vào YAML."""
        initial_config = """
cameras:
- id: cam1
  name: Camera 1
  enabled: true
  stream:
    source: rtsp://example.local/1
    protocol: tcp
    on_demand: true
  zones: []
""".lstrip()
        self.config_path.write_text(initial_config, encoding="utf-8")

        result = camera_service.preview_camera_calibration(
            "cam1",
            CalibrationPreviewRequest(
                image_size={"width": 1920, "height": 1080},
                points=[
                    {
                        "id": "p1",
                        "pixel": {"u": 100, "v": 100},
                        "world": {"x": 0, "y": 0},
                    },
                    {
                        "id": "p2",
                        "pixel": {"u": 1800, "v": 100},
                        "world": {"x": 10, "y": 0},
                    },
                    {
                        "id": "p3",
                        "pixel": {"u": 1800, "v": 980},
                        "world": {"x": 10, "y": 5},
                    },
                    {
                        "id": "p4",
                        "pixel": {"u": 100, "v": 980},
                        "world": {"x": 0, "y": 5},
                    },
                ],
            ),
        )

        self.assertEqual(result["camera_id"], "cam1")
        self.assertEqual(result["quality"]["rating"], "LIMITED")
        self.assertEqual(
            self.config_path.read_text(encoding="utf-8"),
            initial_config,
        )

    # ─────────────────────────────────────────────────────────────────────────
    def test_calibration_preview_rejects_pixel_outside_video(self):
        """Kiểm tra preview từ chối pixel nằm ngoài video gốc."""
        self.config_path.write_text(
            """
cameras:
- id: cam1
  name: Camera 1
  stream: {source: rtsp://example.local/1}
  zones: []
""".lstrip(),
            encoding="utf-8",
        )

        request = CalibrationPreviewRequest(
            image_size={"width": 1920, "height": 1080},
            points=[
                {
                    "id": "p1",
                    "pixel": {"u": 1920, "v": 0},
                    "world": {"x": 0, "y": 0},
                },
                {
                    "id": "p2",
                    "pixel": {"u": 100, "v": 0},
                    "world": {"x": 1, "y": 0},
                },
                {
                    "id": "p3",
                    "pixel": {"u": 100, "v": 100},
                    "world": {"x": 1, "y": 1},
                },
                {
                    "id": "p4",
                    "pixel": {"u": 0, "v": 100},
                    "world": {"x": 0, "y": 1},
                },
            ],
        )

        with self.assertRaisesRegex(ValueError, "nằm ngoài"):
            camera_service.preview_camera_calibration("cam1", request)

    # ─────────────────────────────────────────────────────────────────────────
    def test_apply_calibration_requires_warning_confirmation(self):
        """Kiểm tra calibration LIMITED không được lưu khi chưa xác nhận."""
        initial_config = """
cameras:
- id: cam1
  name: Camera 1
  stream: {source: rtsp://example.local/1}
  zones: []
""".lstrip()
        self.config_path.write_text(initial_config, encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "xác nhận cảnh báo"):
            camera_service.apply_camera_calibration(
                "cam1",
                self._calibration_request(),
            )

        self.assertEqual(
            self.config_path.read_text(encoding="utf-8"),
            initial_config,
        )

    # ─────────────────────────────────────────────────────────────────────────
    def test_apply_get_and_delete_camera_calibration(self):
        """Kiểm tra vòng đời lưu, đọc và xóa calibration của camera."""
        self.config_path.write_text(
            """
cameras:
- id: cam1
  name: Camera 1
  enabled: true
  stream:
    source: rtsp://example.local/1
    protocol: tcp
    on_demand: true
  zones:
  - id: zone1
    name: Zone 1
    points: [[1, 2], [3, 4], [5, 6]]
""".lstrip(),
            encoding="utf-8",
        )

        applied = camera_service.apply_camera_calibration(
            "cam1",
            self._calibration_request(accept_warning=True),
        )
        saved = self._read_config()

        self.assertEqual(applied["quality"]["rating"], "LIMITED")
        self.assertIsNone(applied["quality"]["validation_rmse_m"])
        self.assertEqual(applied["camera_id"], "cam1")
        self.assertEqual(saved["cameras"][0]["zones"][0]["id"], "zone1")
        self.assertEqual(
            saved["cameras"][0]["stream"]["source"],
            "rtsp://example.local/1",
        )
        self.assertEqual(len(saved["cameras"][0]["calibration"]["points"]), 4)

        loaded = camera_service.get_camera_calibration("cam1")
        self.assertEqual(loaded, applied)

        deleted = camera_service.delete_camera_calibration("cam1")
        self.assertEqual(deleted, applied)
        self.assertIsNone(camera_service.get_camera_calibration("cam1"))
        self.assertEqual(self._read_config()["cameras"][0]["zones"][0]["id"], "zone1")

    # ─────────────────────────────────────────────────────────────────────────
    def test_replace_camera_preserves_saved_calibration(self):
        """Kiểm tra replace camera không vô tình xóa calibration đã lưu."""
        camera_service.mediamtx_service.upsert_camera_path = lambda *args, **kwargs: None
        self.config_path.write_text(
            """
cameras:
- id: cam1
  name: Camera 1
  stream: {source: rtsp://example.local/1}
  zones: []
""".lstrip(),
            encoding="utf-8",
        )
        camera_service.apply_camera_calibration(
            "cam1",
            self._calibration_request(accept_warning=True),
        )

        camera_service.replace_camera(
            "cam1",
            CameraCreate(
                name="Camera renamed",
                stream={"source": "rtsp://example.local/2"},
                zones=[],
            ),
        )

        saved_camera = self._read_config()["cameras"][0]
        self.assertEqual(saved_camera["name"], "Camera renamed")
        self.assertIn("calibration", saved_camera)


if __name__ == "__main__":
    unittest.main()
