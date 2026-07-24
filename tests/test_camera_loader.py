import math
import unittest

from src.camera_initializer.camera_loader import (
    _calculate_service_theta,
    load_cameras_from_config,
)


class CameraLoaderServicePointTest(unittest.TestCase):
    """Kiểm tra điểm phục vụ pixel khi được nạp vào runtime."""

    def test_service_point_is_projected_to_runtime_goal_pose(self):
        """Kiểm tra loader chiếu pixel và hướng mặt robot ra khỏi tâm zone."""
        cameras = load_cameras_from_config(
            {
                "cameras": [
                    {
                        "id": "cam1",
                        "name": "Camera 1",
                        "stream": {"source": "rtsp://example.local/1"},
                        "calibration": {
                            "image_size": {"width": 1920, "height": 1080},
                            "homography": [
                                [0.1, 0.0, 1.0],
                                [0.0, 0.2, -2.0],
                                [0.0, 0.0, 1.0],
                            ],
                        },
                        "zones": [
                            {
                                "id": "zone1",
                                "name": "Zone 1",
                                "service_point": [20, 30],
                                "points": [[0, 20], [20, 20], [20, 40], [0, 40]],
                            }
                        ],
                    }
                ]
            }
        )

        self.assertEqual(cameras[0].calibration_image_size, (1920, 1080))
        zone = cameras[0].zones[0]
        self.assertEqual(zone.service_point, (20.0, 30.0))
        self.assertEqual(zone.goal_pose["x"], 3.0)
        self.assertEqual(zone.goal_pose["y"], 4.0)
        self.assertAlmostEqual(zone.goal_pose["theta"], 0.0)

    # ─────────────────────────────────────────────────────────────────────────
    def test_service_theta_matches_robot_heading_convention(self):
        """Kiểm tra theta theo bốn hướng chuẩn mà firmware robot sử dụng."""
        zone_center = (0.0, 0.0)
        cases = [
            ((1.0, 0.0), 0.0),
            ((0.0, 1.0), math.pi / 2),
            ((-1.0, 0.0), math.pi),
            ((0.0, -1.0), -math.pi / 2),
        ]

        for goal_point, expected in cases:
            with self.subTest(goal_point=goal_point):
                self.assertAlmostEqual(
                    _calculate_service_theta(zone_center, goal_point),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
