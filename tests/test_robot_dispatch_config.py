"""Kiểm thử đọc và cập nhật cấu hình auto-dispatch robot."""

import tempfile
import unittest
from pathlib import Path

import yaml

from api.models.robot_dispatch import RobotDispatchConfigUpdate
from api.services import config_store
from api.services.robot_dispatch import (
    get_robot_dispatch_config,
    update_robot_dispatch_config,
)


class RobotDispatchConfigTest(unittest.TestCase):
    """Kiểm tra service cấu hình auto-dispatch robot."""

    def setUp(self):
        """Tạo file cấu hình tạm riêng cho từng ca kiểm thử."""
        self._tmpdir = tempfile.TemporaryDirectory()
        self._old_config_path = config_store.CONFIG_PATH
        self._old_notify = config_store._notify_config_saved
        config_store.CONFIG_PATH = str(Path(self._tmpdir.name) / "config.yaml")
        config_store._notify_config_saved = lambda config: None
        Path(config_store.CONFIG_PATH).write_text(
            yaml.safe_dump({"reid": {"enabled": False}}),
            encoding="utf-8",
        )

    def tearDown(self):
        """Khôi phục config store về trạng thái trước khi kiểm thử."""
        config_store.CONFIG_PATH = self._old_config_path
        config_store._notify_config_saved = self._old_notify
        self._tmpdir.cleanup()

    def test_get_uses_safe_defaults_when_section_is_missing(self):
        """Trả các giá trị mặc định khi YAML chưa có robot_dispatch."""
        self.assertEqual(
            get_robot_dispatch_config(),
            {
                "enabled": False,
                "use_reid": False,
                "ack_timeout_seconds": 1.0,
                "max_retries": 10,
                "max_dispatch_attempts": 10,
                "retry_backoff_seconds": 1.0,
                "robot_rejection_cooldown_seconds": 5.0,
            },
        )

    def test_update_persists_configuration(self):
        """Cập nhật một phần và lưu section robot_dispatch xuống YAML."""
        result = update_robot_dispatch_config(
            RobotDispatchConfigUpdate(
                enabled=True,
                ack_timeout_seconds=1.5,
                max_retries=3,
            )
        )

        self.assertEqual(result["ack_timeout_seconds"], 1.5)
        self.assertEqual(result["max_retries"], 3)
        saved = yaml.safe_load(Path(config_store.CONFIG_PATH).read_text(encoding="utf-8"))
        self.assertEqual(saved["robot_dispatch"], result)

    def test_enabled_reid_dispatch_requires_reid_to_be_enabled(self):
        """Không cho bật auto-dispatch dùng ReID khi ReID hệ thống đang tắt."""
        with self.assertRaisesRegex(ValueError, "ReID"):
            update_robot_dispatch_config(
                RobotDispatchConfigUpdate(enabled=True, use_reid=True)
            )
