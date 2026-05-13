export interface AppConfig {
  auto_start: boolean;
  detector: {
    source: string;
    model_path: string;
    conf: number;
    zone_check_mode: string;
    vid_stride: number;
    verbose: boolean;
  };
  uart: {
    port: string;
    baudrate: number;
  };
  zones: Zone[];
}

export interface Zone {
  name: string;
  goal_pose: {
    x: number;
    y: number;
    theta: number;
  };
  points: number[][]; // Mảng các tọa độ [x, y]
}