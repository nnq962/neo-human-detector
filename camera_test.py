import cv2

mouse_x, mouse_y = 0, 0

def mouse_callback(event, x, y, flags, param):
    global mouse_x, mouse_y
    if event == cv2.EVENT_MOUSEMOVE:
        mouse_x, mouse_y = x, y

rtsp_url = "rtsp://admin:phenikaaneo%40@10.70.22.159:554/Streaming/Channels/101"
cap = cv2.VideoCapture(rtsp_url)

cv2.namedWindow("RTSP")
cv2.setMouseCallback("RTSP", mouse_callback)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    # Vẽ text lên frame
    text = f"x={mouse_x}, y={mouse_y}"
    cv2.putText(frame, text, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1,
                (0, 255, 0), 2)

    cv2.imshow("RTSP", frame)

    if cv2.waitKey(1) & 0xFF == 27:
        break

cap.release()
cv2.destroyAllWindows()