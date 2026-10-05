// ============================================================================
// API layer — typed wrapper around the FastAPI backend.
//
// Every request carries the HttpOnly session cookie (credentials: "include").
// Non-2xx responses become { ok: false, error } so callers never repeat
// try/catch.
// ============================================================================

export interface AiDetection {
  ran: boolean;
  ai_suspected: boolean;
  ai_score: number;
  model: string | null;
  provider: string | null;
  explanation: string;
  latency_ms: number;
}

export interface Me {
  status: string;
  admin: string;
  name: string;
  designation: string | null;
  institution: string | null;
  pending_approval: boolean;
  is_super_admin: boolean;
}

// ----------------------------------------------------------------------------
// Fetch wrapper
// ----------------------------------------------------------------------------

export type ApiResult<T> = { ok: true; data: T; response: Response } | { ok: false; error: string };

async function request<T>(url: string, init?: RequestInit, timeoutMs = 45000): Promise<ApiResult<T>> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      ...init,
      cache: "no-store",
      headers: {
        ...(init?.headers || {}),
      },
      credentials: "include",
      signal: init?.signal || controller.signal,
    });
    clearTimeout(timeoutId);
    if (response.status === 429) throw new Error("Rate limit exceeded. Please wait.");
    if (response.status === 413) {
      throw new Error("File too large — the server limit is 4.5 MB. Please use a smaller or lower-resolution file.");
    }

    let data: unknown = null;
    if ((response.headers.get("content-type") || "").includes("application/json")) {
      data = await response.json();
    }
    if (!response.ok) {
      throw new Error((data as { detail?: string } | null)?.detail || `Error ${response.status}`);
    }
    return { ok: true, data: data as T, response };
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof Error && err.name === "AbortError") {
      return { ok: false, error: "Request timed out" };
    }
    return { ok: false, error: err instanceof Error ? err.message : "Network error" };
  }
}

function form(fields: Record<string, string | Blob | File | undefined | null>): FormData {
  const fd = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (value != null) fd.append(key, value);
  }
  return fd;
}

// ----------------------------------------------------------------------------
// Auth endpoints
// ----------------------------------------------------------------------------

export function getMe(timeoutMs = 8000) {
  return request<Me>("/api/admin/me", undefined, timeoutMs);
}

export function googleLogin(credential: string) {
  return request<{ status: string }>("/api/admin/login", {
    method: "POST",
    body: form({ credential }),
  });
}

export function demoLogin() {
  return request<{ status: string }>("/api/admin/demo_login", {
    method: "POST",
  });
}

export function logout() {
  return request<{ status: string }>("/api/admin/logout", { method: "POST" });
}

export function assignRole(targetEmail: string, designation: string, institution: string) {
  return request<{ status: string }>("/api/admin/assign_role", {
    method: "POST",
    body: form({ target_email: targetEmail, designation, institution }),
  });
}

export function revokeOfficer(targetEmail: string) {
  return request<{ status: string; email: string; revoked_at: string }>("/api/admin/revoke_officer", {
    method: "POST",
    body: form({ target_email: targetEmail }),
  });
}

export function unrevokeOfficer(targetEmail: string) {
  return request<{ status: string; email: string }>("/api/admin/unrevoke_officer", {
    method: "POST",
    body: form({ target_email: targetEmail }),
  });
}

export function removeOfficer(targetEmail: string) {
  return request<{ status: string; email: string }>("/api/admin/remove_officer", {
    method: "POST",
    body: form({ target_email: targetEmail }),
  });
}

/** Officer directory row for super-admin role approvals, revocation, and removal. */
export interface OfficerEntry {
  email: string;
  name: string;
  designation: string | null;
  institution: string | null;
  registered_at: string;
  is_revoked?: boolean;
  revoked_at?: string | null;
}

export function getSigners() {
  return request<{ signers: OfficerEntry[] }>("/api/admin/signers");
}

