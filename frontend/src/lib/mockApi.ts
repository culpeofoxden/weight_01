import type {
  AlertResponse,
  AnalyticsSummaryResponse,
  BucketDetailResponse,
  BucketSummaryResponse,
  GlobalSettingItem,
  GlobalSettingsUpdate,
  LoginRequest,
  TokenResponse,
  UserResponse,
} from "../types/api";

const MOCK_USERS: Array<{ email: string; password: string; user: UserResponse }> = [
  {
    email: "admin@example.com",
    password: "admin123",
    user: { id: 1, email: "admin@example.com", roles: ["admin"] },
  },
  {
    email: "viewer@example.com",
    password: "viewer123",
    user: { id: 2, email: "viewer@example.com", roles: ["viewer"] },
  },
];

const MOCK_BUCKETS: BucketSummaryResponse[] = [
  {
    bucket_id: "AMB-24018-A",
    bucket_session_id: "sess-001",
    primary_station_id: "primary-line-01",
    primary_started_at_utc: "2026-04-19T07:10:00Z",
    primary_ended_at_utc: "2026-04-19T07:24:00Z",
    expected_final_weight_grams: 1200,
    control_weight_grams: 1040,
    discrepancy_grams: -160,
    status: "completed",
  },
  {
    bucket_id: "AMB-24018-B",
    bucket_session_id: "sess-002",
    primary_station_id: "primary-line-01",
    primary_started_at_utc: "2026-04-19T08:05:00Z",
    primary_ended_at_utc: null,
    expected_final_weight_grams: 1280,
    control_weight_grams: null,
    discrepancy_grams: null,
    status: "active",
  },
  {
    bucket_id: "AMB-24018-C",
    bucket_session_id: "sess-003",
    primary_station_id: "primary-line-02",
    primary_started_at_utc: "2026-04-19T06:30:00Z",
    primary_ended_at_utc: "2026-04-19T06:49:00Z",
    expected_final_weight_grams: 1180,
    control_weight_grams: 1170,
    discrepancy_grams: -10,
    status: "completed",
  },
];

const MOCK_ALERTS: AlertResponse[] = [
  {
    alert_type: "primary_negative_delta",
    bucket_id: "AMB-24018-A",
    station_id: "primary-line-01",
    delta_grams: -180,
    expected_weight_grams: 1200,
    actual_weight_grams: 1020,
    status: "sent",
    detected_at_utc: "2026-04-19T07:18:00Z",
    message_text: "Unexpected negative delta detected on primary station for bucket AMB-24018-A.",
  },
  {
    alert_type: "control_discrepancy",
    bucket_id: "AMB-24018-A",
    station_id: "control-room-01",
    delta_grams: -160,
    expected_weight_grams: 1200,
    actual_weight_grams: 1040,
    status: "sent",
    detected_at_utc: "2026-04-19T07:26:00Z",
    message_text: "Control discrepancy exceeded tolerance for bucket AMB-24018-A.",
  },
];

let mockSettings: GlobalSettingItem[] = [
  {
    key: "negative_delta_threshold",
    value: "-100",
    description: "Primary station negative anomaly threshold in grams",
  },
  {
    key: "comparison_tolerance_grams",
    value: "100",
    description: "Allowed loss between primary and control",
  },
  {
    key: "negative_persistence_seconds",
    value: "3",
    description: "Seconds a negative drop must persist",
  },
];

const MOCK_BUCKET_DETAILS: Record<string, BucketDetailResponse> = {
  "AMB-24018-A": {
    summary: MOCK_BUCKETS[0],
    weight_logs: [
      {
        event_id: "evt-001",
        bucket_id: "AMB-24018-A",
        bucket_session_id: "sess-001",
        station_id: "primary-line-01",
        station_type: "primary",
        recorded_at_utc: "2026-04-19T07:11:00Z",
        weight_grams: 1240,
        delta_grams: 0,
        raw_weight_grams: 1245,
        reason: "session_start",
      },
      {
        event_id: "evt-002",
        bucket_id: "AMB-24018-A",
        bucket_session_id: "sess-001",
        station_id: "primary-line-01",
        station_type: "primary",
        recorded_at_utc: "2026-04-19T07:16:00Z",
        weight_grams: 1200,
        delta_grams: -40,
        raw_weight_grams: 1208,
        reason: "stabilized",
      },
      {
        event_id: "evt-003",
        bucket_id: "AMB-24018-A",
        bucket_session_id: "sess-001",
        station_id: "primary-line-01",
        station_type: "primary",
        recorded_at_utc: "2026-04-19T07:18:00Z",
        weight_grams: 1020,
        delta_grams: -180,
        raw_weight_grams: 1018,
        reason: "negative_delta",
      },
    ],
    anomaly_events: [
      {
        anomaly_event_id: "anom-001",
        bucket_id: "AMB-24018-A",
        bucket_session_id: "sess-001",
        station_id: "primary-line-01",
        station_type: "primary",
        event_type: "negative_delta_candidate",
        observed_at_utc: "2026-04-19T07:18:00Z",
        delta_grams: -180,
        weight_before_grams: 1200,
        weight_after_grams: 1020,
        persistence_seconds: 4,
        video_metadata: {},
      },
    ],
    control_records: [
      {
        control_weight_record_id: "ctrl-001",
        bucket_id: "AMB-24018-A",
        station_id: "control-room-01",
        station_type: "control",
        recorded_at_utc: "2026-04-19T07:25:00Z",
        control_weight_grams: 1040,
        operator_note: "Visible product loss during transfer.",
      },
    ],
    alerts: MOCK_ALERTS,
  },
  "AMB-24018-B": {
    summary: MOCK_BUCKETS[1],
    weight_logs: [
      {
        event_id: "evt-101",
        bucket_id: "AMB-24018-B",
        bucket_session_id: "sess-002",
        station_id: "primary-line-01",
        station_type: "primary",
        recorded_at_utc: "2026-04-19T08:06:00Z",
        weight_grams: 1285,
        delta_grams: 0,
        raw_weight_grams: 1286,
        reason: "session_start",
      },
      {
        event_id: "evt-102",
        bucket_id: "AMB-24018-B",
        bucket_session_id: "sess-002",
        station_id: "primary-line-01",
        station_type: "primary",
        recorded_at_utc: "2026-04-19T08:11:00Z",
        weight_grams: 1278,
        delta_grams: -7,
        raw_weight_grams: 1280,
        reason: "stabilized",
      },
    ],
    anomaly_events: [],
    control_records: [],
    alerts: [],
  },
  "AMB-24018-C": {
    summary: MOCK_BUCKETS[2],
    weight_logs: [
      {
        event_id: "evt-201",
        bucket_id: "AMB-24018-C",
        bucket_session_id: "sess-003",
        station_id: "primary-line-02",
        station_type: "primary",
        recorded_at_utc: "2026-04-19T06:31:00Z",
        weight_grams: 1182,
        delta_grams: 0,
        raw_weight_grams: 1184,
        reason: "session_start",
      },
    ],
    anomaly_events: [],
    control_records: [
      {
        control_weight_record_id: "ctrl-201",
        bucket_id: "AMB-24018-C",
        station_id: "control-room-01",
        station_type: "control",
        recorded_at_utc: "2026-04-19T06:50:00Z",
        control_weight_grams: 1170,
        operator_note: null,
      },
    ],
    alerts: [],
  },
};

