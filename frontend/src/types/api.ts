export type UserRole = "admin" | "viewer";

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface UserResponse {
  id: number;
  email: string;
  roles: UserRole[];
}

export interface AlertResponse {
  alert_type: string;
  bucket_id: string;
  station_id: string;
  delta_grams: number;
  expected_weight_grams: number | null;
  actual_weight_grams: number | null;
  status: string;
  detected_at_utc: string;
  message_text: string;
}

export interface BucketSummaryResponse {
  bucket_id: string;
  bucket_session_id: string | null;
  primary_station_id: string | null;
  primary_started_at_utc: string | null;
  primary_ended_at_utc: string | null;
  expected_final_weight_grams: number | null;
  control_weight_grams: number | null;
  discrepancy_grams: number | null;
  status: string;
}

export interface DeviceWeightLog {
  event_id: string;
  bucket_id: string;
  bucket_session_id: string;
  station_id: string;
  station_type: "primary" | "control";
  recorded_at_utc: string;
  weight_grams: number;
  delta_grams: number;
  raw_weight_grams: number;
  reason: string;
}

export interface DeviceAnomalyEvent {
  anomaly_event_id: string;
  bucket_id: string;
  bucket_session_id: string;
  station_id: string;
  station_type: "primary" | "control";
  event_type: string;
  observed_at_utc: string;
  delta_grams: number;
  weight_before_grams: number;
  weight_after_grams: number;
  persistence_seconds: number;
  video_metadata: Record<string, unknown>;
}

export interface DeviceControlWeight {
  control_weight_record_id: string;
  bucket_id: string;
  station_id: string;
  station_type: "primary" | "control";
  recorded_at_utc: string;
  control_weight_grams: number;
  operator_note: string | null;
}

export interface BucketDetailResponse {
  summary: BucketSummaryResponse;
  weight_logs: DeviceWeightLog[];
  anomaly_events: DeviceAnomalyEvent[];
  control_records: DeviceControlWeight[];
  alerts: AlertResponse[];
}

export interface AnalyticsRange {
  label: string;
  count: number;
}

export interface AnalyticsSummaryResponse {
  total_buckets: number;
  anomaly_alerts: number;
  discrepancy_alerts: number;
  average_discrepancy_grams: number;
  common_loss_ranges: AnalyticsRange[];
}

export interface GlobalSettingItem {
  key: string;
  value: string;
  description: string;
}

export interface GlobalSettingsUpdate {
  items: GlobalSettingItem[];
}
