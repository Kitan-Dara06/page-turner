// ─────────────────────────────────────────────────────────────
// lib/api.ts
// Typed fetch wrapper. No component ever calls `fetch` directly.
// All backend communication is routed through the named exports below.
// ─────────────────────────────────────────────────────────────

import {
  ApiError,
  AuthorCatalog,
  CheckpointResponse,
  FeedbackResponse,
  FeedbackSubmit,
  FlashcardResponse,
  FlashcardSubmit,
  RecommendationRequest,
  RecommendationResponse,
  ReleaseResponse,
  TBRAddRequest,
  TBREntryResponse,
  WorkResponse,
  CalibrationData,
  TropeItem,
  TropeDetailResponse,
  TimelineResponse,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Auth token store ──────────────────────────────────────────
// AuthProvider calls setAuthToken on session changes.
// apiFetch automatically attaches it — zero touch to call sites.
let _authToken: string | null = null;

export function setAuthToken(token: string | null) {
  _authToken = token;
}

export function getAuthToken(): string | null {
  return _authToken;
}

// ── Core fetch wrapper ────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${BASE_URL}${path}`;

  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(_authToken ? { Authorization: `Bearer ${_authToken}` } : {}),
      ...(options.headers ?? {}),
    },
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body?.detail ?? detail;
    } catch {
      // body wasn't JSON, keep the default message
    }
    throw new ApiError(res.status, detail);
  }

  // 204 No Content — return null cast to T
  if (res.status === 204) return null as unknown as T;

  return res.json() as Promise<T>;
}

// ── Onboarding ────────────────────────────────────────────────

export const onboarding = {
  /** FR-CS-01: Fetch the calibration flashcard stack. */
  getFlashcards(): Promise<WorkResponse[]> {
    return apiFetch<WorkResponse[]>("/api/v1/onboarding/flashcards");
  },

  /** POST a single card swipe decision. */
  postResponse(payload: FlashcardSubmit): Promise<FlashcardResponse> {
    return apiFetch<FlashcardResponse>("/api/v1/onboarding/response", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },
};

// ── Recommendations ───────────────────────────────────────────

export const recommendations = {
  /** FR-QR-01–07: Submit a natural-language query and get results. */
  query(payload: RecommendationRequest): Promise<RecommendationResponse> {
    return apiFetch<RecommendationResponse>("/api/v1/recommend/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /** FR-FL-02: Fetch books delivered since the last checkpoint. */
  getCheckpoint(): Promise<CheckpointResponse> {
    return apiFetch<CheckpointResponse>("/api/v1/recommend/checkpoint");
  },
  getTropes(): Promise<{ tropes: TropeItem[] }> {
    return apiFetch<{ tropes: TropeItem[] }>("/api/v1/recommend/tropes");
  },
  getTropeDetails(tropeUuid: string): Promise<TropeDetailResponse> {
    return apiFetch<TropeDetailResponse>(
      `/api/v1/recommend/tropes/${tropeUuid}`,
    );
  },
};

// ── Feedback ──────────────────────────────────────────────────

export const feedback = {
  /** FR-FL-01–06: Submit any interaction event to update Tower 1/2. */
  submit(payload: FeedbackSubmit): Promise<FeedbackResponse> {
    return apiFetch<FeedbackResponse>("/api/v1/feedback/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getHistory(): Promise<{ reading: WorkResponse[]; finished: WorkResponse[] }> {
    return apiFetch<{ reading: WorkResponse[]; finished: WorkResponse[] }>(
      "/api/v1/feedback/history",
    );
  },
  getTimeline(): Promise<TimelineResponse> {
    return apiFetch<TimelineResponse>("/api/v1/feedback/timeline");
  },
};

// ── TBR ───────────────────────────────────────────────────────

export const tbr = {
  /** FR-TBR-01: Fetch the user's active TBR queue, sorted by priority. */
  getList(): Promise<TBREntryResponse[]> {
    return apiFetch<TBREntryResponse[]>("/api/v1/tbr/");
  },

  /** FR-TBR-01: Add a book to the TBR with full context capture. */
  add(payload: TBRAddRequest): Promise<TBREntryResponse> {
    return apiFetch<TBREntryResponse>("/api/v1/tbr/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /** Drop a book from the TBR (moves to graveyard). */
  drop(tbrUuid: string): Promise<{ status: string }> {
    return apiFetch<{ status: string }>(`/api/v1/tbr/${tbrUuid}`, {
      method: "DELETE",
    });
  },

  /** FR-TBR-02: Reset priority to 0.7 — user chose to keep. */
  resetPriority(
    tbrUuid: string,
  ): Promise<{ status: string; priority_score: number }> {
    return apiFetch<{ status: string; priority_score: number }>(
      `/api/v1/tbr/${tbrUuid}/reset-priority`,
      { method: "PUT" },
    );
  },
};

// ── Authors ───────────────────────────────────────────────────

export const authors = {
  /** FR-AT-03: Get an author's full catalog with series reading order. */
  getCatalog(personId: string): Promise<AuthorCatalog> {
    return apiFetch<AuthorCatalog>(`/api/v1/authors/${personId}/catalog`);
  },
};

// ── Notifications ─────────────────────────────────────────────

export const notifications = {
  /** FR-AT-02: Get undismissed author release alerts. */
  getReleases(): Promise<ReleaseResponse> {
    return apiFetch<ReleaseResponse>("/api/v1/notifications/releases");
  },

  /** FR-AT-02: Dismiss a single release notification. */
  dismissRelease(eventUuid: string): Promise<{ status: string }> {
    return apiFetch<{ status: string }>(
      `/api/v1/notifications/releases/${eventUuid}/dismiss`,
      { method: "POST" },
    );
  },
};

// ── Profile ───────────────────────────────────────────────────

export interface ProfileDimension {
  key: string;
  name: string;
  question: string;
  value: number;
  interpretation: string;
}

export interface ProfilePhase {
  phase: string;
  confidence: number;
  description: string;
  genre?: string;
  velocity?: number;
}

export interface ProfileResponse {
  dimensions: ProfileDimension[];
  phase: ProfilePhase | null;
  message?: string;
  is_admin?: boolean;
  calibration?: {
    complete: boolean;
    days_remaining: number;
    interactions_remaining: number;
    total_interactions: number;
  };
}

export const profile = {
  /** Returns Tower 1 profile dimensions + current reader phase. */
  get(
    contentMode: "fiction" | "nonfiction" = "fiction",
  ): Promise<ProfileResponse> {
    return apiFetch<ProfileResponse>(
      `/api/v1/profile/?content_mode=${contentMode}`,
    );
  },
};
