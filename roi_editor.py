import cv2
import numpy as np

polygons = []       # list các polygon đã hoàn thành
current_poly = []   # polygon đang vẽ

def mouse_callback(event, x, y, flags, param):
    global current_poly
    if event == cv2.EVENT_LBUTTONDOWN:
        current_poly.append((x, y))
        print(f"Point: ({x}, {y})")

cap = cv2.VideoCapture("rtsp://admin:phenikaaneo%40@10.70.22.159:554/Streaming/Channels/101")  # hoặc RTSP

cv2.namedWindow("Frame")
cv2.setMouseCallback("Frame", mouse_callback)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # vẽ các polygon đã hoàn thành (cả viền lẫn đỉnh)
    for poly in polygons:
        if len(poly) >= 2:
            cv2.polylines(frame, [np.array(poly)], True, (255, 0, 0), 2)
        for i, (x, y) in enumerate(poly):
            cv2.circle(frame, (x, y), 5, (255, 0, 0), -1)
            cv2.putText(frame, f"{x},{y}", (x+5, y-5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 1)

    # vẽ polygon đang vẽ
    for i, (x, y) in enumerate(current_poly):
        cv2.circle(frame, (x, y), 5, (0, 0, 255), -1)
        cv2.putText(frame, f"{x},{y}", (x+5, y-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 1)

    if len(current_poly) >= 2:
        cv2.polylines(frame, [np.array(current_poly)], False, (0, 255, 255), 2)

    cv2.imshow("Frame", frame)

    key = cv2.waitKey(1)

    if key == 27:  # ESC
        break

    elif key == ord('n'):  # next polygon
        if len(current_poly) >= 3:
            polygons.append(current_poly.copy())
        current_poly = []

    elif key == ord('z'):  # undo
        if current_poly:
            current_poly.pop()

    elif key == ord('c'):  # clear all
        polygons = []
        current_poly = []

cap.release()
cv2.destroyAllWindows()