// ----------------------------------------------------------------------------
// MHA screening desk (SIH26188 — AI-Based Fake Identity & Document Screening)
//
// Module contract (1:1 with the problem statement):
//   M1 extraction  OCR/MRZ/declared field extraction
//   M2 validation  format/MRZ/expiry + watchlist
//   M3 tampering   ELA/spectral/noise/metadata + AI-generation cues
//   M4 face        document portrait vs live holder capture
// ----------------------------------------------------------------------------

export type ScreenVerdict = "CLEAR" | "REVIEW" | "FLAGGED";

export interface ScreenCheck {
  label: string;
  ok: boolean | null;
  detail: string;
}

export interface ScreenMrz {
  format?: string;
  valid?: boolean;
  document_ck?: boolean | null;
  dob_ck?: boolean | null;
  expiry_ck?: boolean | null;
  composite_ck?: boolean | null;
  passport?: string;
}

export interface ScreenModuleExtraction {
  medium: "pdf" | "image" | "unknown";
  mrz?: ScreenMrz | null;
  ocr?: { ran: boolean; reason?: string };
  document_aware?: boolean | null;
}

export interface ScreenModuleValidation {
  verdict: string;
  checks: ScreenCheck[];
}

export interface ScreenSpectralAnalysis {
  papr?: number;
  high_freq_ratio?: number;
  spectral_anomaly?: boolean;
  status?: string;
  detail?: string;
}

export interface ScreenNoiseConsistency {
  portrait_noise_var?: number;
  substrate_noise_var?: number;
  noise_ratio?: number;
  consistent?: boolean;
  status?: string;
  detail?: string;
}

export interface ScreenImageQA {
  width?: number;
  height?: number;
  megapixels?: number;
  blur_est?: number;
  blurry?: boolean;
  dark_frac?: number;
  bright_frac?: number;
  overexposed?: boolean;
  underexposed?: boolean;
}

export interface ScreenModuleTampering {
  verdict: string;
  checks: ScreenCheck[];
  ela?: {
    status?: string;
    damage_ratio?: number;
    mean_diff?: number;
    latency_ms?: number;
  } | null;
  spectral?: ScreenSpectralAnalysis | null;
  noise_consistency?: ScreenNoiseConsistency | null;
  qa?: ScreenImageQA | null;
  heatmap_b64?: string | null;
  overlay_grid?: number[][] | null;
  roi?: ForensicsROI[];
  liveness?: Array<{ signal?: string; level?: string; note?: string }>;
}

export interface ScreenModuleFace {
  verdict: string;
  match: boolean | null;
  score: number;
  method: string;
  detail: string;
  checks: ScreenCheck[];
}

export interface ForensicsROI {
  label: string;
  x: number;
  y: number;
  w: number;
  h: number;
  confidence: number;
}

export interface ScreenModules {
  extraction: ScreenModuleExtraction;
  validation: ScreenModuleValidation;
  tampering: ScreenModuleTampering;
  face: ScreenModuleFace;
}

export interface ScreenReport {
  id: string;
  filename: string;
  doc_type: string;
  checkpoint: string;
  verdict: ScreenVerdict;
  risk_score: number;
  confidence: number;
  screener?: string | null;
  created_at: string;
  adjudication?: string | null;
  adjudicator?: string | null;
  adjudication_note?: string | null;
  adjudicated_at?: string | null;
  masked_fields: Record<string, string | boolean | null>;
  field_hashes?: Record<string, { h: string; s: string }> | null;
  session_id?: string | null;
  signals?: string[];
  ai_detection?: AiDetection | null;
  file_hash?: string;
  block_hash?: string | null;
  prev_hash?: string | null;
  watchlist_hits?: { field: string; mask: string }[];
  reasons?: string[];
  latency_ms?: number;
  declared_count?: number;
  modules?: ScreenModules;
  created_at_ist?: string | null;
  removed_at?: string | null;
  removed_at_ist?: string | null;
  removed_by?: string | null;
  nationality?: string | null;
  purpose?: string | null;
  travel_validity?: ScreenTravelValidity | null;
  syndicate_alerts?: Array<{
    level: string;
    type: string;
    title: string;
    detail: string;
    checkpoint: string;
  }>;
}

