import cv2
import numpy as np


def build_homography():
    # Pixel trên ảnh camera: (u, v)
    image_points = np.array(
        [
            [1254, 331],
            [1023, 448],
            [617, 806],
            [187, 802],
            [501, 621],
            [1061, 142],
            [928, 235],
        ],
        dtype=np.float32,
    )

    # Tọa độ thật robot/map: (x, y)
    robot_points = np.array(
        [
            [5.752371788024902, -0.3578376770019531],
            [6.151243686676025, -1.8446992635726929],
            [7.272601127624512, -3.7015960216522217],
            [6.800490379333496, -5.191725254058838],
            [6.311237812042236, -3.9660396575927734],
            [2.7506771087646484, 0.17833957076072693],
            [4.006988048553467, -1.405487060546875],
        ],
        dtype=np.float32,
    )

    # Tính ma trận homography
    H, mask = cv2.findHomography(
        image_points,
        robot_points,
        method=0,
    )

    if H is None:
        raise RuntimeError("Không thể tính được ma trận homography.")

    return H, image_points, robot_points


def pixel_to_robot(
    u: float,
    v: float,
    H: np.ndarray,
) -> tuple[float, float]:
    point = np.array(
        [[[u, v]]],
        dtype=np.float32,
    )

    transformed = cv2.perspectiveTransform(point, H)

    x, y = transformed[0, 0]

    return float(x), float(y)


def evaluate_calibration(
    H: np.ndarray,
    image_points: np.ndarray,
    robot_points: np.ndarray,
):
    print("\nKiểm tra lại các điểm calibration:")
    print("-" * 80)

    errors = []

    for index, (image_point, true_robot_point) in enumerate(
        zip(image_points, robot_points),
        start=1,
    ):
        u, v = image_point
        true_x, true_y = true_robot_point

        pred_x, pred_y = pixel_to_robot(u, v, H)

        error = np.hypot(
            pred_x - true_x,
            pred_y - true_y,
        )

        errors.append(error)

        print(
            f"Điểm {index}: "
            f"pixel=({u:.0f}, {v:.0f}) | "
            f"thật=({true_x:.3f}, {true_y:.3f}) | "
            f"dự đoán=({pred_x:.3f}, {pred_y:.3f}) | "
            f"sai số={error * 100:.1f} cm"
        )

    print("-" * 80)
    print(f"Sai số trung bình: {np.mean(errors) * 100:.1f} cm")
    print(f"Sai số lớn nhất:   {np.max(errors) * 100:.1f} cm")


def main():
    H, image_points, robot_points = build_homography()

    print("Ma trận H:")
    print(H)

    evaluate_calibration(
        H,
        image_points,
        robot_points,
    )

    print("\nNhập pixel bất kỳ trên mặt sàn để đổi sang tọa độ robot.")
    print("Ví dụ: 800 500")
    print("Gõ q để thoát.")

    while True:
        raw = input("\nPixel (u v): ").strip()

        if raw.lower() == "q":
            break

        try:
            u, v = map(float, raw.split())

            x, y = pixel_to_robot(u, v, H)

            print(f"Pixel camera: ({u:.1f}, {v:.1f})")
            print(f"Tọa độ robot: x={x:.4f}, y={y:.4f}")

        except ValueError:
            print("Nhập theo dạng: 800 500")


if __name__ == "__main__":
    main()