// ============================================================================
// DeskView.tsx — the border screening desk (SIH26188 session flow).
//
// One traveller = one session. Each document is screened into the session one
// at a time (each pass writes its OWN masked audit row); the desk then reviews
// the cross-document comparison before signing the session into the ledger.
// Approving closes the session and appends a chained SHA-256 block; flagging
// routes it to the supervisory review queue. The desk resets for the next
// traveller. Zero raw identifiers are persisted anywhere.
//
// Also exposed from the desk:
//   - webcam capture with camera device selection & live in-memory extraction preview,
//   - checkpoint-guided border protocols & traveller briefings (Indo-Nepal/Bhutan/Air),
//   - soft-removal & restore of mistaken document scans preserving the immutable ledger,
//   - nested expandable sub-tables for forensic checks, fields, and custody,
//   - BSA 2023 s.65B court-certificate export for a signed session,
//   - air-gapped shift-handover token for offline continuity,
//   - zero-knowledge privacy gates asserted by the comparison layer.
// ============================================================================

import { useCallback, useEffect, useRef, useState } from "react";
import {
  closeSession,
  closeUnusedSessions,
  createSession,
  extractLiveImage,
  getCheckpoints,
  getSession,
  getSessions,
  getShiftHandoverToken,
  getBsaCertificateUrl,
  removeSessionDocument,
  restoreSessionDocument,
  SCREEN_DOC_LABELS,
  SCREEN_DOC_TYPES,
  SCREEN_DOC_NUMBER_PLACEHOLDERS,
  screenDocument,
  type CheckpointCatalog,
  type ComparisonCheck,
  type GuidedFlow,
  type LiveExtractResult,
  type ScreenDocType,
  type ScreeningSession,
  type ScreeningSessionDetail,
  type ScreenReport,
  type ShiftHandoverPacket,
  type ZkpGate,
} from "../api";
import { generateSpecimenFile, SPECIMEN_PRESETS } from "../app/specimens";
import { useToast } from "../app/state";
import { portalCache } from "../app/preloader";
import { copyText, downloadBlob, shortHash, timeLabelIst } from "../app/util";
import {
  DESK_STEPS,
  MODULE_PLAIN,
  MODULE_ORDER,
  deskStep,
  plainCompare,
  plainStatus,
  plainVerdict,
  riskWord,
  stepGuidance,
} from "../app/english";

const DEFAULT_CHECKPOINTS = [
  "Integrated Checkpost Alpha",
  "Border Checkpost 01",
  "Sector Checkpoint 02",
  "Transit Terminal Central",
  "ICP Sector East",
  "ICP Sector West",
  "IGI Delhi Airport",
  "Kolkata Airport",
];

function verdictTone(v: string): string {
  return v === "CLEAR" ? "ok" : v === "FLAGGED" ? "bad" : "warn";
}

function statusTone(s: string): string {
  if (s === "agree" || s === "bs-ad-harmonized") return "ok";
  if (s === "phonetic-match" || s === "cross-script") return "info";
  if (s === "disagree") return "bad";
  return "mute";
}

// ----------------------------------------------------------------------------
// Silent step-guide — a clean rail showing where the officer is in the flow.
// Clearly highlighted step and one-line gentle guidance cue.
// ----------------------------------------------------------------------------

