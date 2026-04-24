import serial
import threading
import time

UART_PORT = "/dev/ttyS4"
UART_BAUDRATE = 115200

# Khởi tạo UART
ser = serial.Serial(
    port=UART_PORT,
    baudrate=UART_BAUDRATE,
    timeout=0.1  # non-blocking
)

def uart_reader():
    while True:
        try:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)
                print(f"[RAW RX] {data}")
        except Exception as e:
            print(e)

def uart_writer():
    """Luồng gửi dữ liệu UART"""
    counter = 0
    while True:
        try:
            msg = f"Hello {counter}\n"
            ser.write(msg.encode())
            print(f"[TX] {msg.strip()}")
            counter += 1
            time.sleep(1)  # chỉnh tốc độ gửi ở đây
        except Exception as e:
            print(f"[ERROR][WRITE] {e}")
            break

if __name__ == "__main__":
    try:
        print("UART started...")

        # Tạo 2 thread
        t_read = threading.Thread(target=uart_reader, daemon=True)
        t_write = threading.Thread(target=uart_writer, daemon=True)

        t_read.start()
        t_write.start()

        # Giữ chương trình chạy
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping UART...")
        ser.close()