export interface ScreenQueue {
  pending: ScreenReport[];
  recent: ScreenReport[];
}

export interface WatchlistEntry {
  id: number;
  category: string | null;
  mask: string | null;
  reason: string | null;
  added_by: string;
  created_at: string;
}

export const SCREEN_DOC_TYPES = [
  "pan",
  "passport",
  "visa",
  "driving_licence",
  "voter_id",
  "aadhaar",
  "nepali_citizenship",
  "bhutan_citizenship",
  "other",
] as const;

export type ScreenDocType = (typeof SCREEN_DOC_TYPES)[number];

/**
 * Backend-aligned document labels. These are the document families the
 * screening pipeline can extract and validate end to end.
 */
export const SCREEN_DOC_LABELS: Record<ScreenDocType, string> = {
  pan: "PAN",
  passport: "PASSPORT",
  visa: "VISA",
  driving_licence: "DRIVING LICENCE",
  voter_id: "VOTER ID",
  aadhaar: "AADHAAR",
  nepali_citizenship: "NEPALI NAGARIKTA",
  bhutan_citizenship: "BHUTANESE CITIZENSHIP",
  other: "OTHER",
};

export const SCREEN_DOC_NUMBER_PLACEHOLDERS: Record<ScreenDocType, string> = {
  pan: "e.g. ABCDP2234A",
  passport: "e.g. K1234567",
  visa: "e.g. V1234567",
  driving_licence: "e.g. KA0120201234567",
  voter_id: "e.g. ABC1234567",
  aadhaar: "12-digit UID (e.g. 5489 2104 9931)",
  nepali_citizenship: "Cert No (e.g. 12-01-75-03421)",
  bhutan_citizenship: "CID No (e.g. 10101001234)",
  other: "Number printed on the document",
};

/**
 * Watchlist categories are the identifier families the backend actually
 * hashes and compares during screening. The category is metadata; matching
 * is always by SHA-256 digest.
 */
export const SCREEN_WATCHLIST_CATEGORIES = [
  "pan",
  "passport",
  "visa",
  "driving_licence",
  "voter_id",
  "phone",
] as const;

export type ScreenWatchlistCategory =
  (typeof SCREEN_WATCHLIST_CATEGORIES)[number];

export const SCREEN_WATCHLIST_LABELS: Record<ScreenWatchlistCategory, string> = {
  pan: "PAN",
  passport: "PASSPORT",
  visa: "VISA",
  driving_licence: "DRIVING LICENCE",
  voter_id: "VOTER ID",
  phone: "PHONE",
};

export const SCREEN_WATCHLIST_PLACEHOLDERS: Record<
  ScreenWatchlistCategory,
  string
> = {
  pan: "e.g. ABCDP2234A",
  passport: "e.g. K1234567",
  visa: "e.g. V1234567",
  driving_licence: "e.g. KA0120201234567",
  voter_id: "e.g. ABC1234567",
  phone: "e.g. 9876543210",
};

export interface ScreenTravelValidity {
  days_to_expiry: number | null;
  six_month_rule: boolean | null;
  age_at_crossing: number | null;
  status: "VALID" | "EXPIRING_SOON" | "EXPIRED" | "UNKNOWN";
  detail: string;
}

/** Run a screening pass on an uploaded identity document (officer only).
 *  When sessionId is given (SIH26188 session flow) the resulting audit row is
 *  attached to that border session and its per-field digests are persisted for
 *  cross-document comparison. Supports dual-sided upload (file + fileBack). */
export function screenDocument(
  file: File,
  docType: string,
  checkpoint: string,
  declared?: Record<string, string>,
  liveFrame?: Blob | null,
  sessionId?: string,
  fileBack?: File | null,
) {
  const fd = form({ doc_type: docType, checkpoint });
  fd.append("file", file, file.name);
  fd.append("capture_source", file.name.startsWith("webcam_") ? "webcam" : "upload");
  if (fileBack) fd.append("file_back", fileBack, fileBack.name);
  if (declared && Object.keys(declared).length > 0) {
    fd.append("declared", JSON.stringify(declared));
  }
  if (liveFrame) fd.append("live_frame", liveFrame, "holder_live.jpg");
  if (sessionId) fd.append("session_id", sessionId);
  return request<ScreenReport>("/api/screen", { method: "POST", body: fd }, 90000);
}