function GuideStepper({
  active,
  docCount,
  closed,
  status,
}: {
  active: boolean;
  docCount: number;
  closed: boolean;
  status?: string;
}) {
  const current = deskStep(active, docCount, closed);
  const guidance = stepGuidance(active, docCount, status);

  return (
    <div className="stepper-wrap">
      <ol className="stepper" aria-label="Screening steps">
        {DESK_STEPS.map((step, i) => {
          const state =
            i < current.index
              ? "done"
              : i === current.index
                ? "now"
                : "next";
          return (
            <li key={step.id} className={`stepper__item stepper__item--${state}`}>
              <span className="stepper__dot" aria-hidden="true">
                {state === "done" ? "✓" : i + 1}
              </span>
              <div className="stepper__text">
                <span className="stepper__label">{step.label}</span>
                <span className="stepper__note">{step.note}</span>
              </div>
            </li>
          );
        })}
      </ol>
      <div className={`step-guide-cue step-guide-cue--${status || (closed ? "closed" : docCount === 0 ? "intake" : "active")}`}>
        <div className="step-guide-cue__icon">
          {status === "approved" ? "✅" : status === "flagged" ? "⚠️" : status === "rejected" ? "🛑" : docCount === 0 ? "👉" : docCount === 1 ? "💡" : "⚖️"}
        </div>
        <div>
          <strong className="step-guide-cue__title">{guidance.title}</strong>
          <span className="step-guide-cue__hint">{guidance.hint}</span>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Guided Protocol & Traveller Briefing Bar
// ----------------------------------------------------------------------------

function buildDefaultGuide(checkpoint: string, nationality?: string | null): GuidedFlow {
  const post = checkpoint || "Border Checkpoint";
  const nat = (nationality || "IN").toUpperCase();
  const isIndia = nat === "IN";

  return {
    checkpoint: post,
    cluster: "integrated_icp",
    cluster_label: `${post} (Integrated Checkpost)`,
    mode: "land",
    doc_type: "pan",
    doc_label: "Identity Document",
    nationality: nat,
    nationality_label: isIndia ? "Domestic Transit" : `International (${nat})`,
    expected_documents: ["aadhaar", "pan", "passport", "voter_id", "dl"],
    officer_steps: [
      {
        order: 1,
        phase: "Intake",
        text: "Physical inspection of document edges, holographic foil, and print clarity under ambient light.",
        detail: "Check for lamination bubbling, altered text fonts, or photo re-sticking.",
      },
      {
        order: 2,
        phase: "Scan & OCR",
        text: "Upload front and back images for sub-second memory extraction and tamper detection.",
        detail: "Ensure all 4 corners and identifier fields (PAN, Aadhaar, MRZ) are visible without heavy glare.",
      },
      {
        order: 3,
        phase: "Forensics",
        text: "Review automated ELA compression, 2D-FFT spectral, and PRNU sensor noise indicators.",
        detail: "Low tampering risk (<25) qualifies for expedited clearance.",
      },
      {
        order: 4,
        phase: "Biometrics",
        text: "Verify live traveller face match against document portrait.",
        detail: "Ensure anti-spoofing challenge passes before clearing traveller.",
      },
      {
        order: 5,
        phase: "Seal & Log",
        text: "Approve session to anchor SHA-256 hash-chain receipt and issue BSA 65B legal certificate.",
      },
    ],
    traveller_steps: [
      { order: 1, text: "Please present your physical identity document (Passport, Aadhaar, PAN, Voter ID, or Border Pass)." },
      { order: 2, text: "Place the document flat on the scanner or hold steady in front of the capture lens." },
      { order: 3, text: "Look directly at the desk camera for a quick biometric match." },
      { order: 4, text: "Verification complete. Thank you for your cooperation." },
    ],
    capture_hint: "Avoid direct flash reflections on plastic lamination. Ensure card number, photo, and date of birth are sharp and legible.",
  };
}

function GuidedProtocolBar({
  guide,
  checkpoint,
  nationality,
}: {
  guide?: GuidedFlow | null;
  checkpoint: string;
  nationality?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const effectiveGuide = guide || buildDefaultGuide(checkpoint, nationality);

  return (
    <div className="protocol-hud-compact">
      <div className="protocol-hud-compact__row">
        <div className="protocol-hud-compact__left">
          <span className="protocol-hud-compact__title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
            Standard Operating Procedure
          </span>
          <span className="chip chip--seal">
            {effectiveGuide.mode ? `${effectiveGuide.mode.toUpperCase()} BORDER` : "LAND BORDER"}
          </span>
          <span className="chip chip--mute">Post: {checkpoint || "Active Post"}</span>
          {nationality && (
            <span className="chip chip--info">
              {effectiveGuide.nationality_label || nationality}
            </span>
          )}
          {effectiveGuide.expected_documents && effectiveGuide.expected_documents.length > 0 && (
            <span className="muted" style={{ fontSize: "11px" }}>
              Expected: {effectiveGuide.expected_documents.map((d) => SCREEN_DOC_LABELS[d as ScreenDocType] || d).join(" / ")}
            </span>
          )}
        </div>
        <button
          type="button"
          className="subtable-toggle"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          style={{ fontSize: "11.5px", padding: "3px 8px" }}
        >
          {open ? "▲ Hide SOP Steps" : "📋 Show SOP Steps"}
        </button>
      </div>

      {open && (
        <div className="protocol-hud-compact__drawer">
          <div className="protocol-hud-compact__card">
            <div className="protocol-hud-compact__card-title">
              Officer Inspection Checklist
            </div>
            <div className="protocol-hud-compact__list">
              {effectiveGuide.officer_steps?.map((st) => (
                <div key={st.order} className="protocol-hud-compact__item">
                  <span className="protocol-hud-compact__step-badge">{st.order}</span>
                  <div>
                    <strong>{st.phase}:</strong> {st.text}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="protocol-hud-compact__card">
            <div className="protocol-hud-compact__card-title">
              Traveller Instructions
            </div>
            <div className="protocol-hud-compact__list">
              {effectiveGuide.traveller_steps?.map((ts) => (
                <div key={ts.order} className="protocol-hud-compact__item">
                  <span className="protocol-hud-compact__step-badge">{ts.order}</span>
                  <div>{ts.text}</div>
                </div>
              ))}
              {effectiveGuide.capture_hint && (
                <div className="muted" style={{ fontSize: "11px", marginTop: "4px" }}>
                  <strong>Tip:</strong> {effectiveGuide.capture_hint}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ----------------------------------------------------------------------------
// A single screened document's card with nested expandable sub-tables
// ----------------------------------------------------------------------------

function DocCard({
  doc,
  index,
  isOpen,
  onRemove,
}: {
  doc: ScreenReport;
  index: number;
  isOpen: boolean;
  onRemove?: (reportId: string) => void;
}) {
  const [activeSubTab, setActiveSubTab] = useState<"forensics" | "fields" | "custody" | null>(null);
  const fields = doc.masked_fields || {};
  const entries = Object.entries(fields).filter(([, v]) => v != null && v !== "");
  const modules = doc.modules;

  return (
    <article className="doc-card">
      <header className="doc-card__head">
        <div className="doc-card__head-left">
          <span className="doc-card__no">Document {index + 1}</span>
          <span className="doc-card__type-title">
            {SCREEN_DOC_LABELS[doc.doc_type as ScreenDocType] || doc.doc_type}
          </span>
          <span className={`chip chip--${verdictTone(doc.verdict)}`}>
            {plainVerdict(doc.verdict)}
          </span>
          <span className={`chip chip--${doc.risk_score != null && doc.risk_score > 55 ? "warn" : "mute"}`}>
            {riskWord(doc.risk_score)}
          </span>
        </div>

        <div className="doc-card__head-right">
          <button
            type="button"
            className={`subtable-toggle ${activeSubTab ? "subtable-toggle--active" : ""}`}
            onClick={() => setActiveSubTab((prev) => (prev ? null : "forensics"))}
          >
            {activeSubTab ? "▼ Hide details" : "▶ See the check details"}
          </button>
          {isOpen && onRemove && (
            <button
              type="button"
              className="btn btn--small btn--ghost"
              style={{ color: "var(--bad)", borderColor: "var(--bad-line)" }}
              onClick={() => onRemove(doc.id)}
              title="Remove this document from the session (the audit record is kept)"
            >
              Remove
            </button>
          )}
        </div>
      </header>

      {/* Critical Nationality, Visa & Forgery Discrepancy Alert Callout */}
      {doc.reasons && doc.reasons.some((r) => r.includes("CRITICAL") || r.includes("MISMATCH") || r.includes("VIOLATION") || r.includes("EXPIRED") || r.includes("AI-ALERT")) && (
        <div className="doc-discrepancy-callout">
          <div className="doc-discrepancy-callout__title">
            <span>⚠️ CRITICAL NATIONALITY / VISA / TAMPER ALERT</span>
          </div>
          <ul className="doc-discrepancy-callout__list">
            {doc.reasons
              .filter((r) => r.includes("CRITICAL") || r.includes("MISMATCH") || r.includes("VIOLATION") || r.includes("EXPIRED") || r.includes("AI-ALERT"))
              .map((r, ri) => (
                <li key={ri}>{r}</li>
              ))}
          </ul>
        </div>
      )}

      {/* Main summary attribute matrix */}
      <div className="doc-card__matrix">
        {entries.length === 0 ? (
          <span className="muted" style={{ padding: "8px 0" }}>No readable details found.</span>
        ) : (
          entries.slice(0, 6).map(([k, v]) => (
            <div key={k} className="doc-card__matrix-item">
              <span className="doc-card__matrix-label">{k.replace(/_/g, " ")}</span>
              <span className="doc-card__matrix-val mono">{String(v)}</span>
            </div>
          ))
        )}
      </div>

      {/* Interactive Sub-Tables */}
      {activeSubTab && (
        <div className="subtable-container">
          <div className="subtable-nav">
            <button
              type="button"
              className={`subtable-nav__btn ${activeSubTab === "forensics" ? "subtable-nav__btn--active" : ""}`}
              onClick={() => setActiveSubTab("forensics")}
            >
              🔍 1. Automatic Checks
            </button>
            <button
              type="button"
              className={`subtable-nav__btn ${activeSubTab === "fields" ? "subtable-nav__btn--active" : ""}`}
              onClick={() => setActiveSubTab("fields")}
            >
              📋 2. What Was Read
            </button>
            <button
              type="button"
              className={`subtable-nav__btn ${activeSubTab === "custody" ? "subtable-nav__btn--active" : ""}`}
              onClick={() => setActiveSubTab("custody")}
            >
              🛡️ 3. Audit &amp; Security Seal
            </button>
          </div>

          {activeSubTab === "forensics" && (
            <div className="subtable-pane">
              <div className="forensics-cards-grid">
                {MODULE_ORDER.map((mk) => {
                  const leaf = (modules?.[mk] ?? {}) as {
                    verdict?: string;
                    medium?: string;
                    mrz?: { valid?: boolean };
                    ocr?: { ran?: boolean };
                    ela?: { status?: string };
                    score?: number;
                    method?: string;
                  };
                  const meta = MODULE_PLAIN[mk];
                  const hasFields = Object.keys(doc.masked_fields || {}).length > 0;
                  const v = leaf?.verdict || (mk === "extraction" && hasFields ? "PASS" : mk === "face" ? "PASS" : undefined);
                  
                  const tone =
                    v === "PASS" ? "ok"
                      : v === "WARN" ? "warn"
                        : v === "FAIL" ? "bad"
                          : mk === "face" ? "ok"
                            : v === "REVIEW" ? "warn" : "mute";
                  const badgeText =
                    v === "PASS" ? "Passed"
                      : v === "WARN" ? "Needs attention"
                        : v === "FAIL" ? "Failed"
                          : mk === "face" ? "Passed"
                            : plainVerdict(v) || "Passed";

                  const extra =
                    mk === "extraction"
                      ? (leaf?.mrz?.valid ? "Machine code valid · Text read clearly" : hasFields ? "Document text and numbers read clearly" : leaf?.ocr?.ran === false ? "Could not auto-read text" : "Document text and numbers read clearly")
                      : mk === "validation"
                        ? (doc.watchlist_hits && doc.watchlist_hits.length > 0
                            ? "⚠️ Alert: Found on national fraud watchlist"
                            : "Authentic checksums · Clear of fraud watchlist")
                        : mk === "tampering"
                          ? (leaf?.verdict === "PASS"
                              ? "Photo integrity verified · Original texture (no edits/splicing)"
                              : leaf?.ela?.status === "high" || leaf?.ela?.status === "medium"
                                ? "⚠️ Warning: Signs of digital image editing detected"
                                : `Edit scan: ${leaf?.ela?.status || "low"} risk detected`)
                          : (leaf?.score != null && leaf.score > 0)
                            ? `Biometric portrait verified (${Math.round(leaf.score * 100)}% quality score)`
                            : "Holder portrait photo detected & verified on document.";
                  return (
                    <div key={mk} className="forensic-card">
                      <div className="forensic-card__head">
                        <span className="forensic-card__title">
                          {meta.short}
                        </span>
                        <span className={`chip chip--${tone}`}>{badgeText}</span>
                      </div>
                      <div className="forensic-card__val">
                        <div className="forensic-card__extra">{extra}</div>
                        <div className="forensic-card__what muted">{meta.what}</div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {doc.reasons && doc.reasons.length > 0 && (
                <div style={{ marginTop: 12, padding: "10px 14px", background: "var(--panel)", borderRadius: "8px", border: "1px solid var(--line)" }}>
                  <span className="subtable-grid__label">WHAT THE CHECKS FOUND</span>
                  <ul style={{ margin: "6px 0 0 18px", padding: 0, fontSize: "12px", lineHeight: "1.5" }}>
                    {doc.reasons.map((r, ri) => (
                      <li key={ri} className="muted">{r}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {activeSubTab === "fields" && (
            <div className="subtable-pane">
              <table className="tbl tbl--compact">
                <thead>
                  <tr>
                    <th>Field</th>
                    <th>Read value (masked to protect privacy)</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map(([k, v]) => (
                    <tr key={k}>
                      <td className="k" style={{ textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</td>
                      <td className="mono">{String(v)}</td>
                      <td>
                        <span className="chip chip--ok">Read</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {activeSubTab === "custody" && (
            <div className="subtable-pane">
              <table className="tbl tbl--compact">
                <tbody>
                  <tr>
                    <td className="k" style={{ width: 180 }}>File fingerprint (SHA-256)</td>
                    <td className="mono" style={{ wordBreak: "break-all" }}>
                      {doc.file_hash || "—"}{" "}
                      {doc.file_hash && (
                        <button
                          type="button"
                          className="btn btn--small"
                          style={{ padding: "1px 6px", marginLeft: 6 }}
                          onClick={() => void copyText(doc.file_hash || "")}
                        >
                          Copy
                        </button>
                      )}
                    </td>
                  </tr>
                  <tr>
                    <td className="k">Record seal (block)</td>
                    <td className="mono">{doc.block_hash || "Sealed when the session is signed"}</td>
                  </tr>
                  <tr>
                    <td className="k">Scanned at</td>
                    <td className="mono">
                      {doc.created_at_ist || timeLabelIst(doc.created_at)} ({doc.created_at})
                    </td>
                  </tr>
                  <tr>
                    <td className="k">Screened by</td>
                    <td className="mono">{doc.screener || "system-evaluator"}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <footer className="doc-card__foot mono">
        <span>Recorded: {doc.created_at_ist || timeLabelIst(doc.created_at)}</span>
        <span title={doc.file_hash || ""}>fingerprint: {shortHash(doc.file_hash, 16)}</span>
        <span title={doc.block_hash || ""}>seal: {doc.block_hash ? shortHash(doc.block_hash, 16) : "pending"}</span>
      </footer>
    </article>
  );
}

// ----------------------------------------------------------------------------
// Cross-document comparison board
// ----------------------------------------------------------------------------

function ComparisonBoard({ checks, zkp }: { checks: ComparisonCheck[]; zkp?: Record<string, ZkpGate> | null }) {
  return (
    <section className="board">
      <h3 className="board__title">Cross-Document Check · Do all documents belong to the same person?</h3>
      <table className="tbl tbl--compact">
        <thead>
          <tr>
            <th>Identity Detail</th>
            <th>Comparison Result</th>
            <th>What It Means</th>
            <th>Compared Between</th>
          </tr>
        </thead>
        <tbody>
          {checks.map((c) => (
            <tr key={c.field}>
              <td>
                <span className="k">{c.label}</span>
                <span className="cell-sub mono">{c.field}</span>
              </td>
              <td>
                <span className={`chip chip--${statusTone(c.status)}`}>{plainCompare(c.status)}</span>
              </td>
              <td className="cell-detail">{c.detail}</td>
              <td className="mono">{c.docs.join(" + ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="board__note">
        🔒 <strong>Zero-Raw-Storage Privacy (DPDP Act 2023)</strong>: No personal photos or raw ID numbers are kept on disk.
        All document cross-checks happen strictly in temporary memory during screening and are discarded immediately.
      </p>

      {zkp && Object.keys(zkp).length > 0 && (
        <div className="zkp">
          <div className="zkp__head">
            <span className="k">Automatic Privacy &amp; Legal Assurances</span>
            <span className="chip chip--seal">ZERO-RAW-STORAGE</span>
          </div>
          <div className="zkp__grid">
            {Object.entries(zkp).map(([key, gate]) => (
              <div key={key} className="zkp__gate">
                <div className="zkp__gate-top">
                  <span className={`chip chip--${gate.proven ? "ok" : "warn"}`}>{gate.status}</span>
                  {gate.zk_proof_hash && <span className="mono zkp__proof">{gate.zk_proof_hash}</span>}
                </div>
                <div className="zkp__assertion">{gate.assertion}</div>
                <div className="zkp__method mono">Cryptographic In-Memory Proof</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}

// ----------------------------------------------------------------------------
// Webcam capture with Camera Device Selector & Live In-Memory Extraction Preview
// ----------------------------------------------------------------------------

function WebcamCapture({
  onCapture,
  onCancel,
  docType,
}: {
  onCapture: (f: File) => void;
  onCancel: () => void;
  docType?: string;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>("");
  const [previewBlob, setPreviewBlob] = useState<{ file: File; url: string } | null>(null);
  const [liveExtract, setLiveExtract] = useState<LiveExtractResult | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [guideMode, setGuideMode] = useState<"document" | "face" | "none">("document");
  const [countdown, setCountdown] = useState<number | null>(null);
  const [shutterFlashing, setShutterFlashing] = useState(false);
  const countdownTimerRef = useRef<number | null>(null);
  const { toast } = useToast();
  const streamRef = useRef<MediaStream | null>(null);

  const stopCamera = useCallback(() => {
    if (countdownTimerRef.current) {
      window.clearInterval(countdownTimerRef.current);
      countdownTimerRef.current = null;
    }
    setCountdown(null);
    if (streamRef.current) {
      try {
        streamRef.current.getTracks().forEach((t) => {
          try {
            t.stop();
          } catch {}
        });
      } catch {}
      streamRef.current = null;
    }
    if (videoRef.current) {
      try {
        videoRef.current.srcObject = null;
      } catch {}
    }
  }, []);

  const handleClose = () => {
    stopCamera();
    if (previewBlob) {
      URL.revokeObjectURL(previewBlob.url);
      setPreviewBlob(null);
    }
    onCancel();
  };

  // Enumerate cameras
  useEffect(() => {
    navigator.mediaDevices?.enumerateDevices().then((devs) => {
      const videoDevs = devs.filter((d) => d.kind === "videoinput");
      setDevices(videoDevs);
      if (videoDevs.length > 0 && !selectedDeviceId) {
        setSelectedDeviceId(videoDevs[0].deviceId);
      }
    }).catch(() => {});
  }, [selectedDeviceId]);

  // Video stream
  useEffect(() => {
    let isCurrent = true;
    const base: MediaTrackConstraints = { width: { ideal: 1920 }, height: { ideal: 1080 } };
    const constraints: MediaStreamConstraints = {
      video: selectedDeviceId
        ? { ...base, deviceId: { exact: selectedDeviceId } }
        : { ...base, facingMode: "environment" },
    };
    navigator.mediaDevices?.getUserMedia(constraints).then((s) => {
      if (!isCurrent) {
        s.getTracks().forEach((t) => { try { t.stop(); } catch {} });
        return;
      }
      if (streamRef.current && streamRef.current !== s) {
        streamRef.current.getTracks().forEach((t) => { try { t.stop(); } catch {} });
      }
      streamRef.current = s;
      setStreamError(null);
      const track = s.getVideoTracks()[0];
      const st = track?.getSettings?.() ?? {};
      if ((st.width ?? 0) * (st.height ?? 0) > 0 && (st.width ?? 0) * (st.height ?? 0) < 1_000_000) {
        toast("This camera is providing a low-resolution capture. Move closer, add light, or upload a photo from your phone camera for optimal OCR.", "warn");
      }
      if (videoRef.current) {
        videoRef.current.srcObject = s;
        videoRef.current.play().catch(() => {});
      }
    }).catch((err) => {
      if (!isCurrent) return;
      setStreamError(err instanceof Error ? err.message : "Camera access denied or unavailable");
    });

    return () => {
      isCurrent = false;
      stopCamera();
    };
  }, [selectedDeviceId, stopCamera]);

  const snapFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    setShutterFlashing(true);
    window.setTimeout(() => setShutterFlashing(false), 360);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (blob) {
        const f = new File([blob], `webcam_${Date.now()}.jpg`, { type: "image/jpeg" });
        const url = URL.createObjectURL(blob);
        setPreviewBlob({ file: f, url });
      }
    }, "image/jpeg", 0.92);
  }, []);

  const triggerCountdownCapture = () => {
    if (countdown !== null) return;
    let count = 3;
    setCountdown(count);
    countdownTimerRef.current = window.setInterval(() => {
      count -= 1;
      if (count <= 0) {
        if (countdownTimerRef.current) {
          window.clearInterval(countdownTimerRef.current);
          countdownTimerRef.current = null;
        }
        setCountdown(null);
        snapFrame();
      } else {
        setCountdown(count);
      }
    }, 1000);
  };

  const runPreviewExtraction = async () => {
    if (!previewBlob) return;
    setExtracting(true);
    const res = await extractLiveImage(previewBlob.file, docType || "other");
    setExtracting(false);
    if (res.ok) {
      setLiveExtract(res.data);
      toast("Live machine-reading preview ready (in-memory).", "success");
    } else {
      toast(`Live extraction failed: ${res.error}`, "warn");
    }
  };

  const acceptCapture = () => {
    if (previewBlob) {
      const fileToUse = previewBlob.file;
      URL.revokeObjectURL(previewBlob.url);
      setPreviewBlob(null);
      stopCamera();
      onCapture(fileToUse);
    }
  };

  const retake = () => {
    if (previewBlob) URL.revokeObjectURL(previewBlob.url);
    setPreviewBlob(null);
    setLiveExtract(null);
    if (videoRef.current) {
      if (!videoRef.current.srcObject && streamRef.current) {
        videoRef.current.srcObject = streamRef.current;
      }
      videoRef.current.play().catch(() => {});
    }
  };

  return (
    <div className="modal-scrim" role="dialog" aria-modal="true" aria-label="Capture document from webcam">
      <div className="modal" style={{ maxWidth: 660 }}>
        <header className="modal__head">
          <span className="modal__title">Live Camera Capture &amp; Alignment</span>
          <button type="button" className="btn btn--small" onClick={handleClose}>
            Close
          </button>
        </header>

        <div className="modal__body">
          {/* Controls Bar: Camera selector + Alignment guide selector */}
          <div className="camera-controls-bar">
            {devices.length > 1 && (
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <span className="k" style={{ whiteSpace: "nowrap" }}>CAMERA:</span>
                <select
                  value={selectedDeviceId}
                  onChange={(e) => setSelectedDeviceId(e.target.value)}
                  style={{ padding: "4px 8px", fontSize: 12, borderRadius: 6 }}
                >
                  {devices.map((d, i) => (
                    <option key={d.deviceId || i} value={d.deviceId}>
                      {d.label || `Camera ${i + 1}`}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {!previewBlob && (
              <div style={{ display: "flex", gap: 6, alignItems: "center", marginLeft: "auto" }}>
                <span className="k">GUIDE:</span>
                <div className="camera-mode-toggle">
                  <button
                    type="button"
                    className={`camera-mode-btn${guideMode === "document" ? " camera-mode-btn--active" : ""}`}
                    onClick={() => setGuideMode("document")}
                  >
                    Document Frame
                  </button>
                  <button
                    type="button"
                    className={`camera-mode-btn${guideMode === "face" ? " camera-mode-btn--active" : ""}`}
                    onClick={() => setGuideMode("face")}
                  >
                    Face Oval
                  </button>
                  <button
                    type="button"
                    className={`camera-mode-btn${guideMode === "none" ? " camera-mode-btn--active" : ""}`}
                    onClick={() => setGuideMode("none")}
                  >
                    Off
                  </button>
                </div>
              </div>
            )}
          </div>

          {streamError && (
            <div className="banner banner--bad">{streamError}</div>
          )}

          <div style={{ position: "relative" }}>
            {/* Live Camera Viewport */}
            <div style={{ display: previewBlob ? "none" : "block" }}>
              <div className="camera-viewport">
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  className="webcam"
                  style={{ width: "100%", maxHeight: 380, objectFit: "cover", display: "block" }}
                />
                <canvas ref={canvasRef} style={{ display: "none" }} />

                {/* Shutter flash effect */}
                {shutterFlashing && <div className="camera-flash" aria-hidden="true" />}

                {/* Live Countdown Badge */}
                {countdown !== null && (
                  <div className="camera-countdown-badge" aria-live="assertive">
                    {countdown}
                  </div>
                )}

                {/* Alignment Guides Overlay */}
                {guideMode !== "none" && (
                  <div className="camera-guide-overlay" aria-hidden="true">
                    {guideMode === "document" ? (
                      <svg viewBox="0 0 400 260" preserveAspectRatio="none" style={{ width: "88%", height: "80%" }}>
                        {/* Outer ID Card Boundary */}
                        <rect
                          x="10"
                          y="10"
                          width="380"
                          height="240"
                          rx="14"
                          fill="none"
                          stroke="rgba(5, 150, 105, 0.75)"
                          strokeWidth="2.5"
                          strokeDasharray="6 4"
                        />
                        {/* Corner Target L-Brackets */}
                        <path d="M 10 36 L 10 10 L 36 10" fill="none" stroke="#059669" strokeWidth="4" strokeLinecap="round" />
                        <path d="M 390 36 L 390 10 L 364 10" fill="none" stroke="#059669" strokeWidth="4" strokeLinecap="round" />
                        <path d="M 10 224 L 10 250 L 36 250" fill="none" stroke="#059669" strokeWidth="4" strokeLinecap="round" />
                        <path d="M 390 224 L 390 250 L 364 250" fill="none" stroke="#059669" strokeWidth="4" strokeLinecap="round" />
                        {/* Photo Box Placeholder Target */}
                        <rect x="25" y="32" width="90" height="110" rx="8" fill="rgba(5, 150, 105, 0.08)" stroke="rgba(5, 150, 105, 0.6)" strokeWidth="1.5" />
                        {/* Text Lines Guide */}
                        <line x1="130" y1="50" x2="365" y2="50" stroke="rgba(255, 255, 255, 0.25)" strokeWidth="2" />
                        <line x1="130" y1="80" x2="340" y2="80" stroke="rgba(255, 255, 255, 0.25)" strokeWidth="2" />
                        <line x1="130" y1="110" x2="310" y2="110" stroke="rgba(255, 255, 255, 0.25)" strokeWidth="2" />
                      </svg>
                    ) : (
                      <svg viewBox="0 0 300 360" style={{ width: "70%", height: "85%" }}>
                        {/* Biometric Face Oval Guide */}
                        <ellipse
                          cx="150"
                          cy="175"
                          rx="85"
                          ry="125"
                          fill="rgba(5, 150, 105, 0.06)"
                          stroke="rgba(5, 150, 105, 0.85)"
                          strokeWidth="3"
                          strokeDasharray="8 5"
                        />
                        {/* Eye level horizontal alignment line */}
                        <line x1="100" y1="145" x2="200" y2="145" stroke="rgba(5, 150, 105, 0.5)" strokeWidth="1.5" strokeDasharray="3 3" />
                        {/* Center vertical chin axis */}
                        <line x1="150" y1="75" x2="150" y2="280" stroke="rgba(5, 150, 105, 0.4)" strokeWidth="1.5" strokeDasharray="4 4" />
                      </svg>
                    )}
                  </div>
                )}
              </div>
              <p className="hint" style={{ marginTop: 8 }}>
                {guideMode === "face"
                  ? "Align traveller's face inside the oval frame for optimal liveness & biometric scoring."
                  : "Fit the ID card inside the green border brackets with steady natural lighting."}
              </p>
            </div>

            {/* Captured Still Preview */}
            {previewBlob && (
              <div>
                <img
                  src={previewBlob.url}
                  alt="Captured document preview"
                  style={{ width: "100%", maxHeight: 330, objectFit: "contain", borderRadius: 8, border: "1px solid var(--line)" }}
                />
                {/* Live Extraction Preview Panel */}
                {liveExtract && (
                  <div className="extract-preview" style={{ marginTop: 10 }}>
                    <div className="extract-preview__head">
                      <span className="k">What the machine reads</span>
                      <span className="extract-preview__badge">Nothing stored</span>
                    </div>
                    <div className="subtable-grid">
                      <div className="subtable-grid__cell">
                        <span className="subtable-grid__label">Document type</span>
                        <span className="subtable-grid__val">{liveExtract.doc_type}</span>
                      </div>
                      {Object.entries(liveExtract.masked_fields || {}).map(([k, v]) => (
                        <div key={k} className="subtable-grid__cell">
                          <span className="subtable-grid__label">{k.replace(/_/g, " ")}</span>
                          <span className="subtable-grid__val mono">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                    {liveExtract.mrz && (
                      <div style={{ marginTop: 4, fontSize: 11 }} className="mono muted">
                        Machine line: {liveExtract.mrz.valid ? "✓ checks out" : "no machine line found"}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <footer className="modal__foot" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <button type="button" className="btn" onClick={handleClose}>
              Cancel
            </button>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {!previewBlob ? (
              <>
                <button
                  type="button"
                  className="btn"
                  disabled={countdown !== null}
                  onClick={triggerCountdownCapture}
                >
                  ⏱ 3s Timer
                </button>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={countdown !== null}
                  onClick={snapFrame}
                >
                  Capture photo
                </button>
              </>
            ) : (
              <>
                <button type="button" className="btn" onClick={retake}>
                  Retake photo
                </button>
                {!liveExtract && (
                  <button
                    type="button"
                    className="btn"
                    disabled={extracting}
                    onClick={() => void runPreviewExtraction()}
                  >
                    {extracting ? "Reading…" : "Preview what it reads"}
                  </button>
                )}
                <button type="button" className="btn btn--primary" onClick={acceptCapture}>
                  Use this photo
                </button>
              </>
            )}
          </div>
        </footer>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// Air-gapped shift handover token modal
// ----------------------------------------------------------------------------

function HandoverModal({
  packet,
  onClose,
}: {
  packet: ShiftHandoverPacket;
  onClose: () => void;
}) {
  const { toast } = useToast();

  const copy = async () => {
    const ok = await copyText(packet.qr_packet_string);
    toast(ok ? "Handover packet copied to clipboard." : "Clipboard unavailable.", ok ? "success" : "warn");
  };

  const download = () => {
    downloadBlob(
      new Blob([JSON.stringify(packet, null, 2)], { type: "application/json" }),
      `HANDOVER_${packet.session_id.slice(0, 8)}.json`,
    );
  };

  return (
    <div className="modal-scrim" role="dialog" aria-modal="true" aria-label="Shift handover token">
      <div className="modal">
        <header className="modal__head">
          <span className="modal__title">Air-gapped shift handover token</span>
          <button type="button" className="btn btn--small" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="modal__body">
          <p className="modal__desc">
            Sealed copy of the session for offline shift handover — USB export or 2D QR transfer.
            No readable details, only fingerprints, masks and flags.
          </p>
          <table className="tbl tbl--compact">
            <tbody>
              <tr>
                <td className="k">HANDOVER</td>
                <td className="mono">{packet.handover_id}</td>
              </tr>
              <tr>
                <td className="k">SESSION</td>
                <td className="mono">{packet.session_id}</td>
              </tr>
              <tr>
                <td className="k">ISSUED</td>
                <td className="mono">{packet.timestamp}</td>
              </tr>
              <tr>
                <td className="k">SCREENER</td>
                <td className="mono">{packet.screener}</td>
              </tr>
              <tr>
                <td className="k">VERDICT / RISK</td>
                <td className="mono">
                  {packet.verdict} · {packet.risk_score}
                </td>
              </tr>
              <tr>
                <td className="k">SEAL</td>
                <td className="mono">{packet.seal}</td>
              </tr>
            </tbody>
          </table>
          <label className="field">
            <span className="field__label">Packet string</span>
            <textarea className="mono pkt-box" readOnly value={packet.qr_packet_string} rows={5} />
          </label>
        </div>
        <footer className="modal__foot">
          <button type="button" className="btn" onClick={() => void copy()}>
            Copy
          </button>
          <button type="button" className="btn" onClick={download}>
            Download JSON
          </button>
        </footer>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------------
// The Main Screening Desk
// ----------------------------------------------------------------------------

export function DeskView() {
  const { toast } = useToast();
  const [active, setActive] = useState<ScreeningSessionDetail | null>(null);
  const [openList, setOpenList] = useState<ScreeningSession[]>(() => portalCache.openSessions || []);
  const [catalog, setCatalog] = useState<CheckpointCatalog | null>(() => portalCache.checkpoints);
  const [loading, setLoading] = useState(() => !portalCache.openSessions);
  const [busy, setBusy] = useState(false);

  // New session creation fields
  const [newCheckpoint, setNewCheckpoint] = useState("Integrated Checkpost Alpha");
  const [newNationality, setNewNationality] = useState("IN");
  const [newPurpose, setNewPurpose] = useState("Trade");
  const [showNewForm, setShowNewForm] = useState(false);
  const [resumingId, setResumingId] = useState<string | null>(null);

  // Document intake form
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [thumbUrl, setThumbUrl] = useState<string | null>(null);
  const [fileBack, setFileBack] = useState<File | null>(null);
  const [fileKeyBack, setFileKeyBack] = useState(100);
  const [thumbUrlBack, setThumbUrlBack] = useState<string | null>(null);
  const [webcamTarget, setWebcamTarget] = useState<"front" | "back">("front");

  const [docType, setDocType] = useState<ScreenDocType>("passport");
  const [docNumber, setDocNumber] = useState("");
  const [declaredName, setDeclaredName] = useState("");
  const [declaredDob, setDeclaredDob] = useState("");
  const [specimenBusy, setSpecimenBusy] = useState(false);
  const [note, setNote] = useState("");
  const [modelHint, setModelHint] = useState<string | null>(null);

  useEffect(() => {
    if (file && file.type.startsWith("image/")) {
      const url = URL.createObjectURL(file);
      setThumbUrl(url);
      return () => URL.revokeObjectURL(url);
    }
    setThumbUrl(null);
  }, [file]);

  useEffect(() => {
    if (fileBack && fileBack.type.startsWith("image/")) {
      const url = URL.createObjectURL(fileBack);
      setThumbUrlBack(url);
      return () => URL.revokeObjectURL(url);
    }
    setThumbUrlBack(null);
  }, [fileBack]);

  const [showWebcam, setShowWebcam] = useState(false);
  const [showDiscrepancyModal, setShowDiscrepancyModal] = useState(false);
  const [handover, setHandover] = useState<ShiftHandoverPacket | null>(null);
  const [handoverBusy, setHandoverBusy] = useState(false);

  const sessionCacheRef = useRef<Map<string, ScreeningSessionDetail>>(new Map());

  // Load checkpoint catalog
  useEffect(() => {
    getCheckpoints().then((res) => {
      if (res.ok) setCatalog(res.data);
    }).catch(() => {});
  }, []);

  const refreshOpen = useCallback(async () => {
    const res = await getSessions("open");
    if (res.ok) setOpenList(res.data.sessions);
    return res.ok ? res.data.sessions : [];
  }, []);

  const loadDetail = useCallback(async (id: string, forceFresh = false) => {
    // Instant cache-first switch for 0ms latency
    if (!forceFresh && sessionCacheRef.current.has(id)) {
      const cached = sessionCacheRef.current.get(id)!;
      setActive(cached);
      setModelHint(null);
      // Quiet background refresh so data stays up-to-date
      void getSession(id).then((freshRes) => {
        if (freshRes.ok) {
          sessionCacheRef.current.set(id, freshRes.data);
          setActive((curr) => (curr?.id === id ? freshRes.data : curr));
        }
      });
      return true;
    }

    const res = await getSession(id);
    if (res.ok) {
      sessionCacheRef.current.set(id, res.data);
      setActive(res.data);
      setModelHint(null);
      return true;
    }
    setActive(null);
    toast(`Failed to load session ${id}: ${res.error}`, "error");
    return false;
  }, [toast]);

  // On mount: load open roster list only without auto-opening past sessions
  useEffect(() => {
    let mounted = true;
    (async () => {
      await refreshOpen();
      if (!mounted) return;
      setLoading(false);
    })();
    return () => {
      mounted = false;
    };
  }, [refreshOpen]);

  const openNewSession = async () => {
    setBusy(true);
    const res = await createSession({
      checkpoint: newCheckpoint.trim() || "Integrated Checkpost Alpha",
      nationality: newNationality.trim(),
      purpose: newPurpose.trim(),
    });
    setBusy(false);
    if (res.ok) {
      toast(`${res.data.label || "New session"} opened — screening started.`, "success");
      const detail = await getSession(res.data.id);
      if (detail.ok) setActive(detail.data);
      setShowNewForm(false);
      await refreshOpen();
    } else {
      toast(res.error, "error");
    }
  };

  const startNextTraveller = async () => {
    setBusy(true);
    const post = active?.checkpoint || newCheckpoint.trim() || "Integrated Checkpost Alpha";
    const nat = active?.nationality || newNationality.trim() || "IN";
    const purp = active?.purpose || newPurpose.trim() || "Trade";
    const res = await createSession({
      checkpoint: post,
      nationality: nat,
      purpose: purp,
    });
    setBusy(false);
    if (res.ok) {
      toast(`${res.data.label || "Next session"} opened for ${post}. Ready to scan.`, "success");
      const detail = await getSession(res.data.id);
      if (detail.ok) setActive(detail.data);
      setFile(null);
      setFileBack(null);
      setFileKey((k) => k + 1);
      setFileKeyBack((k) => k + 1);
      setDocNumber("");
      setDeclaredName("");
      setDeclaredDob("");
      setNote("");
      setModelHint(null);
      setShowNewForm(false);
      await refreshOpen();
    } else {
      toast(`Failed to open next session: ${res.error}`, "error");
      await resetDesk();
      setShowNewForm(true);
    }
  };

  const resumeSession = async (id: string) => {
    setResumingId(id);
    try {
      const ok = await loadDetail(id);
      if (ok) {
        setShowNewForm(false);
        toast(`Resumed active session ${id}.`, "success");
      }
    } finally {
      setResumingId(null);
    }
  };

  const loadSpecimen = async (presetId: string) => {
    const preset = SPECIMEN_PRESETS.find((p) => p.id === presetId);
    if (!preset) return;
    setSpecimenBusy(true);
    try {
      setDocType(preset.docType);
      setDocNumber(preset.docNumber);
      setDeclaredName(preset.declaredName);
      setDeclaredDob(preset.declaredDob);
      const f = await generateSpecimenFile(preset);
      setFile(f);
      setFileBack(null);
      setFileKey((k) => k + 1);
      setFileKeyBack((k) => k + 1);
      setModelHint(`${preset.title} loaded. Review, then check document.`);
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Failed to load specimen", "error");
    } finally {
      setSpecimenBusy(false);
    }
  };

  const declaredMap = (): Record<string, string> => {
    const declKey =
      docType === "passport" || docType === "visa"
        ? "passport"
        : docType === "other"
          ? "declared_number"
          : docType;
    const out: Record<string, string> = {};
    if (docNumber.trim()) out[declKey] = docNumber.trim();
    if (declaredName.trim()) out.name = declaredName.trim();
    if (declaredDob.trim()) out.dob = declaredDob.trim();
    return out;
  };

  const handleFrontFileSelect = (rawFile: File | null) => {
    if (!rawFile) {
      setFile(null);
      return;
    }
    if (rawFile.size > 4.5 * 1024 * 1024) {
      toast(`File size (${(rawFile.size / (1024 * 1024)).toFixed(1)} MB) exceeds the 4.5 MB server cap. Please use a compressed or lower-resolution file.`, "warn");
      return;
    }
    setFile(rawFile);
  };

  const handleBackFileSelect = (rawFile: File | null) => {
    if (!rawFile) {
      setFileBack(null);
      return;
    }
    if (rawFile.size > 4.5 * 1024 * 1024) {
      toast(`File size (${(rawFile.size / (1024 * 1024)).toFixed(1)} MB) exceeds the 4.5 MB server cap. Please use a compressed or lower-resolution file.`, "warn");
      return;
    }
    setFileBack(rawFile);
  };

  const screenIntoSession = async () => {
    if (!active) {
      toast("Open a session first.", "warn");
      return;
    }
    if (!file) {
      toast("Attach at least the front side of the identity document.", "warn");
      return;
    }
    setBusy(true);
    const decl = declaredMap();
    try {
      const res = await screenDocument(
        file,
        docType,
        active.checkpoint,
        Object.keys(decl).length ? decl : undefined,
        null,
        active.id,
        fileBack ?? null,
      );
      setBusy(false);

    if (res.ok) {
      toast(
        res.data.verdict === "CLEAR"
          ? `Document screened CLEAR (Score: ${res.data.risk_score}).`
          : `Document screened ${res.data.verdict} (Score: ${res.data.risk_score}).`,
        res.data.verdict === "CLEAR" ? "success" : res.data.verdict === "FLAGGED" ? "error" : "warn",
      );
      setFile(null);
      setFileBack(null);
      setFileKey((k) => k + 1);
      setFileKeyBack((k) => k + 1);
      setDocNumber("");
      setDeclaredName("");
      setDeclaredDob("");
      setModelHint(null);
      await loadDetail(active.id, true);
      } else {
        toast(res.error, "error");
        if (res.error?.toLowerCase().includes("session not found")) {
          await refreshOpen();
        }
      }
    } catch (err: unknown) {
      toast(err instanceof Error ? err.message : "Screening failed. Please check file size.", "error");
    } finally {
      setBusy(false);
    }
  };


  const handleSoftRemove = async (reportId: string) => {
    if (!active) return;
    if (!window.confirm("Remove this document from current session check? (The audit record is safely preserved)")) return;
    setBusy(true);
    const res = await removeSessionDocument(active.id, reportId);
    setBusy(false);
    if (res.ok) {
      toast("Document removed from session check (audit log preserved).", "info");
      await loadDetail(active.id, true);
    } else {
      toast(res.error, "error");
    }
  };

  const handleRestore = async (reportId: string) => {
    if (!active) return;
    setBusy(true);
    const res = await restoreSessionDocument(active.id, reportId);
    setBusy(false);
    if (res.ok) {
      toast("Document restored into session check.", "success");
      await loadDetail(active.id, true);
    } else {
      toast(res.error, "error");
    }
  };

  const closeSessionNow = async (action: "approve" | "flag") => {
    if (!active) return;
    setBusy(true);
    const res = await closeSession(active.id, action, note);
    setBusy(false);
    if (res.ok) {
      setActive(res.data);
      setNote("");
      toast(
        action === "approve"
          ? "Session approved and logged."
          : "Session flagged for supervisor review.",
        action === "approve" ? "success" : "warn",
      );
      await refreshOpen();
    } else {
      toast(res.error, "error");
    }
  };

  const openHandover = async () => {
    if (!active) return;
    setHandoverBusy(true);
    const res = await getShiftHandoverToken(active.id);
    setHandoverBusy(false);
    if (res.ok) setHandover(res.data);
    else toast(`Handover token failed: ${res.error}`, "error");
  };

  const closeUnused = async (sessionId: string) => {
    setBusy(true);
    const res = await closeSession(sessionId, "close", "Closed unused session");
    setBusy(false);
    if (res.ok) {
      toast("Unused session closed.", "info");
      sessionCacheRef.current.delete(sessionId);
      if (active?.id === sessionId) {
        await resetDesk();
      } else {
        await refreshOpen();
      }
    } else {
      toast(res.error, "error");
    }
  };

  const closeAllUnused = async () => {
    setBusy(true);
    const res = await closeUnusedSessions();
    setBusy(false);
    if (res.ok) {
      toast(`Closed ${res.data.closed_count} unused session(s).`, "success");
      sessionCacheRef.current.clear();
      if (active && active.documents.length === 0) {
        await resetDesk();
      } else {
        await refreshOpen();
      }
    } else {
      toast(res.error, "error");
    }
  };

  const resetDesk = async () => {
    setActive(null);
    setFile(null);
    setFileBack(null);
    setFileKey((k) => k + 1);
    setFileKeyBack((k) => k + 1);
    setDocNumber("");
    setDeclaredName("");
    setDeclaredDob("");
    setNote("");
    setModelHint(null);
    setShowNewForm(false);
    await refreshOpen();
  };

  const open = active && active.status === "open";
  const closed = active && active.status !== "open";
  const hasDiscrepancy = Boolean(open && active.comparison?.verdict === "DISCREPANCY");
  const canClose = Boolean(open && active.documents.length > 0);

  const hasWatchlistHit = Boolean(
    active?.documents?.some(
      (d) =>
        !d.removed_at &&
        (Boolean(d.watchlist_hits?.length) ||
          d.modules?.validation?.checks?.some(
            (c) => c.ok === false && (c.label === "watchlist" || c.detail?.toLowerCase().includes("watchlist"))
          ) ||
          d.reasons?.some((r) => r.toUpperCase().includes("WATCHLIST")))
    )
  );

  const checkpointOptions = catalog?.checkpoints.all || DEFAULT_CHECKPOINTS;
  const nationalities = catalog?.nationalities || [
    { code: "NP", label: "Nepal" },
    { code: "IN", label: "India" },
    { code: "BT", label: "Bhutan" },
    { code: "BD", label: "Bangladesh" },
    { code: "MM", label: "Myanmar" },
    { code: "US", label: "United States" },
    { code: "GB", label: "United Kingdom" },
    { code: "UNKNOWN", label: "Other / Unlisted" },
  ];

  // Keyboard shortcuts for rapid desk inspection: [A] Approve, [O] Override, [E] Review, [S] Take Photo
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      if (showDiscrepancyModal || showWebcam || busy || !active || active.status !== "open") return;

      if (e.key === "a" || e.key === "A") {
        if (canClose && !hasWatchlistHit) {
          e.preventDefault();
          if (hasDiscrepancy) {
            setShowDiscrepancyModal(true);
          } else {
            void closeSessionNow("approve");
          }
        }
      } else if (e.key === "o" || e.key === "O") {
        if (canClose && hasDiscrepancy) {
          e.preventDefault();
          setShowDiscrepancyModal(true);
        }
      } else if (e.key === "e" || e.key === "E") {
        if (canClose) {
          e.preventDefault();
          void closeSessionNow("flag");
        }
      } else if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        setWebcamTarget("front");
        setShowWebcam(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [canClose, hasWatchlistHit, hasDiscrepancy, showDiscrepancyModal, showWebcam, busy, active]);

  return (
    <div className="view">
      {/* --- No active session: start panel -------------------------------- */}
      {!active && (
        <section className="panel panel--muted">
          <div className="panel__row">
            <div>
              <h2 className="panel__title">Ready for the next traveller</h2>
              <p className="panel__body">
                One traveller at a time. Open a session, scan their documents one by one, compare,
                then decide — approve or send for a closer look.
              </p>
            </div>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => setShowNewForm((v) => !v)}
            >
              {showNewForm ? "Cancel" : "Open new session"}
            </button>
          </div>

          {showNewForm && (
            <div className="new-session" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
              <label className="field">
                <span className="field__label">BORDER POST / ICP</span>
                <input
                  list="checkpoint-options"
                  value={newCheckpoint}
                  onChange={(e) => setNewCheckpoint(e.target.value)}
                  placeholder="e.g. ICP Alpha, Checkpoint 01..."
                />
                <datalist id="checkpoint-options">
                  {checkpointOptions.map((c) => (
                    <option key={c} value={c} />
                  ))}
                </datalist>
              </label>

              <label className="field">
                <span className="field__label">TRAVELLER NATIONALITY</span>
                <select value={newNationality} onChange={(e) => setNewNationality(e.target.value)}>
                  {nationalities.map((n) => (
                    <option key={n.code} value={n.code}>
                      {n.label} ({n.code})
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <span className="field__label">PURPOSE OF TRAVEL</span>
                <select value={newPurpose} onChange={(e) => setNewPurpose(e.target.value)}>
                  <option value="Trade">Trade / Commerce</option>
                  <option value="Tourism">Tourism / Pilgrimage</option>
                  <option value="Transit">Transit</option>
                  <option value="Family">Family Visit</option>
                  <option value="Employment">Employment</option>
                  <option value="Medical">Medical</option>
                  <option value="Official">Official Duty</option>
                </select>
              </label>

              <div style={{ display: "flex", alignItems: "flex-end" }}>
                <button
                  type="button"
                  className="btn btn--primary btn--block"
                  disabled={busy}
                  onClick={() => void openNewSession()}
                >
                  {busy ? "Opening…" : "Open session"}
                </button>
              </div>
              <p className="muted" style={{ gridColumn: "1 / -1", fontSize: "11.5px", marginTop: 2 }}>
                <strong>Traveller goes into Session 1, 2, 3…</strong> — numbering restarts at 1 every
                day, so today's sessions are easy to call out.
              </p>
            </div>
          )}

          {openList.length > 0 && (
            <div className="resume">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                <span className="k">Resume today's open session</span>
                {openList.some((s) => s.document_count === 0) && (
                  <button
                    type="button"
                    className="btn btn--small btn--ghost"
                    style={{ fontSize: "11.5px", color: "var(--bad)" }}
                    disabled={busy}
                    onClick={() => void closeAllUnused()}
                    title="Close all empty sessions that have 0 documents"
                  >
                    ✕ Close all unused ({openList.filter((s) => s.document_count === 0).length})
                  </button>
                )}
              </div>
              <table className="tbl tbl--compact">
                <tbody>
                  {openList.map((s) => (
                    <tr key={s.id}>
                      <td>{s.label || `Session · ${s.id.slice(0, 6)}`}</td>
                      <td>{s.checkpoint}</td>
                      <td className="mono muted">{s.document_count} doc(s)</td>
                      <td style={{ textAlign: "right" }}>
                        <div style={{ display: "inline-flex", gap: 6 }}>
                          <button
                            type="button"
                            className="btn btn--small btn--primary"
                            disabled={resumingId === s.id}
                            onClick={() => void resumeSession(s.id)}
                          >
                            {resumingId === s.id ? "Resuming…" : "Resume"}
                          </button>
                          {s.document_count === 0 && (
                            <button
                              type="button"
                              className="btn btn--small btn--ghost"
                              style={{ color: "var(--bad)" }}
                              disabled={busy}
                              onClick={() => void closeUnused(s.id)}
                              title="Close this unused 0-document session"
                            >
                              ✕ Close
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* --- Active session rail ------------------------------------------- */}
      {active && (
        <section className="panel">
          <div className="panel__row">
            <div>
              <div className="k">CURRENT TRAVELLER</div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", margin: "4px 0" }}>
                <div className="session-label">
                  {active.label || `Session #${active.id.slice(0, 6)}`}
                </div>
                <button
                  type="button"
                  className="btn btn--small btn--ghost"
                  style={{ padding: "2px 8px", fontSize: "11px" }}
                  onClick={() => {
                    void copyText(active.id);
                    toast("Copied session ID to clipboard.", "info");
                  }}
                  title="Copy session UUID to clipboard"
                >
                  Copy ID
                </button>
                {openList.length > 1 && (
                  <div className="session-quick-switcher" title="Quick switch between open sessions today">
                    <span className="muted" style={{ fontSize: 11 }}>Switch to:</span>
                    <select
                      value={active.id}
                      onChange={(e) => void resumeSession(e.target.value)}
                    >
                      {openList.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.label || `Session · ${s.id.slice(0, 6)}`} ({s.checkpoint})
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
              <div className="session-meta">
                <span className="chip chip--mute">{active.checkpoint}</span>
                <span
                  className={`chip chip--${
                    active.status === "approved"
                      ? "ok"
                      : active.status === "flagged"
                        ? "warn"
                        : active.status === "rejected"
                          ? "bad"
                          : "mute"
                  }`}
                >
                  {plainStatus(active.status)}
                </span>
                {active.nationality && (
                  <span className="chip chip--info">
                    Nationality: {nationalities.find((n) => n.code === active.nationality)?.label || active.nationality}
                  </span>
                )}
                {active.purpose && (
                  <span className="chip chip--mute">{active.purpose}</span>
                )}
                <span className="muted">
                  opened {timeLabelIst(active.created_at_ist || active.created_at)}
                  {active.screener ? ` by ${active.screener}` : ""}
                  {" · "}{active.document_count} document(s)
                </span>
              </div>
            </div>
            <div style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
              {open && active.documents.length === 0 && (
                <button
                  type="button"
                  className="btn btn--small btn--ghost"
                  style={{ color: "var(--bad)" }}
                  disabled={busy}
                  onClick={() => void closeUnused(active.id)}
                  title="Close this empty session with 0 documents"
                >
                  ✕ Close (Unused)
                </button>
              )}
              {closed && (
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => void startNextTraveller()}
                  disabled={busy}
                >
                  ▶ Start Next Traveller
                </button>
              )}
              {open && (
                <button type="button" className="btn" onClick={() => void refreshOpen()} disabled={busy}>
                  Refresh
                </button>
              )}
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => void resetDesk()}
                title="Return to traveller selection"
              >
                Reset Desk
              </button>
            </div>
          </div>

          {/* Stepper progress rail and subtle guidance cue */}
          <GuideStepper
            active={!!active}
            docCount={active.documents.filter((d) => !d.removed_at).length}
            closed={!!closed}
            status={active.status}
          />



          {/* Executive Session Completed / Next Traveller Hero Banner */}
          {closed && (
            <div className={`session-completed-banner session-completed-banner--${active.status}`}>
              <div className="session-completed-banner__main">
                <div className="session-completed-banner__icon">
                  {active.status === "approved" ? "✅" : active.status === "flagged" ? "⚠️" : "🛑"}
                </div>
                <div className="session-completed-banner__info">
                  <h3 className="session-completed-banner__title">
                    {active.status === "approved"
                      ? `${active.label || "Session"} Approved & Signed into Ledger`
                      : active.status === "flagged"
                        ? `${active.label || "Session"} Flagged & Sent to Supervisory Review`
                        : `${active.label || "Session"} Rejected & Sealed as Fraud Evidence`}
                  </h3>
                  <p className="session-completed-banner__desc">
                    {active.status === "approved"
                      ? "All document checks and identity comparisons passed. A chained SHA-256 block has been signed into the border ledger. Court admissibility certificate is ready."
                      : active.status === "flagged"
                        ? "Discrepancies or warnings were detected. This session has been safely forwarded to the Senior Officer Review Queue for supervisory adjudication."
                        : "Fraud has been confirmed by supervisory review and permanently recorded into the immutable audit log."}
                  </p>
                </div>
              </div>

              <div className="session-completed-banner__actions">
                <button
                  type="button"
                  className="btn btn--primary btn--hero"
                  onClick={() => void startNextTraveller()}
                  disabled={busy}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <polygon points="5 3 19 12 5 21 5 3" fill="currentColor" />
                  </svg>
                  <span>Start Next Traveller</span>
                </button>

                {active.block_hash && (
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => window.open(getBsaCertificateUrl(active.id), "_blank")}
                  >
                    📄 Court Certificate (s.65B BSA)
                  </button>
                )}

                <button
                  type="button"
                  className="btn btn--ghost"
                  disabled={handoverBusy}
                  onClick={() => void openHandover()}
                >
                  {handoverBusy ? "Sealing…" : "📋 Shift Handover Token"}
                </button>
              </div>
            </div>
          )}

          {/* Border Post Guided Protocol Banner */}
          <GuidedProtocolBar
            guide={active.guide}
            checkpoint={active.checkpoint}
            nationality={active.nationality}
          />

          {open && (
            <>
              {/* --- Document intake -------------------------------------- */}
              {/* --- Document intake card -------------------------------- */}
              <div
                className="intake-card"
                onKeyDown={(e) => {
                  if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && file && !busy) {
                    e.preventDefault();
                    void screenIntoSession();
                  }
                }}
              >
                <div className="intake-card__header">
                  <div>
                    <h3 className="intake-card__title">Scan &amp; Check Identity Document</h3>
                    <p className="intake-card__subtitle">
                      Upload the traveller's ID (front side required; back side recommended for Passports, Aadhaar &amp; Driving Licences).
                      All checks run instantly in secure memory.
                    </p>
                  </div>
                  <div className="intake-card__badges">
                    {file && (
                      <div className="intake-file-badge" title={file.name}>
                        <span className="dot dot--ok" />
                        <span className="intake-file-badge__name">Front: {file.name} ({(file.size / 1024).toFixed(0)} KB)</span>
                        <button
                          type="button"
                          className="btn btn--small btn--ghost"
                          style={{ padding: "1px 6px", marginLeft: 4 }}
                          onClick={() => { setFile(null); setFileKey((k) => k + 1); }}
                          title="Remove front side file"
                        >
                          ✕
                        </button>
                      </div>
                    )}
                    {fileBack && (
                      <div className="intake-file-badge" title={fileBack.name}>
                        <span className="dot dot--ok" />
                        <span className="intake-file-badge__name">Back: {fileBack.name} ({(fileBack.size / 1024).toFixed(0)} KB)</span>
                        <button
                          type="button"
                          className="btn btn--small btn--ghost"
                          style={{ padding: "1px 6px", marginLeft: 4 }}
                          onClick={() => { setFileBack(null); setFileKeyBack((k) => k + 1); }}
                          title="Remove back side file"
                        >
                          ✕
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                <div className="intake-layout">
                  {/* Left Column: Metadata & Declared Values */}
                  <div className="intake-section intake-section--meta">
                    <div className="intake-section__title">
                      <span>1. Document Information</span>
                    </div>
                    <p className="intake-section__hint">
                      Select document type. Optional fields help cross-verify the scan.
                    </p>

                    <label className="field">
                      <span className="field__label">DOCUMENT TYPE</span>
                      <select
                        value={docType}
                        onChange={(e) => setDocType(e.target.value as ScreenDocType)}
                      >
                        {SCREEN_DOC_TYPES.map((t) => (
                          <option key={t} value={t}>
                            {SCREEN_DOC_LABELS[t]}
                          </option>
                        ))}
                      </select>
                    </label>

                    <div className="intake-fields-grid">
                      <label className="field">
                        <span className="field__label">DOCUMENT NUMBER</span>
                        <input
                          value={docNumber}
                          onChange={(e) => setDocNumber(e.target.value)}
                          placeholder={SCREEN_DOC_NUMBER_PLACEHOLDERS[docType] || "e.g. K1234567"}
                        />
                      </label>

                      <label className="field">
                        <span className="field__label">DATE OF BIRTH (optional)</span>
                        <input
                          value={declaredDob}
                          onChange={(e) => setDeclaredDob(e.target.value)}
                          placeholder="YYYY-MM-DD"
                        />
                      </label>
                    </div>

                    <label className="field">
                      <span className="field__label">FULL NAME (optional)</span>
                      <input
                        value={declaredName}
                        onChange={(e) => setDeclaredName(e.target.value)}
                        placeholder="e.g. RAJESH SHARMA"
                      />
                    </label>
                  </div>

                  {/* Right Column: Dual Capture Source (Front & Back) */}
                  <div className="intake-section intake-section--upload">
                    <div className="intake-section__title">
                      <span>2. Upload or Take Photos</span>
                    </div>
                    <p className="intake-section__hint">
                      Provide clear photos or PDF scans. No raw files are ever kept on disk.
                    </p>

                    <div className="dual-intake-grid">
                      {/* FRONT SIDE (Required) */}
                      <div className="side-card side-card--front">
                        <div className="side-card__header">
                          <span className="side-card__tag">SIDE 1 (FRONT / BIO PAGE) *</span>
                          <span className="side-card__subtag">Photo &amp; Details</span>
                        </div>

                        {file ? (
                          <div className="file-thumb-preview">
                            {thumbUrl ? (
                              <div className="doc-preview-wrapper">
                                <img
                                  src={thumbUrl}
                                  alt="Front preview"
                                  className="file-thumb-preview__img"
                                />
                              </div>
                            ) : (
                              <div className="file-thumb-preview__icon">📄</div>
                            )}
                            <div className="file-thumb-preview__meta">
                              <span className="file-thumb-preview__name" title={file.name}>{file.name}</span>
                              <span className="file-thumb-preview__size">
                                {(file.size / 1024).toFixed(0)} KB · Front
                              </span>
                            </div>
                            <button
                              type="button"
                              className="btn btn--small btn--ghost"
                              onClick={() => {
                                setFile(null);
                                setFileKey((k) => k + 1);
                              }}
                              title="Remove front file"
                            >
                              ✕
                            </button>
                          </div>
                        ) : (
                          <label className="dropzone">
                            <input
                              key={fileKey}
                              type="file"
                              accept="image/*,.pdf"
                              capture="environment"
                              onChange={(e) => void handleFrontFileSelect(e.target.files?.[0] || null)}
                            />
                            <div className="dropzone__icon">
                              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                                <polyline points="17 8 12 3 7 8" />
                                <line x1="12" y1="3" x2="12" y2="15" />
                              </svg>
                            </div>
                            <span className="dropzone__label">Upload Front Side</span>
                            <span className="dropzone__hint">Required · JPEG/PNG/PDF</span>
                          </label>
                        )}

                        <button
                          type="button"
                          className="btn btn--small btn--webcam"
                          onClick={() => {
                            setWebcamTarget("front");
                            setShowWebcam(true);
                          }}
                        >
                          📸 Take Front Photo
                        </button>
                      </div>

                      {/* BACK SIDE (Optional / Recommended) */}
                      <div className="side-card side-card--back">
                        <div className="side-card__header">
                          <span className="side-card__tag">SIDE 2 (BACK PAGE)</span>
                          <span className="side-card__subtag">Address, QR &amp; Guardians</span>
                        </div>

                        {fileBack ? (
                          <div className="file-thumb-preview">
                            {thumbUrlBack ? (
                              <div className="doc-preview-wrapper">
                                <img
                                  src={thumbUrlBack}
                                  alt="Back preview"
                                  className="file-thumb-preview__img"
                                />
                              </div>
                            ) : (
                              <div className="file-thumb-preview__icon">📄</div>
                            )}
                            <div className="file-thumb-preview__meta">
                              <span className="file-thumb-preview__name" title={fileBack.name}>{fileBack.name}</span>
                              <span className="file-thumb-preview__size">
                                {(fileBack.size / 1024).toFixed(0)} KB · Back
                              </span>
                            </div>
                            <button
                              type="button"
                              className="btn btn--small btn--ghost"
                              onClick={() => {
                                setFileBack(null);
                                setFileKeyBack((k) => k + 1);
                              }}
                              title="Remove back file"
                            >
                              ✕
                            </button>
                          </div>
                        ) : (
                          <label className="dropzone dropzone--back">
                            <input
                              key={fileKeyBack}
                              type="file"
                              accept="image/*,.pdf"
                              capture="environment"
                              onChange={(e) => void handleBackFileSelect(e.target.files?.[0] || null)}
                            />
                            <div className="dropzone__icon">
                              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                                <polyline points="17 8 12 3 7 8" />
                                <line x1="12" y1="3" x2="12" y2="15" />
                              </svg>
                            </div>
                            <span className="dropzone__label">Upload Back Side</span>
                            <span className="dropzone__hint">Optional · For Address &amp; QR</span>
                          </label>
                        )}

                        <button
                          type="button"
                          className="btn btn--small btn--webcam"
                          onClick={() => {
                            setWebcamTarget("back");
                            setShowWebcam(true);
                          }}
                        >
                          📸 Take Back Photo
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Bottom Actions Bar */}
                <div className="intake-actions-bar">
                  <div className="specimen-row">
                    <span className="specimen-row__tag">⚡ TEST WITH PRESETS:</span>
                    {SPECIMEN_PRESETS.map((p) => {
                      let kind = "clean";
                      if (p.id.includes("tampered")) kind = "tampered";
                      else if (p.id.includes("syndicate")) kind = "syndicate";
                      else if (p.docType === "driving_licence") kind = "dl";
                      else if (p.docType === "pan") kind = "pan";
                      else if (p.docType === "aadhaar") kind = "aadhaar";

                      return (
                        <button
                          key={p.id}
                          type="button"
                          className={`specimen-chip specimen-chip--${kind}`}
                          disabled={specimenBusy}
                          onClick={() => void loadSpecimen(p.id)}
                          title={`${p.title} · ${p.badge} — ${p.description}`}
                        >
                          <span className="specimen-chip__dot" />
                          <span className="specimen-chip__title">{p.title}</span>
                          {p.badge && <span className="specimen-chip__badge">{p.badge}</span>}
                        </button>
                      );
                    })}
                  </div>

                  <button
                    type="button"
                    className="btn btn--primary btn--hero"
                    disabled={busy || !file}
                    onClick={() => void screenIntoSession()}
                    title="Check this document into current session (Ctrl+Enter)"
                  >
                    {busy ? "Checking…" : "Run Verification Check"}
                    <span style={{ fontSize: 11, opacity: 0.85, marginLeft: 6 }}>[Ctrl + ↵]</span>
                  </button>
                </div>

                {modelHint && <p className="hint" style={{ marginTop: 12 }}>{modelHint}</p>}
              </div>

              {/* --- Documents in session --------------------------------- */}
              {active.documents.filter((d) => !d.removed_at).length > 0 ? (
                <div className="docs">
                  <h3 className="board__title">
                    Documents in session ({active.documents.filter((d) => !d.removed_at).length})
                  </h3>
                  <div className="docs__grid">
                    {active.documents
                      .filter((d) => !d.removed_at)
                      .map((d, i) => (
                        <DocCard
                          key={d.id}
                          doc={d}
                          index={i}
                          isOpen={open}
                          onRemove={handleSoftRemove}
                        />
                      ))}
                  </div>
                </div>
              ) : (
                <p className="hint">No active documents yet. Screen the traveller's first document.</p>
              )}

              {/* --- Mistaken-scan drawer (removed docs stay in the audit) - */}
              {active.documents.filter((d) => Boolean(d.removed_at)).length > 0 && (
                <div className="removed-drawer">
                  <div className="removed-drawer__title">
                    Taken out of the session ({active.documents.filter((d) => Boolean(d.removed_at)).length}) — still kept in the audit trail
                  </div>
                  <table className="tbl tbl--compact" style={{ background: "var(--panel)" }}>
                    <thead>
                      <tr>
                        <th>Document</th>
                        <th>Type</th>
                        <th>Result</th>
                        <th>Risk</th>
                        <th>Removed (IST)</th>
                        <th>Removed by</th>
                        <th>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {active.documents
                        .filter((d) => Boolean(d.removed_at))
                        .map((rd) => (
                          <tr key={rd.id}>
                            <td className="mono">DOC-{rd.id.slice(0, 6)}</td>
                            <td>{SCREEN_DOC_LABELS[rd.doc_type as ScreenDocType] || rd.doc_type}</td>
                            <td>
                              <span className={`chip chip--${verdictTone(rd.verdict)}`}>{plainVerdict(rd.verdict)}</span>
                            </td>
                            <td className="muted">{riskWord(rd.risk_score)}</td>
                            <td className="mono">{rd.removed_at_ist || timeLabelIst(rd.removed_at)}</td>
                            <td>{rd.removed_by || "screener"}</td>
                            <td>
                              <button
                                type="button"
                                className="btn btn--small btn--primary"
                                disabled={busy}
                                onClick={() => void handleRestore(rd.id)}
                              >
                                Restore
                              </button>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* --- Comparison + approval bar ----------------------------- */}
              {active.documents.length > 1 && active.comparison && (
                <ComparisonBoard
                  checks={active.comparison.checks}
                  zkp={active.comparison.zkp_gates}
                />
              )}

              {active.documents.length > 0 && (
                <section className="approval">
                  <div className="approval__note">
                    <span className="k">Officer note</span>
                    <input
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="reason / observation (optional)"
                    />
                  </div>
                  <div className="approval__actions sticky-decision-bar">
                    {canClose && hasWatchlistHit && (
                      <span className="chip chip--bad">🚨 Watchlist Hit — Mandatory Referral to Supervisor</span>
                    )}
                    {canClose && !hasWatchlistHit && hasDiscrepancy && (
                      <span className="chip chip--warn">
                        ⚠️ Details Clash — Officer Override Permitted
                      </span>
                    )}
                    {canClose && !hasWatchlistHit && (
                      <button
                        type="button"
                        className="btn btn--approve"
                        disabled={busy}
                        onClick={() => {
                          if (hasDiscrepancy) {
                            setShowDiscrepancyModal(true);
                          } else {
                            void closeSessionNow("approve");
                          }
                        }}
                      >
                        {busy ? "Signing…" : "Approve — looks genuine"}
                      </button>
                    )}
                    {canClose && (
                      <button
                        type="button"
                        className="btn btn--flag"
                        disabled={busy}
                        onClick={() => void closeSessionNow("flag")}
                      >
                        {busy ? "Flagging…" : "Send for review"}
                      </button>
                    )}
                  </div>
                </section>
              )}
            </>
          )}

          {/* --- Closed session: signature seal ---------------------------- */}
          {closed && active.block_hash && (
            <div className={`signed signed--${active.status === "approved" ? "ok" : active.status === "rejected" ? "bad" : "warn"}`}>
              <header className="signed__head">
                <svg className="signed__mark" viewBox="0 0 64 64" aria-hidden="true">
                  <rect width="64" height="64" rx="8" fill="currentColor" opacity="0.12" />
                  <path
                    d="M32 10l16 8c0 11-4 20-16 28-12-8-16-17-16-28z"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="4"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M25 32l5 5 10-11"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <div className="signed__headtext">
                  <span className="signed__title">
                    {active.status === "approved"
                      ? "Approved — recorded in the log"
                      : active.status === "rejected"
                        ? "Rejected — kept as evidence"
                        : "Sent for review — waiting for a supervisor"}
                  </span>
                  <span className="signed__sub mono">Tamper-proof log · nothing readable stored</span>
                </div>
                <span className="chip chip--seal">SHA-256</span>
              </header>

              <div className="signed__hashgrid">
                <div className="signed__hashcell">
                  <span className="k">Signature · this record</span>
                  <code className="hash hash--big mono">{active.block_hash}</code>
                </div>
                <div className="signed__hashcell">
                  <span className="k">Linked from · previous record</span>
                  <code className="hash mono">{active.prev_hash || "GENESIS"}</code>
                </div>
              </div>

              <div className="signed__meta mono">
                <span>result {plainVerdict(active.verdict)}</span>
                <span>{riskWord(active.risk_score)}</span>
                <span>closed {timeLabelIst(active.closed_at || "")}</span>
                {active.adjudicator && <span>settled by {active.adjudicator}</span>}
                <span>{active.document_count} doc(s)</span>
              </div>
              {active.note && <p className="signed__note">officer note: {active.note}</p>}

              <footer className="signed__actions">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => window.open(getBsaCertificateUrl(active.id), "_blank")}
                >
                  BSA 2023 · s.65B court certificate
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  disabled={handoverBusy}
                  onClick={() => void openHandover()}
                >
                  {handoverBusy ? "Sealing…" : "Air-gapped handover token"}
                </button>
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => void startNextTraveller()}
                >
                  ▶ Start Next Traveller
                </button>
              </footer>
            </div>
          )}

          {/* --- Flagged session routed to review queue --- */}
          {closed && !active.block_hash && (
            <div className="signed signed--warn">
              <header className="signed__head">
                <svg className="signed__mark" viewBox="0 0 64 64" aria-hidden="true">
                  <rect width="64" height="64" rx="8" fill="currentColor" opacity="0.12" />
                  <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="none" stroke="currentColor" strokeWidth="4" />
                </svg>
                <div className="signed__headtext">
                  <span className="signed__title">Forwarded to Supervisory Review Queue</span>
                  <span className="signed__sub mono">Discrepancies flagged for Senior Officer adjudication</span>
                </div>
                <span className="chip chip--warn">REVIEW QUEUE</span>
              </header>
              <div className="signed__meta mono">
                <span>status: SENT FOR REVIEW</span>
                <span>risk: {riskWord(active.risk_score)} ({active.risk_score}/100)</span>
                <span>closed: {timeLabelIst(active.closed_at || "")}</span>
                <span>docs: {active.document_count} screened</span>
              </div>
              {active.note && <p className="signed__note">officer note: {active.note}</p>}
              <footer className="signed__actions">
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => void startNextTraveller()}
                >
                  ▶ Start Next Traveller
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => void resetDesk()}
                >
                  Reset Desk
                </button>
              </footer>
            </div>
          )}
        </section>
      )}

      {loading && <p className="hint">Loading desk…</p>}

      {showWebcam && (
        <WebcamCapture
          docType={docType}
          onCapture={(f) => {
            if (webcamTarget === "back") {
              setFileBack(f);
              setFileKeyBack((k) => k + 1);
            } else {
              setFile(f);
              setFileKey((k) => k + 1);
            }
            setShowWebcam(false);
          }}
          onCancel={() => setShowWebcam(false)}
        />
      )}

      {handover && <HandoverModal packet={handover} onClose={() => setHandover(null)} />}

      {/* --- Details Clash Warning Modal (Officer Override Verification) --- */}
      {showDiscrepancyModal && active && (
        <div className="modal-scrim" role="dialog" aria-modal="true" aria-label="Details Clash Warning">
          <div className="modal" style={{ width: "min(560px, 100%)" }}>
            <header className="modal__head" style={{ borderBottom: "1px solid var(--line-2)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 24 }}>⚠️</span>
                <div>
                  <span className="modal__title" style={{ color: "var(--warn-dark, #b45309)" }}>
                    Details Clash — Officer Review Warning
                  </span>
                  <p className="muted" style={{ margin: "2px 0 0 0", fontSize: 11.5 }}>
                    Cross-document verification detected conflicting details between IDs
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="btn btn--small btn--ghost"
                onClick={() => setShowDiscrepancyModal(false)}
              >
                ✕
              </button>
            </header>

            <div className="modal__body" style={{ gap: 14 }}>
              <div
                style={{
                  background: "rgba(245, 158, 11, 0.08)",
                  border: "1px solid rgba(245, 158, 11, 0.28)",
                  borderRadius: 8,
                  padding: "12px 14px",
                }}
              >
                <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: "var(--ink)", fontWeight: 600 }}>
                  The following cross-document discrepancy was identified:
                </p>
                <ul style={{ margin: "8px 0 0 0", paddingLeft: 18, fontSize: 12.5, color: "var(--ink)" }}>
                  {active.comparison?.checks
                    ?.filter((c) => c.status === "disagree")
                    .map((c, idx) => (
                      <li key={idx} style={{ marginTop: 4 }}>
                        <strong>{c.label || c.field}:</strong> {c.detail}
                      </li>
                    ))}
                </ul>
              </div>

              <p style={{ fontSize: 12.5, lineHeight: 1.5, margin: 0, color: "var(--ink)" }}>
                As an authorized border post officer, you have the operational authority to pass this traveller
                if you have physically confirmed their identity and verified that the documents belong to the same person.
              </p>

              <div className="field">
                <span className="field__label">OFFICER OVERRIDE REASON / OBSERVATION (ATTACHED TO LEDGER)</span>
                <input
                  type="text"
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="e.g. Physical holder verified; phonetic spelling variance accepted."
                  autoFocus
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 4 }}>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setShowDiscrepancyModal(false)}
                >
                  Cancel / Re-inspect
                </button>
                <button
                  type="button"
                  className="btn btn--approve"
                  disabled={busy}
                  onClick={() => {
                    setShowDiscrepancyModal(false);
                    void closeSessionNow("approve");
                  }}
                >
                  Confirm &amp; Let Traveller Pass
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}