import unittest

import numpy as np

from src.reid.datatypes import ReIdConfig, ReIdTrackKey, ReIdTrackState, ReIdTrackStatus
from src.reid.gallery import IdentityGallery
from src.reid.track_manager import ReIdTrackManager


class ReIdTrackManagerTest(unittest.TestCase):
    def test_cleanup_dead_tracks_is_scoped_to_current_camera(self):
        config = ReIdConfig(grace_period=10)
        manager = ReIdTrackManager(
            gallery=IdentityGallery(config),
            embedding_function=lambda _crop: np.ones(4, dtype=np.float32),
            config=config,
        )

        cam_a_key = ReIdTrackKey("cam-a", 1)
        manager.active_tracks[cam_a_key] = ReIdTrackState(
            key=cam_a_key,
            last_seen=1,
        )

        manager.cleanup_dead_tracks("cam-b", set(), frame_idx=100)
        self.assertIn(cam_a_key, manager.active_tracks)

        manager.cleanup_dead_tracks("cam-a", set(), frame_idx=12)
        self.assertNotIn(cam_a_key, manager.active_tracks)

    def test_reverify_requires_consecutive_misses_before_detach(self):
        config = ReIdConfig(
            sim_threshold_match=0.75,
            max_reverify_misses=2,
        )
        gallery = IdentityGallery(config)
        global_id = gallery.resolve_identity(np.asarray([1.0, 0.0]), frame_idx=1).global_id
        manager = ReIdTrackManager(
            gallery=gallery,
            embedding_function=lambda _crop: np.ones(2, dtype=np.float32),
            config=config,
        )
        track = ReIdTrackState(
            key=ReIdTrackKey("cam-a", 1),
            status=ReIdTrackStatus.MATCHED,
            global_id=global_id,
            matched_at=1,
        )

        manager._reverify_confirmed_track(track, np.asarray([0.0, 1.0]), frame_idx=2)
        self.assertEqual(track.status, ReIdTrackStatus.MATCHED)
        self.assertEqual(track.global_id, global_id)
        self.assertEqual(track.reverify_miss_count, 1)

        manager._reverify_confirmed_track(track, np.asarray([0.0, 1.0]), frame_idx=3)
        self.assertEqual(track.status, ReIdTrackStatus.NEW)
        self.assertIsNone(track.global_id)
        self.assertEqual(track.reverify_miss_count, 0)


if __name__ == "__main__":
    unittest.main()
