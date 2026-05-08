from typing import List, Optional
import numpy as np
from src.models import Zone
from .logger import LOGGER

def load_zones(cfg: dict) -> Optional[List[Zone]]:
    zones_data = cfg.get("zones")
    if not zones_data:
        return None
        
    zones = []
    for z_dict in zones_data:
        try:
            name = z_dict.get("name")
            goal_pose = z_dict.get("goal_pose", {})
            points = z_dict.get("points", [])
            
            if not name or not points:
                LOGGER.warning(f"Bỏ qua zone thiếu name hoặc points: {z_dict}")
                continue
                
            if len(points) < 3:
                LOGGER.warning(f"Bỏ qua zone '{name}' vì có ít hơn 3 điểm (chỉ có {len(points)} điểm)")
                continue
                
            # Ép kiểu list[list] thành numpy array để dùng cho openCV
            pts = np.array(points, dtype=np.int32)
            
            zone = Zone(
                name=name,
                pts=pts,
                goal_pose=goal_pose
            )
            zones.append(zone)
        except Exception as e:
            LOGGER.warning(f"Lỗi khi parse zone {z_dict.get('name')}: {e}")
            
    return zones if zones else None