export function getScreenQueue() {
  return request<ScreenQueue>("/api/screen/queue");
}

export function getScreenReport(reportId: string) {
  return request<ScreenReport>(
    `/api/screen/reports/${encodeURIComponent(reportId)}`,
  );
}

export function adjudicateScreen(reportId: string, decision: string, note?: string) {
  return request<{ ok: boolean }>(
    `/api/screen/reports/${encodeURIComponent(reportId)}/adjudicate`,
    { method: "POST", body: form({ decision, note: note || "" }) },
  );
}

export function getWatchlist() {
  return request<{ entries: WatchlistEntry[] }>("/api/screen/watchlist");
}

export function addWatchlistEntry(category: string, value: string, reason?: string) {
  return request<{ ok: boolean; id?: number; mask?: string; already?: boolean }>(
    "/api/screen/watchlist/add",
    { method: "POST", body: form({ category, value, reason: reason || "" }) },
  );
}

export function removeWatchlistEntry(entryId: number) {
  return request<{ ok: boolean }>("/api/screen/watchlist/remove", {
    method: "POST",
    body: form({ entry_id: String(entryId) }),
  });
}

export function getSyndicateAlerts(checkpoint?: string) {
  const url = checkpoint ? `/api/screen/syndicate-alerts?checkpoint=${encodeURIComponent(checkpoint)}` : "/api/screen/syndicate-alerts";
  return request<{
    checkpoint_filter: string;
    total_screened_sample: number;
    alerts: Array<{
      level: string;
      type: string;
      title: string;
      detail: string;
      checkpoint: string;
    }>;
    active_alerts_count: number;
  }>(url);
}

export function getDossierUrl(reportId: string, autoPrint: boolean = false): string {
  return `/api/screen/dossier/${encodeURIComponent(reportId)}${autoPrint ? "?print=true" : ""}`;
}

export function getBsaCertificateUrl(sessionId: string): string {
  return `/api/screen/bsa65b/${encodeURIComponent(sessionId)}`;
}

export function getShiftHandoverToken(sessionId: string) {
  return request<ShiftHandoverPacket>(
    `/api/screen/handover/${encodeURIComponent(sessionId)}`,
  );
}

export interface ShiftHandoverPacket {
  handover_id: string;
  session_id: string;
  timestamp: string;
  screener: string;
  verdict: string;
  risk_score: number;
  seal: string;
  qr_packet_string: string;
  qr_packet: Record<string, unknown>;
}

export function getBorderThreatMatrix() {
  return request<{
    timestamp: string;
    overall_threat_level: string;
    national_border_threat_index: number;
    active_syndicates_flagged: number;
    checkpoints: Array<{
      id: string;
      name: string;
      state: string;
      threat_level: string;
      threat_score: number;
      primary_threat: string;
      active_alerts: number;
      status: string;
    }>;
  }>("/api/border/threat_matrix");
}

export interface AadhaarFieldBox {
  label: string;
  class_id?: number;
  x: number;
  y: number;
  w: number;
  h: number;
  confidence: number;
}

export function getAadhaarFields(file: File) {
  const fd = new FormData();
  fd.append("file", file, file.name);
  return request<{
    ok: boolean;
    count: number;
    fields: AadhaarFieldBox[];
    model: string;
  }>("/api/screen/aadhaar-fields", {
    method: "POST",
    body: fd,
  });
}

export interface LivenessResult {
  verdict: "LIVE" | "SUSPECT" | "SPOOF";
  liveness_passed: boolean;
  confidence: number;
  challenge: string;
  checks: ScreenCheck[];
  signals: string[];
  motion_score?: number;
  latency_ms?: number;
}

