// ─────────────────────────────────────────────────────────────
// lib/types.ts
// Single source of truth for all shared types.
// Mirrors every Pydantic schema in backend/app/schemas/*.py exactly.
// ─────────────────────────────────────────────────────────────

// ── Enums ────────────────────────────────────────────────────

export type FlashcardDecision = "read_it" | "interested" | "not_interested";

export type FeedbackEventType =
  | "logged_read"
  | "not_interested"
  | "reread"
  | "checkpoint_update"
  | "interested";

export type CheckpointStatus =
  | "finished"
  | "still_reading"
  | "abandoned"
  | "havent_started";

export type AbandonmentStage = "barely_started" | "halfway" | "nearly_finished";

export type MatchSource = "tbr" | "vector" | "llm_expanded";

// ── Author / Book ─────────────────────────────────────────────

export interface AuthorResponse {
  person_uuid: string;
  canonical_name: string;
}

export interface SeriesInfo {
  series_uuid: string;
  title: string;
  order_float: number;
  is_core_storyline: boolean;
}

export interface WorkResponse {
  work_uuid: string;
  title: string;
  author: AuthorResponse;
  language: string;
  aggregate_rating: number | null;
  cover_url: string | null;
  page_count: number | null;
  publication_year: number | null;
  series: SeriesInfo | null;
  enrichment_status: string; // "pending" | "partial" | "complete" | "failed"
}

// ── Onboarding ────────────────────────────────────────────────

export interface FlashcardSubmit {
  work_uuid: string;
  decision: FlashcardDecision;
}

export interface FlashcardResponse {
  status: string;
  event_logged: string;
}

// ── Recommendations ───────────────────────────────────────────

export interface RecommendationRequest {
  query: string;
}

export interface RecommendedItem {
  work: WorkResponse;
  explanation: string;
  match_source: string;
  tbr_context_bonus: boolean;
  is_in_tbr: boolean;
  description: string | null;
}

export interface TBRMatch {
  work_uuid: string;
  title: string;
  author_name: string;
  cover_url: string | null;
  explanation: string;
  overlap_score: number;
}

export interface RecommendationResponse {
  session_id: string;
  query_rewritten: string;
  mood_tags_extracted: string[];
  results: RecommendedItem[];
  author_spotlight?: AuthorSpotlight | null;
  tbr_matches: TBRMatch[];
  content_mode: string;
}

// ── Author Spotlight ──────────────────────────────────────────

export interface AuthorSpotlightBook {
  work_uuid: string;
  title: string;
  cover_url: string | null;
  publication_year: number | null;
  series_label: string | null;
}

export interface AuthorSpotlight {
  author_name: string;
  person_uuid: string | null;
  pen_names: string[];
  books: AuthorSpotlightBook[];
}

// ── Checkpoint ────────────────────────────────────────────────

export interface CheckpointItem {
  rec_uuid: string;
  work: WorkResponse;
  delivered_at: string;
}

export interface TBRDropCandidate {
  tbr_uuid: string;
  work_uuid: string;
  title: string;
  author_name: string;
  cover_url: string | null;
  priority_score: number;
  days_since_added: number;
}

export interface CheckpointResponse {
  pending_items: CheckpointItem[];
  drop_candidates: TBRDropCandidate[];
}

// ── Feedback ──────────────────────────────────────────────────

export interface FeedbackSubmit {
  work_uuid: string;
  event_type: FeedbackEventType;
  checkpoint_status?: CheckpointStatus;
  stated_rating?: number;
  abandonment_stage?: AbandonmentStage;
}

export interface FeedbackResponse {
  status: string;
  event_id: string;
}

// ── TBR ───────────────────────────────────────────────────────

export interface TBRAddRequest {
  work_uuid: string;
  current_query_text?: string;
  current_mood_tags?: string[];
}

export interface TBREntryResponse {
  tbr_uuid: string;
  work: WorkResponse;
  added_at: string;
  priority_score: number;
  add_query_text: string | null;
  add_time_of_day: string | null;
  add_day_of_week: string | null;
}

// ── Authors ───────────────────────────────────────────────────

export interface SeriesWork {
  work_uuid: string;
  title: string;
  order: number;
  is_core: boolean;
  is_read: boolean;
}

export interface SeriesCatalog {
  series_uuid: string;
  title: string;
  works: SeriesWork[];
  is_complete: boolean;
}

export interface AuthorCatalog {
  canonical_name: string;
  person_uuid: string;
  pen_names: PenNameEntry[];
  series: SeriesCatalog[];
  standalones: SeriesWork[];
}

export interface PenNameEntry {
  display_name: string;
  pen_name_uuid: string;
}

// ── Notifications / Release Alerts ───────────────────────────

export interface ReleaseItem {
  event_uuid: string;
  title: string;
  author_name: string;
  publication_date: string;
  work_uuid: string | null;
  dismissed: boolean;
}

export interface ReleaseResponse {
  count: number;
  releases: ReleaseItem[];
}

// ── API Error ─────────────────────────────────────────────────

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// ── Trope & Timeline additions ────────────────────────────────

export interface CalibrationData {
  complete: boolean;
  days_remaining: number;
  interactions_remaining: number;
  total_interactions: number;
}

export interface TropeItem {
  canonical_name: string;
  trope_uuid: string;
  book_count: number;
}

export interface TropeDetailResponse {
  trope: {
    canonical_name: string;
    trope_uuid: string;
  };
  works: WorkResponse[];
}

export interface TimelineEvent {
  event_uuid: string;
  event_type: string;
  event_timestamp: string;
  query_text: string | null;
  mood_tags: string[] | Record<string, any> | null;
  stated_rating: number | null;
  abandonment_stage: string | null;
  tower1_snapshot: Record<string, any> | null;
  work: WorkResponse | null;
}

export interface TimelineResponse {
  timeline: TimelineEvent[];
}
