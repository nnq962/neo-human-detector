export type DetectorMode = 'head' | 'person';
export type ModelSize = 'nano' | 'medium';
export type BatchSize = 1 | 2 | 4;
export type ZoneCheckMode = 'bottom_center' | 'center';

export interface DetectorConfig {
  mode: DetectorMode;
  model_size: ModelSize;
  batch_size: BatchSize;
  conf: number;
  vid_stride: number;
  verbose: boolean;
}

export interface DetectorSettings {
  auto_start: boolean;
  detector: DetectorConfig;
}

export interface UartConfig {
  port: string;
  baudrate: number;
}

export interface ZonesStateMachineConfig {
  zone_check_mode: ZoneCheckMode;
  confirm_enter_time: number;
  confirm_exit_time: number;
  pending_enter_miss_grace_time: number;
}

export type GeneralDetectorConfig = DetectorConfig & ZonesStateMachineConfig & {
  source?: string;
};

export interface AppConfig {
  auto_start: boolean;
  detector: GeneralDetectorConfig;
  uart: UartConfig;
  cameras: Camera[];
  zones: Zone[];
}

export interface Camera {
  id: string;
  name: string;
  source: string;
  source_protocol?: string;
  source_on_demand?: boolean;
  enabled?: boolean;
  webrtc_address?: string;
  zones?: Zone[];
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
