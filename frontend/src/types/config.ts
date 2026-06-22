export type ModelSize = 'nano' | 'medium';
export type BatchSize = 1 | 2;
export type DetectionTask = 'detect' | 'pose';
export type TrackerConfig = 'bytetrack.yaml' | 'botsort.yaml';

export interface DetectionConfig {
  task: DetectionTask;
  model_size: ModelSize;
  batch_size: BatchSize;
  conf: number;
  tracker: TrackerConfig;
  verbose: boolean;
}

export interface DetectorSettings {
  auto_start: boolean;
  detection: DetectionConfig;
}

export interface UartConfig {
  port: string;
  baudrate: number;
}

export interface ZoneStateMachineConfig {
  confirm_enter_time: number;
  confirm_exit_time: number;
  pending_enter_miss_grace_time: number;
}

export type GeneralDetectionConfig = DetectionConfig & ZoneStateMachineConfig & {
  source?: string;
};

export interface AppConfig {
  auto_start: boolean;
  detection: GeneralDetectionConfig;
  uart: UartConfig;
  cameras: Camera[];
  zones: Zone[];
}

export interface CameraStream {
  source: string;
  protocol?: string;
  on_demand?: boolean;
}

export interface Camera {
  id: string;
  name: string;
  stream: CameraStream;
  enabled?: boolean;
  webrtc_address?: string;
  zones?: Zone[];
}

export interface Zone {
  id?: string;
  name: string;
  goal_pose: {
    x: number;
    y: number;
    theta: number;
  };
  points: number[][]; // Mảng các tọa độ [x, y]
}