export function verifyLiveness(frames: Blob[], challenge: string = "blink", meta: Record<string, unknown> = {}) {
  const fd = new FormData();
  frames.forEach((f, idx) => {
    fd.append("frames", f, `frame_${idx}.jpg`);
  });
  fd.append("challenge", challenge);
  fd.append("client_meta", JSON.stringify(meta));
  return request<LivenessResult>("/api/screen/liveness", {
    method: "POST",
    body: fd,
  });
}

// ----------------------------------------------------------------------------
// Screening lookup & analytics — verified-digest surface for the screening
// desk. The lookup re-verifies a file/text/digest against past screening
// records; analytics aggregates verdict mix + latency. No raw bytes, no PII.
// ----------------------------------------------------------------------------

export type VerdictKind = "AUTHENTIC" | "PROVEN_FAKE" | "REVOKED" | "UNSIGNED";

/** Latest matching screening record for a digest (adjudication-aware verdict). */
export interface ScreeningLookup {
  verdict: VerdictKind;
  message: string;
  hash: string;
  filename: string;
  checkpoint: string;
  headline: string;
  guidance: string;
  reasons: string[];
  screening: {
    verdict: ScreenVerdict;
    risk_score: number;
    confidence: number;
    adjudication?: string | null;
    adjudicator?: string | null;
    adjudication_note?: string | null;
    adjudicated_at?: string | null;
    screener?: string | null;
    created_at: string;
  } | null;
  ai_detection?: AiDetection | null;
  ai_score?: number;
  ai_model?: string | null;
  ai_provider?: string | null;
  ai_explanation?: string;
  ai_suspected?: boolean;
}

export interface Broadcast {
  title: string;
  urgency: string;
  content: string;
  signer: string;
  institution: string;
  designation: string;
  timestamp: string;
  file_hash: string;
  signature: string;
  ipfs_cid: string;
  media_type: string;
  media_name: string;
  has_media: boolean;
  is_mine: boolean;
  can_delete: boolean;
}

export interface AnalyticsPayload {
  stats: Record<VerdictKind, number>;
  latency: { avg_ms: number; min_ms: number; max_ms: number; samples: number } | null;
  providers: Record<string, number>;
}

export interface DetectionUsage {
  provider: string;
  model: string;
  period_day: string;
  period_month: string;
  ops_used_today: number;
  ops_used_month: number;
  limit_today: number;
  limit_month: number;
  remaining_today: number;
  remaining_month: number;
}

export interface AnalyticsSummary {
  analytics: AnalyticsPayload;
  usage: DetectionUsage | null;
  cached: boolean;
}

/** Screening lookup: re-check a file against the latest matching screening pass. */
export function verifyFile(file: Blob, filename: string, clientHash?: string) {
  const fd = new FormData();
  fd.append("file", file, filename);
  if (clientHash) fd.append("client_hash", clientHash);
  return request<ScreeningLookup>("/api/verify", { method: "POST", body: fd });
}

/** Screening lookup: paste raw text, hashed client-side the same way. */
export function verifyText(rawText: string) {
  const fd = form({ raw_text: rawText });
  return request<ScreeningLookup>("/api/verify", { method: "POST", body: fd });
}

/** Screening lookup: re-check a digest with no uploaded content. */
export function verifyHash(hash: string) {
  const fd = form({ client_hash: hash });
  return request<ScreeningLookup>("/api/verify", { method: "POST", body: fd });
}

export function getBroadcasts(limit = 200) {
  return request<{ broadcasts: Broadcast[]; authed: boolean }>(`/api/broadcasts?limit=${limit}`);
}

export function deleteBroadcast(fileHash: string) {
  return request<{ status: string }>("/api/broadcasts/delete", {
    method: "POST",
    body: form({ file_hash: fileHash }),
  });
}

export function createBroadcast(title: string, urgency: string, message: string) {
  return request<{ ok: boolean; status: string; file_hash: string }>(
    "/api/broadcasts/create",
    { method: "POST", body: form({ broadcast_title: title, urgency_level: urgency, message }) },
  );
}

