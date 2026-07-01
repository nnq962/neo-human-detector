import threading
import time


MAX_UART_BYTES = 250
UART_SEND_REPEAT_COUNT = 3
UART_REPEAT_DELAY_SECONDS = 0.5


# ─────────────────────────────────────────────────────────────────────────────
def _get_uart_zone_id(item: dict) -> str:
    """Lấy định danh zone dùng trong chuỗi UART."""
    return item.get("zone_key") or item.get("zone_name", "")


# ─────────────────────────────────────────────────────────────────────────────
def _build_uart_string(det_list: list, clr_list: list, is_sync: bool = False) -> str:
    """Đóng gói danh sách detected/cleared thành chuỗi UART."""
    parts = []
    if is_sync:
        parts.append("sync")

    if det_list:
        d_str = "d:" + ";".join([
            f"{_get_uart_zone_id(item)},{item['goal_pose'].get('x', 0)},{item['goal_pose'].get('y', 0)},{item['goal_pose'].get('theta', 0)}"
            for item in det_list
        ])
        parts.append(d_str)

    if clr_list:
        c_str = "c:" + ";".join([
            f"{_get_uart_zone_id(item)},{item['goal_pose'].get('x', 0)},{item['goal_pose'].get('y', 0)},{item['goal_pose'].get('theta', 0)}"
            for item in clr_list
        ])
        parts.append(c_str)

    return "-".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
def _send_uart_string_repeated(uart, message: str):
    """Gửi lặp lại một chuỗi UART để tăng xác suất robot nhận được."""
    for _ in range(UART_SEND_REPEAT_COUNT):
        threading.Thread(target=uart.send_string, args=(message,), daemon=True).start()
        time.sleep(UART_REPEAT_DELAY_SECONDS)


# ─────────────────────────────────────────────────────────────────────────────
def send_uart_payload(uart, payload: dict, is_sync: bool = False):
    """Chuyển payload event sang chuỗi UART và chia nhỏ nếu vượt quá giới hạn bytes."""
    if not payload or uart is None:
        return

    detected = payload.get("detected", [])
    cleared = payload.get("cleared", [])
    all_events = [("d", d) for d in detected] + [("c", c) for c in cleared]

    current_det = []
    current_clr = []

    for event_type, event_data in all_events:
        if event_type == "d":
            current_det.append(event_data)
        else:
            current_clr.append(event_data)

        test_str = _build_uart_string(current_det, current_clr, is_sync)

        if len(test_str.encode("utf-8")) > MAX_UART_BYTES:
            if event_type == "d":
                current_det.pop()
            else:
                current_clr.pop()

            full_str = _build_uart_string(current_det, current_clr, is_sync)
            if full_str:
                _send_uart_string_repeated(uart, full_str)

            current_det = [event_data] if event_type == "d" else []
            current_clr = [event_data] if event_type == "c" else []

    final_str = _build_uart_string(current_det, current_clr, is_sync)
    if final_str:
        _send_uart_string_repeated(uart, final_str)
