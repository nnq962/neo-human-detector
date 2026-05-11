import yaml
import os
import aidcv as cv2

CONFIG_PATH = "configs/default.yaml"
TEST_CONFIG_PATH = "configs/test.yaml"

class FlowList(list):
    """Lớp hỗ trợ in mảng thành chuỗi inline [x, y] trong YAML."""
    pass

def flow_list_rep(dumper, data):
    return dumper.represent_sequence('tag:yaml.org,2002:seq', data, flow_style=True)

yaml.add_representer(FlowList, flow_list_rep)

def get_config_data() -> dict:
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError("Configuration file not found.")
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def deep_update(d, u):
    import collections.abc
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = deep_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d

def save_config_data(config_dict: dict) -> None:
    # Ép kiểu điểm (points) thành mảng inline [x, y] thay vì list nhiều dòng
    if "zones" in config_dict and config_dict["zones"] is not None:
        for z in config_dict["zones"]:
            if "points" in z:
                z["points"] = [FlowList(pt) for pt in z["points"]]

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config_dict, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    try:
        test_config = {}
        if os.path.exists(TEST_CONFIG_PATH):
            with open(TEST_CONFIG_PATH, "r", encoding="utf-8") as f:
                test_config = yaml.safe_load(f) or {}

        import copy
        new_test_config = copy.deepcopy(config_dict)
        
        # Khôi phục các tham số đặc biệt cho test.yaml
        if "detector" in test_config:
            if "show" in test_config["detector"]:
                new_test_config.setdefault("detector", {})["show"] = test_config["detector"]["show"]
            if "show_scale" in test_config["detector"]:
                new_test_config.setdefault("detector", {})["show_scale"] = test_config["detector"]["show_scale"]
                
        # Xóa auto_start trong test.yaml
        new_test_config.pop("auto_start", None)

        with open(TEST_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(new_test_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except Exception as e:
        pass # Ignore errors if test.yaml doesn't exist or isn't writable

    # Bắn tín hiệu hot-reload sang detector sau khi lưu file
    try:
        from api.services import detector as detector_service
        detector_service.update_dynamic_params(config_dict)
        detector_service.update_zone(config_dict.get("zones"))
    except Exception as e:
        import logging
        logging.warning(f"Could not trigger hot-reload: {e}")

def get_snapshot_image() -> bytes:
    config = get_config_data()
    rtsp_url = config.get("detector", {}).get("source")
    
    if not rtsp_url:
        raise ValueError("Không tìm thấy RTSP URL trong config.")
        
    cap = cv2.VideoCapture(rtsp_url)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise RuntimeError("Không thể kết nối đến Camera.")

    success, buffer = cv2.imencode('.jpg', frame)
    if not success:
        raise RuntimeError("Lỗi mã hóa ảnh JPEG.")

    return buffer.tobytes()