export function getAnalytics() {
  return request<AnalyticsPayload>("/api/analytics");
}

/** One round trip for the whole dashboard (tallies + latency + quota). */
export function getAnalyticsSummary() {
  return request<AnalyticsSummary>("/api/analytics/summary");
}

export interface LedgerAnchorStatus {
  anchored: boolean;
  status: string;
  in_sync: boolean;
  anchor_head_hash: string | null;
  current_db_head_hash: string | null;
  total_blocks: number;
  anchor_blocks: number;
  anchored_at: string | null;
  anchor_type: string | null;
  public_url: string | null;
  signature: string | null;
  manifest?: Record<string, unknown>;
}

export function getLedgerAnchor() {
  return request<LedgerAnchorStatus>("/api/screen/ledger/anchor");
}

export function triggerLedgerAnchor() {
  return request<{
    ok: boolean;
    status: string;
    head_hash: string;
    total_blocks: number;
    anchored_at: string;
    anchor_type: string;
    public_url: string;
    signature: string;
    manifest: Record<string, unknown>;
  }>("/api/screen/ledger/anchor", { method: "POST" });
}

export interface LedgerVerifyResult {
  valid: boolean;
  total_blocks: number;
  verified_blocks?: number;
  head_hash: string | null;
  genesis_hash: string;
  broken_at: string | null;
  reason?: string;
  status: string;
  anchor: {
    anchored: boolean;
    in_sync: boolean;
    anchor_head_hash?: string;
    anchor_type?: string;
    public_url?: string;
    anchored_at?: string;
    signature?: string;
    hint?: string;
  };
}

export function verifyLedgerChain() {
  return request<LedgerVerifyResult>("/api/screen/ledger/verify");
}

// ----------------------------------------------------------------------------
// Border screening SESSIONS (SIH26188) — one traveller per session.
// Documents are screened into a session one at a time, cross-compared for
// discrepancies, then approved (chained SHA-256 block into the ledger) or
// flagged for the supervisory review queue.
// ----------------------------------------------------------------------------

export type SessionStatus = "open" | "approved" | "flagged" | "rejected";
export type SessionVerdict = "PENDING" | "CLEAR" | "REVIEW" | "FLAGGED";

export type ComparisonStatus = "agree" | "disagree" | "cross-script" | "single" | "none";
export type ComparisonVerdict = "CONSISTENT" | "DISCREPANCY" | "INCOMPLETE";

export interface ComparisonCheck {
  field: string;
  label: string;
  status: ComparisonStatus;
  detail: string;
  docs: string[];
  mask?: string | null;
  masks?: Record<string, string | null> | null;
}

export interface ZkpGate {
  assertion: string;
  proven: boolean;
  method: string;
  status: string;
  zk_proof_hash?: string | null;
}

export interface SessionComparison {
  checks: ComparisonCheck[];
  verdict: ComparisonVerdict;
  risk_bump: number;
  zkp_gates?: Record<string, ZkpGate> | null;
}

export interface ScreeningSession {
  id: string;
  status: SessionStatus;
  verdict: SessionVerdict | null;
  risk_score: number | null;
  checkpoint: string;
  screener: string | null;
  /** Human label "Session N" per IST day (resets to 1 each day). */
  label?: string | null;
  comparison: SessionComparison | null;
  note: string;
  adjudicator: string | null;
  adjudicated_at: string | null;
  created_at: string;
  created_at_ist?: string | null;
  updated_at: string;
  closed_at: string | null;
  block_hash: string | null;
  prev_hash: string | null;
  document_count?: number;
  nationality?: string | null;
  purpose?: string | null;
  mode?: string | null;
  guide?: GuidedFlow | null;
}

export interface ScreeningSessionDetail extends ScreeningSession {
  documents: ScreenReport[];
  comparison: SessionComparison;
}

export interface SessionLedgerPayload {
  blocks: ScreeningSession[];
  head_hash: string | null;
  total_blocks: number;
}

