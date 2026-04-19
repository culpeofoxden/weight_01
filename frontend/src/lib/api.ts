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
import {
  buildMockBucketCsv,
  mockGetAlerts,
  mockGetAnalyticsSummary,
  mockGetBucket,
  mockGetBuckets,
  mockGetSettings,
  mockLogin,
  mockMe,
  mockUpdateSettings,
} from "./mockApi";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";
const USE_MOCK_API = (import.meta.env.VITE_USE_MOCK_API as string | undefined) !== "false";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface RequestOptions extends RequestInit {
  token?: string | null;
  query?: Record<string, string | number | null | undefined>;
}

let onUnauthorized: (() => void) | null = null;

export function registerUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = new URL(path, API_BASE_URL);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== null && value !== undefined && value !== "") {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.toString();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");

  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  const response = await fetch(buildUrl(path, options.query), {
    ...options,
    headers,
  });

  if (response.status === 401 && onUnauthorized) {
    onUnauthorized();
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const json = (await response.json()) as { detail?: string };
      detail = json.detail ?? detail;
    } catch {
      // ignore non-json errors
    }
    throw new ApiError(detail || "Request failed", response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  login(payload: LoginRequest) {
    if (USE_MOCK_API) {
      return mockLogin(payload);
    }
    return request<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  me(token: string) {
    if (USE_MOCK_API) {
      return mockMe(token);
    }
    return request<UserResponse>("/api/v1/auth/me", { token });
  },

  getBuckets(token: string, filters: { bucket_id?: string; status?: string }) {
    if (USE_MOCK_API) {
      return mockGetBuckets(filters);
    }
    return request<BucketSummaryResponse[]>("/api/v1/buckets", { token, query: filters });
  },

  getBucket(token: string, bucketId: string) {
    if (USE_MOCK_API) {
      return mockGetBucket(bucketId);
    }
    return request<BucketDetailResponse>(`/api/v1/buckets/${bucketId}`, { token });
  },

  getAlerts(token: string, filters: { bucket_id?: string; alert_type?: string }) {
    if (USE_MOCK_API) {
      return mockGetAlerts(filters);
    }
    return request<AlertResponse[]>("/api/v1/alerts", { token, query: filters });
  },

  getAnalyticsSummary(token: string) {
    if (USE_MOCK_API) {
      return mockGetAnalyticsSummary();
    }
    return request<AnalyticsSummaryResponse>("/api/v1/analytics/summary", { token });
  },

  getSettings(token: string) {
    if (USE_MOCK_API) {
      return mockGetSettings();
    }
    return request<GlobalSettingItem[]>("/api/v1/settings", { token });
  },

  updateSettings(token: string, payload: GlobalSettingsUpdate) {
    if (USE_MOCK_API) {
      return mockUpdateSettings(payload);
    }
    return request<GlobalSettingItem[]>("/api/v1/settings", {
      method: "PUT",
      token,
      body: JSON.stringify(payload),
    });
  },
};

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

export function isMockApiEnabled(): boolean {
  return USE_MOCK_API;
}

export function getMockBucketCsv(bucketId: string): string {
  return buildMockBucketCsv(bucketId);
}
