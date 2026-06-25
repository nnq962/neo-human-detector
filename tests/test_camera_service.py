import tempfile
import unittest
from pathlib import Path

import yaml

from api.models.camera import CameraCreate, CameraUpdate
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


if __name__ == "__main__":
    unittest.main()