export interface SessionLedgerVerify {
  valid: boolean;
  total_blocks: number;
  verified_blocks?: number;
  head_hash: string | null;
  broken_at: string | null;
  status: string;
  reason?: string;
}

export interface CheckpointCluster {
  key: string;
  label: string;
  mode: string;
  checkpoints: string[];
}

export interface CheckpointCatalog {
  checkpoints: {
    clusters: CheckpointCluster[];
    all: string[];
    modes: Record<string, string>;
  };
  documents: Record<string, { label: string; field: string; hint: string }>;
  nationalities: { code: string; label: string }[];
}

export interface GuidedStep {
  phase: string;
  order: number;
  text: string;
  detail?: string;
}

export interface GuidedFlow {
  checkpoint: string;
  cluster: string;
  cluster_label: string;
  mode: string;
  doc_type: string;
  doc_label: string;
  nationality: string;
  nationality_label: string;
  expected_documents: string[];
  officer_steps: GuidedStep[];
  traveller_steps: { order: number; text: string }[];
  capture_hint: string;
}

export interface StatsOverview {
  reports: {
    generated_at_utc: string;
    generated_at_ist: string;
    total_screens: number;
    verdicts: Record<string, number>;
    risk_buckets: Record<string, number>;
    by_doc_type: Record<string, { count: number; flagged: number; avg_risk: number }>;
    by_checkpoint: Record<string, { count: number; flagged: number }>;
    by_officer: Record<string, { count: number; flagged: number }>;
    modules: Record<string, Record<string, number>>;
    ai_detector?: { ran: number; suspected: number; score_sum: number };
    latency_ms: { min: number | null; max: number; sum: number; p50: number | null; p95: number | null };
    hourly_ist: Record<number, number>;
    daily?: Record<string, number>;
    flagged_count: number;
  };
  sessions: {
    total_sessions: number;
    by_status: Record<string, number>;
    by_verdict: Record<string, number>;
    avg_docs_per_session?: number;
  };
  throughput: {
    window_minutes: number;
    screenings_count: number;
    per_minute: number;
  };
}

export interface LiveExtractResult {
  ok: boolean;
  medium: string;
  fields: Record<string, any>;
  masked_fields: Record<string, string>;
  ocr: any;
  mrz: any;
  doc_type: string;
  has_face_frame: boolean;
  guidance: any;
}

/** Open a new border session for the person now at the desk. */
export function createSession(
  checkpointOrParams:
    | string
    | { checkpoint?: string; nationality?: string; purpose?: string; mode?: string },
) {
  const params =
    typeof checkpointOrParams === "string"
      ? { checkpoint: checkpointOrParams }
      : checkpointOrParams;
  return request<ScreeningSession>("/api/sessions", {
    method: "POST",
    body: form({
      checkpoint: params.checkpoint || "",
      nationality: params.nationality || "",
      purpose: params.purpose || "",
      mode: params.mode || "",
    }),
  });
}

/** Soft-remove a document from an open session while preserving the immutable audit ledger. */
export function removeSessionDocument(sessionId: string, reportId: string) {
  return request<{
    ok: boolean;
    already_removed: boolean;
    report_id: string;
    removed_at?: string;
    removed_at_ist?: string;
    removed_by?: string;
  }>(`/api/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(reportId)}/remove`, {
    method: "POST",
  });
}

/** Undo soft-removal while the session is still open. */
export function restoreSessionDocument(sessionId: string, reportId: string) {
  return request<{ ok: boolean; restored: boolean; report_id: string }>(
    `/api/sessions/${encodeURIComponent(sessionId)}/documents/${encodeURIComponent(reportId)}/restore`,
    { method: "POST" },
  );
}

/** Get checkpoint clusters, document catalog, and nationalities. */
export function getCheckpoints() {
  return request<CheckpointCatalog>("/api/checkpoints");
}

/** Get guided officer & traveller protocol for a specific checkpoint/doc/nationality. */
export function getGuide(checkpoint = "", docType = "other", nationality = "UNKNOWN") {
  const q = new URLSearchParams({
    checkpoint,
    doc_type: docType,
    nationality,
  });
  return request<GuidedFlow>(`/api/guide?${q.toString()}`);
}

