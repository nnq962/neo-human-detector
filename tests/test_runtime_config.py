import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from api.models.camera import CameraUpdate
from api.models.runtime import RuntimeSettingsUpdate
from api.services import camera as camera_service
from api.services import config_store
from api.services import runtime as runtime_service
from src.app.utils import build_runtime_config
from src.camera_initializer import load_cameras_from_config


class RuntimeConfigTest(unittest.TestCase):
    """Kiểm tra cấu hình camera riêng của runtime."""

    def setUp(self):
        """Tạo config tạm và cô lập các dịch vụ bên ngoài."""
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self._tmpdir.name) / "config.yaml"
        self._old_config_path = config_store.CONFIG_PATH
        self._old_notify = config_store._notify_config_saved
        self._old_upsert = camera_service.mediamtx_service.upsert_camera_path
        self._old_delete = camera_service.mediamtx_service.delete_camera_path
        config_store.CONFIG_PATH = str(self.config_path)
        config_store._notify_config_saved = lambda config: None
        camera_service.mediamtx_service.upsert_camera_path = lambda *args, **kwargs: None
        camera_service.mediamtx_service.delete_camera_path = lambda *args, **kwargs: None
        self._write_config()

    # ─────────────────────────────────────────────────────────────────────────
    def tearDown(self):
        """Khôi phục config và MediaMTX service sau mỗi test."""
        config_store.CONFIG_PATH = self._old_config_path
        config_store._notify_config_saved = self._old_notify
        camera_service.mediamtx_service.upsert_camera_path = self._old_upsert
        camera_service.mediamtx_service.delete_camera_path = self._old_delete
        self._tmpdir.cleanup()

    # ─────────────────────────────────────────────────────────────────────────
    def _write_config(self) -> None:
        """Ghi cấu hình bốn camera dùng chung cho các test."""
        self.config_path.write_text(
            """
runtime:
  auto_start: false
  camera_ids: []
detection:
  model_id: test-dynamic-model
  conf: 0.5
  verbose: false
cameras:
- {id: cam1, name: Camera 1, enabled: true, stream: {source: rtsp://one}, zones: []}
- {id: cam2, name: Camera 2, enabled: true, stream: {source: rtsp://two}, zones: []}
- {id: cam3, name: Camera 3, enabled: true, stream: {source: rtsp://three}, zones: []}
- {id: cam4, name: Camera 4, enabled: false, stream: {source: rtsp://four}, zones: []}
""".lstrip(),
            encoding="utf-8",
        )

    # ─────────────────────────────────────────────────────────────────────────
    def _read_config(self) -> dict:
        """Đọc lại YAML sau thao tác service."""
        return yaml.safe_load(self.config_path.read_text(encoding="utf-8"))

    # ─────────────────────────────────────────────────────────────────────────
    def test_runtime_selection_derives_batch_and_preserves_order(self):
        """Kiểm tra batch được suy ra và thứ tự camera được giữ nguyên."""
        artifact = SimpleNamespace(id="test-dynamic-model", batch_size="dynamic")
        with patch.object(runtime_service, "resolve_model_artifact", return_value=artifact):
            result = runtime_service.update_runtime_config(
                RuntimeSettingsUpdate(camera_ids=["cam2", "cam1"]),
            )

        self.assertEqual(result["batch_size"], 2)
        self.assertEqual(result["camera_ids"], ["cam2", "cam1"])
        saved = self._read_config()
        self.assertEqual(saved["runtime"]["camera_ids"], ["cam2", "cam1"])
        self.assertNotIn("batch_size", saved["runtime"])
        self.assertNotIn("batch_size", saved["detection"])

        runtime_config = build_runtime_config(str(self.config_path))
        self.assertEqual(runtime_config.camera_ids, ("cam2", "cam1"))
        self.assertEqual(runtime_config.detection.batch_size, 2)

        cameras = load_cameras_from_config(
            saved,
            camera_ids=runtime_config.camera_ids,
        )
        self.assertEqual([camera.id for camera in cameras], ["cam2", "cam1"])

    # ─────────────────────────────────────────────────────────────────────────
    def test_runtime_rejects_unsupported_camera_count(self):
        """Kiểm tra runtime từ chối lựa chọn ba camera."""
        artifact = SimpleNamespace(id="test-dynamic-model", batch_size="dynamic")
        with patch.object(runtime_service, "resolve_model_artifact", return_value=artifact):
            with self.assertRaisesRegex(ValueError, "batch 1, 2 hoặc 4"):
                runtime_service.update_runtime_config(
                    RuntimeSettingsUpdate(camera_ids=["cam1", "cam2", "cam3"]),
                )

        self.assertEqual(self._read_config()["runtime"]["camera_ids"], [])

    # ─────────────────────────────────────────────────────────────────────────
    def test_runtime_rejects_disabled_camera(self):
        """Kiểm tra camera đã tắt không thể tham gia runtime."""
        artifact = SimpleNamespace(id="test-dynamic-model", batch_size="dynamic")
        with patch.object(runtime_service, "resolve_model_artifact", return_value=artifact):
            with self.assertRaisesRegex(ValueError, "đang bị tắt"):
                runtime_service.update_runtime_config(
                    RuntimeSettingsUpdate(camera_ids=["cam4"]),
                )

    # ─────────────────────────────────────────────────────────────────────────
    def test_auto_start_requires_camera_selection(self):
        """Kiểm tra auto-start không thể bật khi chưa chọn camera."""
        with self.assertRaisesRegex(ValueError, "Cần chọn camera"):
            runtime_service.update_runtime_config(
                RuntimeSettingsUpdate(auto_start=True),
            )

    # ─────────────────────────────────────────────────────────────────────────
    def test_fixed_batch_model_must_match_selection(self):
        """Kiểm tra model batch cố định phải khớp số camera."""
        artifact = SimpleNamespace(id="test-fixed-model", batch_size=2)
        with patch.object(runtime_service, "resolve_model_artifact", return_value=artifact):
            with self.assertRaisesRegex(ValueError, "chỉ hỗ trợ batch 2"):
                runtime_service.update_runtime_config(
                    RuntimeSettingsUpdate(camera_ids=["cam1"]),
                )

    # ─────────────────────────────────────────────────────────────────────────
    def test_disabling_selected_camera_cleans_runtime_selection(self):
        """Kiểm tra tắt camera sẽ loại camera khỏi runtime và tắt auto-start."""
        config = self._read_config()
        config["runtime"] = {"auto_start": True, "camera_ids": ["cam1", "cam2"]}
        self.config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

        camera_service.update_camera("cam1", CameraUpdate(enabled=False))

        saved = self._read_config()
        self.assertEqual(saved["runtime"]["camera_ids"], ["cam2"])
        self.assertFalse(saved["runtime"]["auto_start"])

    # ─────────────────────────────────────────────────────────────────────────
    def test_deleting_selected_camera_cleans_runtime_selection(self):
        """Kiểm tra xóa camera sẽ loại ID khỏi runtime."""
        config = self._read_config()
        config["runtime"] = {"auto_start": True, "camera_ids": ["cam1"]}
        self.config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

        camera_service.delete_camera("cam1")

        saved = self._read_config()
        self.assertEqual(saved["runtime"]["camera_ids"], [])
        self.assertFalse(saved["runtime"]["auto_start"])


if __name__ == "__main__":
    unittest.main()
