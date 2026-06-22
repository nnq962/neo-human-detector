import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from api.services import config_store


class ConfigStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self._tmpdir.name) / "config.yaml"
        self._old_config_path = config_store.CONFIG_PATH
        self._old_notify = config_store._notify_config_saved
        config_store.CONFIG_PATH = str(self.config_path)
        config_store._notify_config_saved = lambda config: None

    def tearDown(self):
        config_store.CONFIG_PATH = self._old_config_path
        config_store._notify_config_saved = self._old_notify
        self._tmpdir.cleanup()

    def test_save_writes_valid_yaml(self):
        config_store.save_config_data(
            {
                "source": "runtime-only",
                "zone_state_machine": {
                    "confirm_enter_time": 1.0,
                    "confirm_exit_time": 2.0,
                    "pending_enter_miss_grace_time": 3.0,
                },
                "cameras": [
                    {
                        "id": "cam1",
                        "name": "Camera 1",
                        "stream": {"source": "rtsp://example", "protocol": "tcp"},
                        "zones": [
                            {
                                "id": "z1",
                                "name": "zone_1",
                                "points": [[1, 2], [3, 4]],
                            }
                        ],
                    }
                ],
            }
        )

        saved = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        self.assertNotIn("source", saved)
        self.assertEqual(saved["zone_state_machine"]["pending_enter_miss_grace_time"], 3.0)
        self.assertEqual(saved["cameras"][0]["zones"][0]["points"], [[1, 2], [3, 4]])

    def test_save_is_atomic_when_yaml_dump_fails(self):
        self.config_path.write_text("stable: true\n", encoding="utf-8")
        old_dump = config_store.yaml.dump

        def fail_dump(*args, **kwargs):
            raise RuntimeError("dump failed")

        config_store.yaml.dump = fail_dump
        try:
            with self.assertRaises(RuntimeError):
                config_store.save_config_data({"stable": False})
        finally:
            config_store.yaml.dump = old_dump

        self.assertEqual(
            yaml.safe_load(self.config_path.read_text(encoding="utf-8")),
            {"stable": True},
        )

    def test_concurrent_transactions_do_not_lose_updates(self):
        self.config_path.write_text("updates: {}\n", encoding="utf-8")

        def write_one(index: int):
            def mutate(config: dict) -> None:
                time.sleep(0.002)
                config.setdefault("updates", {})[f"k{index}"] = index

            config_store.update_config_data(mutate)

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write_one, range(40)))

        saved = yaml.safe_load(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["updates"], {f"k{i}": i for i in range(40)})


if __name__ == "__main__":
    unittest.main()