/** Get border-wide screening statistics and operational health in IST. */
export function getStatsOverview() {
  return request<StatsOverview>("/api/stats/overview");
}

/** In-memory extraction of live document image (zero-storage). */
export function extractLiveImage(file: File, docType = "other", liveFrame?: File | null) {
  return request<LiveExtractResult>("/api/extract", {
    method: "POST",
    body: form({
      file,
      doc_type: docType,
      live_frame: liveFrame || undefined,
    }),
  });
}

/** List sessions (own lane; supervisors see the whole desk). */
export function getSessions(status?: string, checkpoint?: string) {
  const q: string[] = [];
  if (status) q.push(`status=${encodeURIComponent(status)}`);
  if (checkpoint) q.push(`checkpoint=${encodeURIComponent(checkpoint)}`);
  const url = q.length ? `/api/sessions?${q.join("&")}` : "/api/sessions";
  return request<{ sessions: ScreeningSession[] }>(url);
}

/** Full session detail: documents + live cross-document comparison. */
export function getSession(sessionId: string) {
  return request<ScreeningSessionDetail>(
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
}

/** Desk officer closes the session: 'approve' signs it into the ledger;
 *  'flag' routes it to the supervisory review queue; 'close' closes an unused 0-doc session. */
export function closeSession(sessionId: string, verdict: "approve" | "flag" | "close", note?: string) {
  return request<ScreeningSessionDetail>(
    `/api/sessions/${encodeURIComponent(sessionId)}/close`,
    { method: "POST", body: form({ verdict, note: note || "" }) },
  );
}

/** Close all unused sessions with 0 documents in one click. */
export function closeUnusedSessions() {
  return request<{ ok: boolean; closed_count: number }>("/api/sessions/close-unused", {
    method: "POST",
  });
}

/** Supervisory officer settles a FLAGGED session (CLEARED / CONFIRMED_FRAUD / INCONCLUSIVE). */
export function adjudicateSession(
  sessionId: string,
  decision: "CLEARED" | "CONFIRMED_FRAUD" | "INCONCLUSIVE",
  note?: string,
) {
  return request<ScreeningSessionDetail>(
    `/api/sessions/${encodeURIComponent(sessionId)}/adjudicate`,
    { method: "POST", body: form({ decision, note: note || "" }) },
  );
}

/** Signed session blocks (the border ledger), oldest first. */
export function getSessionLedger() {
  return request<SessionLedgerPayload>("/api/sessions/ledger/blocks");
}

/** Tamper-check the whole session ledger end to end. */
export function verifySessionLedger() {
  return request<SessionLedgerVerify>("/api/sessions/ledger/verify");
}

export interface ChatResponse {
  ok: boolean;
  answer?: string;
  reason?: string;
  message?: string;
}

/** AI project assistant / technical oracle chat. */
export async function chatWithAssistant(message: string, history?: { role: string; text: string }[]): Promise<ChatResponse> {
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ message, history: history || [] }),
    });
    if (!res.ok) {
      return { ok: false, reason: `HTTP ${res.status}` };
    }
    const data = await res.json();
    return data as ChatResponse;
  } catch (err) {
    return { ok: false, reason: err instanceof Error ? err.message : "network_error" };
  }
}

export interface MlHealthStatus {
  status: "online" | "sleeping" | "offline" | "unconfigured";
  configured: boolean;
  url?: string;
  latency_ms?: number;
  models?: Record<string, boolean | string>;
  message?: string;
}

/** Check remote ML microservice health status. */
export function getMlStatus() {
  return request<MlHealthStatus>("/api/ml/status", { method: "GET" }, 10000);
}

/** Send lightweight keepalive ping to prevent Hugging Face Space from sleeping. */
export function pingMlKeepAlive() {
  return request<MlHealthStatus>("/api/ml/keepalive/ping", { method: "POST" }, 15000);
}

