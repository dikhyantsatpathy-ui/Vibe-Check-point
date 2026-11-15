// ============================================================================
// WatchlistView.tsx — screened watchlist (supervisory access).
// Entries store ONLY a SHA-256 digest of the identifier plus a masked display
// form. Matching during screening is always by digest; the raw identifier is
// never persisted.
//
// Features:
//   - Hash-only watchlist addition & removal,
//   - Nested expandable sub-tables for cryptographic audit receipts.
// ============================================================================

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  SCREEN_WATCHLIST_CATEGORIES,
  SCREEN_WATCHLIST_LABELS,
  SCREEN_WATCHLIST_PLACEHOLDERS,
  addWatchlistEntry,
  getWatchlist,
  removeWatchlistEntry,
  type ScreenWatchlistCategory,
  type WatchlistEntry,
} from "../api";
import { useAuth, useToast } from "../app/state";
import { copyText, downloadBlob, shortHash, timeLabelIst } from "../app/util";

import { portalCache } from "../app/preloader";

export function WatchlistView() {
  const { toast } = useToast();
  const { me } = useAuth();
  const isSuper = !!me?.is_super_admin;
  const [entries, setEntries] = useState<WatchlistEntry[]>(() => portalCache.watchlistEntries || []);
  const [loading, setLoading] = useState(() => !portalCache.watchlistEntries);
  const [busy, setBusy] = useState(false);
  const [category, setCategory] = useState<ScreenWatchlistCategory>("passport");
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // QoL Controls: search, category filter, export
  const [searchQuery, setSearchQuery] = useState("");
  const [filterCat, setFilterCat] = useState("ALL");

  const load = useCallback(async () => {
    const res = await getWatchlist();
    if (res.ok) {
      portalCache.watchlistEntries = res.data.entries;
      setEntries(res.data.entries);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const exportWatchlistCsv = () => {
    const rows = [
      ["ID", "Category", "Masked_Identifier", "Reason", "Added_By", "Added_At_IST"],
      ...filteredEntries.map((e) => [
        `WL-${e.id}`,
        SCREEN_WATCHLIST_LABELS[(e.category || "passport") as ScreenWatchlistCategory] || e.category,
        e.mask,
        `"${(e.reason || "").replace(/"/g, '""')}"`,
        e.added_by,
        timeLabelIst(e.created_at),
      ]),
    ];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const date = new Date().toISOString().slice(0, 10);
    downloadBlob(new Blob([csv], { type: "text/csv" }), `SSB_BORDER_WATCHLIST_${date}.csv`);
    toast(`Exported ${filteredEntries.length} watchlist entries to CSV.`, "success");
  };

  const filteredEntries = useMemo(() => {
    return entries.filter((e) => {
      if (filterCat !== "ALL" && e.category !== filterCat) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const rawCat = e.category || "passport";
        const catLabel = (SCREEN_WATCHLIST_LABELS[rawCat as ScreenWatchlistCategory] || rawCat || "").toLowerCase();
        const match =
          catLabel.includes(q) ||
          (e.mask && e.mask.toLowerCase().includes(q)) ||
          (e.reason && e.reason.toLowerCase().includes(q)) ||
          (e.added_by && e.added_by.toLowerCase().includes(q));
        if (!match) return false;
      }
      return true;
    });
  }, [entries, filterCat, searchQuery]);

  const add = async () => {
    if (!value.trim()) {
      toast("Enter an identifier value.", "warn");
      return;
    }
    setBusy(true);
    const res = await addWatchlistEntry(category, value.trim(), reason.trim() || undefined);
    setBusy(false);
    if (res.ok) {
      toast(
        res.data.already ? "Identifier is already on the watchlist." : "Added — only its digest is stored.",
        res.data.already ? "warn" : "success",
      );
      setValue("");
      setReason("");
      await load();
    } else {
      toast(res.error, "error");
    }
  };

  const remove = async (id: number) => {
    setBusy(true);
    const res = await removeWatchlistEntry(id);
    setBusy(false);
    if (res.ok) {
      toast("Watchlist entry removed.", "success");
      await load();
    } else {
      toast(res.error, "error");
    }
  };

  if (!isSuper) {
    return (
      <div className="view">
        <section className="panel panel--muted">
          <h2 className="panel__title">Watchlist — supervisory access only</h2>
          <p className="panel__body">
            The watchlist is maintained and viewed only by authorised supervisors. Your account is
            not registered as a supervisor.
          </p>
        </section>
      </div>
    );
  }

  return (
    <div className="view">
      <section className="panel">
        <div className="panel__row">
          <div>
            <h2 className="panel__title">Known-fraud list (watchlist)</h2>
            <p className="panel__body">
              Names and numbers are kept only as fingerprints (SHA-256) with a masked view for the
              officer. Screening matches by fingerprint — the real value is never stored.
            </p>
          </div>
          <button type="button" className="btn" onClick={() => void load()}>
            Reload
          </button>
        </div>

        <div className="watch-add">
          <label className="field">
            <span className="field__label">Category</span>
            <select value={category} onChange={(e) => setCategory(e.target.value as ScreenWatchlistCategory)}>
              {SCREEN_WATCHLIST_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {SCREEN_WATCHLIST_LABELS[c]}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field__label">Identifier</span>
            <input
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={SCREEN_WATCHLIST_PLACEHOLDERS[category]}
            />
          </label>
          <label className="field">
            <span className="field__label">Reason</span>
            <input
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Interpol red notice / forged visa cluster"
            />
          </label>
          <button type="button" className="btn btn--primary" disabled={busy} onClick={() => void add()}>
            {busy ? "Adding…" : "Add to watchlist"}
          </button>
        </div>

        {/* QoL Filter & Search Bar */}
        <div className="filter-bar">
          <div className="filter-bar__search">
            <span className="filter-bar__search-icon" aria-hidden="true">
              🔍
            </span>
            <input
              type="text"
              placeholder="Search by masked value, reason, or supervisor…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <div className="filter-bar__group">
            <select
              className="filter-bar__select"
              value={filterCat}
              onChange={(e) => setFilterCat(e.target.value)}
              title="Filter by document category"
            >
              <option value="ALL">All categories ({SCREEN_WATCHLIST_CATEGORIES.length})</option>
              {SCREEN_WATCHLIST_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {SCREEN_WATCHLIST_LABELS[c]}
                </option>
              ))}
            </select>
          </div>

          <div className="filter-bar__actions">
            <button
              type="button"
              className="btn btn--small btn--ghost"
              onClick={exportWatchlistCsv}
              disabled={filteredEntries.length === 0}
              title="Download privacy-safe watchlist CSV export"
            >
              📥 Export CSV
            </button>
            <button
              type="button"
              className="btn btn--small"
              onClick={() => void load()}
              title="Reload watchlist from database"
            >
              ↻ Reload
            </button>
          </div>
        </div>

        <div className="filter-summary">
          <span>
            Showing {filteredEntries.length} of {entries.length} watchlist entries
            {searchQuery.trim() && ` matching "${searchQuery}"`}
            {filterCat !== "ALL" && ` in ${SCREEN_WATCHLIST_LABELS[filterCat as ScreenWatchlistCategory] || filterCat}`}
          </span>
          {(searchQuery || filterCat !== "ALL") && (
            <button
              type="button"
              className="btn btn--small btn--ghost"
              onClick={() => {
                setSearchQuery("");
                setFilterCat("ALL");
              }}
            >
              Clear filters
            </button>
          )}
        </div>

        {loading ? (
          <p className="hint">Loading watchlist…</p>
        ) : filteredEntries.length === 0 ? (
          <p className="hint">
            {entries.length === 0
              ? "Watchlist empty."
              : "No watchlist entries match your filter or search criteria."}
          </p>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Category</th>
                <th>Masked view</th>
                <th>Reason</th>
                <th>Added by</th>
                <th>Added (IST)</th>
                <th>Details</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {filteredEntries.map((e) => (
                <>
                  <tr key={e.id}>
                    <td>
                      <span className="chip chip--mute">
                        {SCREEN_WATCHLIST_LABELS[(e.category || "passport") as ScreenWatchlistCategory] || e.category}
                      </span>
                    </td>
                    <td className="mono">{e.mask}</td>
                    <td className="cell-detail">{e.reason || "—"}</td>
                    <td>{e.added_by}</td>
                    <td className="mono">{timeLabelIst(e.created_at)}</td>
                    <td>
                      <button
                        type="button"
                        className="subtable-toggle"
                        style={{ padding: "2px 6px", fontSize: 11 }}
                        onClick={() => setExpandedId((cur) => (cur === e.id ? null : e.id))}
                      >
                        {expandedId === e.id ? "▼" : "▶"} Details
                      </button>
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn--small btn--flag"
                        disabled={busy}
                        onClick={() => void remove(e.id)}
                      >
                        Remove
                      </button>
                    </td>
                  </tr>

                  {/* Expandable nested sub-table for watchlist audit verification */}
                  {expandedId === e.id && (
                    <tr key={`${e.id}-detail`}>
                      <td colSpan={7} style={{ padding: 0, background: "var(--panel-2)" }}>
                        <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--line)" }}>
                          <span className="k" style={{ fontSize: 11, marginBottom: 6, display: "block" }}>
                            HOW THIS ENTRY IS STORED (AUDIT)
                          </span>
                          <table className="tbl tbl--compact" style={{ background: "var(--panel)" }}>
                            <tbody>
                              <tr>
                                <td className="k">ENTRY ID</td>
                                <td className="mono">#WL-{e.id}</td>
                              </tr>
                              <tr>
                                <td className="k">DIGEST MASK</td>
                                <td className="mono">
                                  {shortHash(e.mask, 28)}{" "}
                                  <button
                                    type="button"
                                    className="btn btn--small"
                                    style={{ padding: "1px 6px", marginLeft: 6 }}
                                    onClick={() => void copyText(e.mask || "")}
                                  >
                                    Copy
                                  </button>
                                </td>
                              </tr>
                              <tr>
                                <td className="k">STORAGE POLICY</td>
                                <td>
                                  <span className="chip chip--ok">NOT STORED</span>
                                  <span className="muted" style={{ fontSize: 11, marginLeft: 8 }}>
                                    Only a fingerprint (SHA-256) of this identifier is kept and
                                    matched. The number itself is never saved.
                                  </span>
                                </td>
                              </tr>
                              <tr>
                                <td className="k">SUPERVISOR</td>
                                <td>{e.added_by}</td>
                              </tr>
                            </tbody>
                          </table>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}