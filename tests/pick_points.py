import cv2

# Đường dẫn luồng RTSP của bạn
rtsp_url = "rtsp://admin:061223@bC@192.168.0.10:554/Streaming/Channels/101"

# Danh sách để lưu trữ các điểm đã click (mỗi điểm là một tuple (x, y))
clicked_points = []

# Hàm xử lý sự kiện click chuột
def click_event(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        # Khi click chuột trái, lưu tọa độ vào danh sách
        clicked_points.append((x, y))
        print(f"Đã chọn điểm: X={x}, Y={y}")

# Khởi tạo kết nối với luồng RTSP
cap = cv2.VideoCapture(rtsp_url)

if not cap.isOpened():
    print("Không thể kết nối tới luồng RTSP. Vui lòng kiểm tra lại URL hoặc mạng.")
    exit()

# Tạo một cửa sổ và đặt tên cho nó
window_name = "RTSP Camera Stream"
cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

# Gắn hàm xử lý chuột vào cửa sổ OpenCV
cv2.setMouseCallback(window_name, click_event)

print("Đang chạy... Nhấn chuột trái để chọn điểm. Nhấn 'q' để thoát.")

while True:
    # Đọc frame từ camera (Dòng chuẩn)
    ret, frame = cap.read()
    
    if not ret:
        print("Mất kết nối hoặc không thể đọc dữ liệu từ camera.")
        break

    # Vẽ tất cả các điểm đã chọn lên frame hiện tại
    for pt in clicked_points:
        # Vẽ một chấm tròn màu đỏ tại tọa độ (x, y)
        cv2.circle(frame, pt, 5, (0, 0, 255), -1)
        
        # Viết chữ tọa độ ngay cạnh điểm đó
        text = f"({pt[0]}, {pt[1]})"
        cv2.putText(frame, text, (pt[0] + 10, pt[1] - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

    # Hiển thị frame
    cv2.imshow(window_name, frame)

    # Nhấn 'q' trên bàn phím để thoát vòng lặp
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Giải phóng bộ nhớ và đóng tất cả cửa sổ
cap.release()
cv2.destroyAllWindows()