function wait(ms = 250): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export async function mockLogin(payload: LoginRequest): Promise<TokenResponse> {
  await wait();
  const match = MOCK_USERS.find((user) => user.email === payload.email && user.password === payload.password);
  if (!match) {
    const error = new Error("Invalid credentials") as Error & { status: number };
    error.status = 401;
    throw error;
  }
  return {
    access_token: `mock-token:${match.user.email}`,
    token_type: "bearer",
  };
}

export async function mockMe(token: string): Promise<UserResponse> {
  await wait();
  const email = token.replace("mock-token:", "");
  const match = MOCK_USERS.find((user) => user.user.email === email);
  if (!match) {
    const error = new Error("Invalid access token") as Error & { status: number };
    error.status = 401;
    throw error;
  }
  return match.user;
}

export async function mockGetBuckets(filters: { bucket_id?: string; status?: string }): Promise<BucketSummaryResponse[]> {
  await wait();
  return MOCK_BUCKETS.filter((bucket) => {
    const bucketMatch = !filters.bucket_id || bucket.bucket_id.toLowerCase().includes(filters.bucket_id.toLowerCase());
    const statusMatch = !filters.status || bucket.status === filters.status;
    return bucketMatch && statusMatch;
  });
}

export async function mockGetBucket(bucketId: string): Promise<BucketDetailResponse> {
  await wait();
  const detail = MOCK_BUCKET_DETAILS[bucketId];
  if (!detail) {
    const error = new Error("Bucket not found") as Error & { status: number };
    error.status = 404;
    throw error;
  }
  return detail;
}

export async function mockGetAlerts(filters: { bucket_id?: string; alert_type?: string }): Promise<AlertResponse[]> {
  await wait();
  return MOCK_ALERTS.filter((alert) => {
    const bucketMatch = !filters.bucket_id || alert.bucket_id === filters.bucket_id;
    const typeMatch = !filters.alert_type || alert.alert_type === filters.alert_type;
    return bucketMatch && typeMatch;
  });
}

export async function mockGetAnalyticsSummary(): Promise<AnalyticsSummaryResponse> {
  await wait();
  return {
    total_buckets: MOCK_BUCKETS.length,
    anomaly_alerts: MOCK_ALERTS.filter((alert) => alert.alert_type === "primary_negative_delta").length,
    discrepancy_alerts: MOCK_ALERTS.filter((alert) => alert.alert_type === "control_discrepancy").length,
    average_discrepancy_grams: -85,
    common_loss_ranges: [
      { label: "0-99g", count: 1 },
      { label: "-100 to -299g", count: 1 },
      { label: "< -300g", count: 0 },
    ],
  };
}

export async function mockGetSettings(): Promise<GlobalSettingItem[]> {
  await wait();
  return [...mockSettings];
}

export async function mockUpdateSettings(payload: GlobalSettingsUpdate): Promise<GlobalSettingItem[]> {
  await wait();
  mockSettings = payload.items.map((item) => ({ ...item }));
  return [...mockSettings];
}

export function buildMockBucketCsv(bucketId: string): string {
  const detail = MOCK_BUCKET_DETAILS[bucketId];
  if (!detail) {
    return "";
  }
  const header = "event_id,bucket_id,bucket_session_id,station_id,station_type,recorded_at_utc,weight_grams,delta_grams,raw_weight_grams,reason";
  const rows = detail.weight_logs.map((row) =>
    [
      row.event_id,
      row.bucket_id,
      row.bucket_session_id,
      row.station_id,
      row.station_type,
      row.recorded_at_utc,
      row.weight_grams,
      row.delta_grams,
      row.raw_weight_grams,
      row.reason,
    ].join(","),
  );
  return [header, ...rows].join("\n");
}
