import ReferenceDialog from "./ReferenceDialog";
import FindingDialog from "./FindingDialog";
import ComparisonDetailsDialog from "./ComparisonDetailsDialog";
import ClassificationMap, {
  type ClassificationGraph,
} from "./ClassificationMap";
import ReviewChecklist, {
  needsAttention,
  reviewLabel,
} from "./ReviewChecklist";
import type { ReviewItem } from "./types";
import { useEffect, useRef, useState } from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Building2,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  FileCheck2,
  FileSearch,
  FileText,
  FolderOpen,
  Info,
  LoaderCircle,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  UploadCloud,
  X,
  AlertCircle,
  CircleHelp,
} from "lucide-react";
import { api, json } from "./api";
import type { Row, Session, Reference, Run, Finding } from "./types";

import {
  formatDate,
  money,
  display,
  short,
  rateTypeLabel,
  searchRows,
} from "./presentation";
import { Pill, Empty, Source, RowsTable, Mapping } from "./components";

type Tab = "upload" | "data" | "checks" | "differences";
const tabs: { id: Tab; name: string; icon: typeof FileText }[] = [
  { id: "upload", name: "Upload & review", icon: UploadCloud },
  { id: "data", name: "Saved data", icon: FolderOpen },
  { id: "checks", name: "Labor checks", icon: ClipboardCheck },
  { id: "differences", name: "Differences", icon: SlidersHorizontal },
];
const titles = {
  upload: "A clearer path to confident review.",
  data: "Your labor data, in one place.",
  checks: "Check the rates. See the evidence.",
  differences: "Focus on what needs attention.",
};
const subtitles = {
  upload:
    "Upload a change request, review the printed labor rates, and save the rows you need.",
  data: "Browse reviewed labor records and prepare them for comparison with your rate schedule.",
  checks:
    "Compare submitted labor rates with approved schedules for the dates the work occurred.",
  differences:
    "Only confirmed rate differences appear here. Every finding links back to its source.",
};
export default function App() {
  const [tab, setTabState] = useState<Tab>(
    (localStorage.getItem("warren-tab") as Tab) || "upload",
  );
  const setTab = (value: Tab) => {
    setTabState(value);
    localStorage.setItem("warren-tab", value);
  };
  const [rows, setRows] = useState<Row[]>([]),
    [details, setDetails] = useState<Record<string, Row>>({}),
    [sessions, setSessions] = useState<Session[]>([]),
    [session, setSession] = useState<Session | null>(null);
  const [reference, setReference] = useState<Reference | null>(null),
    [runs, setRuns] = useState<Run[]>([]),
    [runId, setRunId] = useState(localStorage.getItem("warren-run") || "");
  const [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [loaded, setLoaded] = useState(false);
  const [file, setFile] = useState<File | null>(null),
    [project, setProject] = useState(""),
    [contractor, setContractor] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set()),
    [previewSelection, setPreviewSelection] = useState<Set<string>>(new Set()),
    [reviewed, setReviewed] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1),
    [search, setSearch] = useState(""),
    [contractorFilter, setContractorFilter] = useState(""),
    [projectFilter, setProjectFilter] = useState(""),
    [technical, setTechnical] = useState(false),
    [resultFilter, setResultFilter] = useState("needs_review");
  const [referenceOpen, setReferenceOpen] = useState(false),
    [referencePreview, setReferencePreview] = useState<Reference | null>(null),
    [previewRow, setPreviewRow] = useState<Row | null>(null),
    [finding, setFinding] = useState<Finding | null>(null),
    [editIds, setEditIds] = useState<string[]>([]),
    [edit, setEdit] = useState<Row>({});
  const [targetTable, setTargetTable] = useState("");
  const [attentionOnly, setAttentionOnly] = useState(false);
  const jumpToTable = (item: ReviewItem) => {
    setPage(item.page);
    setTargetTable(item.table_id);
  };
  useEffect(() => {
    if (!targetTable) return;
    const element = document.getElementById(`review-table-${targetTable}`);
    element?.focus({ preventScroll: true });
    element?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [page, targetTable]);
  const [classificationMap, setClassificationMap] =
    useState<ClassificationGraph | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const currentRun = runs.find((r) => r.id === runId) || runs[0];
  const currentTab = tabs.some((t) => t.id === tab) ? tab : "upload";
  const setCurrentRun = (id: string) => {
    setRunId(id);
    localStorage.setItem("warren-run", id);
  };
  const load = async () => {
    const [data, history, refs, checks] = await Promise.all([
      api<{ records: Row[]; details: Record<string, Row> }>("/records"),
      api<Session[]>("/sessions"),
      api<{ active: Reference | null }>("/reference"),
      api<Run[]>("/checks"),
    ]);
    setRows(data.records);
    setDetails(data.details);
    setSessions(history);
    setReference(refs.active);
    setRuns(checks);
    // On initial load, prefer a completed replacement for an obsolete rule version.
    // Manual history selection remains available after the workspace has loaded.
    const previous = checks.find((run) => run.id === runId);
    if (!loaded && previous?.rules_changed) {
      const ids = new Set(previous.record_ids);
      const replacement = checks.find(
        (run) =>
          !run.stale &&
          run.record_ids.length === ids.size &&
          run.record_ids.every((id) => ids.has(id)),
      );
      if (replacement) setCurrentRun(replacement.id);
    }
    setLoaded(true);
  };
  const act = async (task: () => Promise<void>) => {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await task();
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  };
  const adoptSession = (next: Session, openReview = false) => {
    setSession(next);
    localStorage.setItem("warren-session", next.id);
    setReviewed(next.reviewed || {});
    setTargetTable("");
    setPreviewSelection(
      new Set(
        (next.extraction?.records || [])
          .filter((r) => !next.saved_ids?.includes(r.record_id))
          .map((r) => r.record_id),
      ),
    );
    setPage(
      next.review_summary?.items.find(
        (i) => i.status === "mapping" || i.status === "needs_review",
      )?.page ||
        next.extraction?.tables[0]?.page ||
        1,
    );
    if (openReview)
      requestAnimationFrame(() => {
        const checklist = document.getElementById("review-checklist");
        checklist?.focus({ preventScroll: true });
        checklist?.scrollIntoView({ block: "start", behavior: "smooth" });
      });
  };
  useEffect(() => {
    let alive = true;
    load().catch((e) => {
      if (alive) {
        setError(e.message);
        setLoaded(true);
      }
    });
    const id = localStorage.getItem("warren-session");
    if (id)
      api<Session>(`/sessions/${id}`)
        .then((s) => {
          if (alive) adoptSession(s);
        })
        .catch(() => localStorage.removeItem("warren-session"));
    return () => {
      alive = false;
    };
  }, []);
  useEffect(() => {
    if (!session || !["queued", "processing"].includes(session.status)) return;
    let alive = true;
    const id = setInterval(
      () =>
        api<Session>(`/sessions/${session.id}`)
          .then((next) => {
            if (alive) {
              if (next.status === "ready") {
                adoptSession(next, true);
                load().catch((e) => setError(e.message));
              } else setSession(next);
            }
          })
          .catch((e) => {
            if (alive) setError(e.message);
          }),
      1000,
    );
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [session?.id, session?.status]);
  useEffect(() => {
    setSearch("");
    setContractorFilter("");
    setProjectFilter("");
  }, [tab]);
  const startUpload = () =>
    act(async () => {
      if (!file) throw Error("Choose a document first.");
      const form = new FormData();
      form.append("file", file);
      form.append("project", project);
      form.append("contractor", contractor);
      const next = await api<Session>("/sessions", {
        method: "POST",
        body: form,
      });
      adoptSession(next);
      await load();
    });
  const confirmTable = (tableId: string, checked: boolean) =>
    act(async () => {
      if (!session) return;
      const confirmations = { ...reviewed };
      if (checked)
        confirmations[tableId] = session.review_tokens?.[tableId] || "";
      else delete confirmations[tableId];
      setReviewed(confirmations);
      let next: Session;
      try {
        next = await api<Session>(
          `/sessions/${session.id}/review`,
          json("PUT", { revision: session.revision, reviewed: confirmations }),
        );
      } catch (error) {
        setReviewed(reviewed);
        throw error;
      }
      setSession(next);
      setReviewed(next.reviewed || {});
      await load();
    });
  const saveRows = () =>
    act(async () => {
      if (!session) return;
      const summary = await api<{
        added: number;
        already_present: number;
        total: number;
      }>(
        `/sessions/${session.id}/save`,
        json("POST", {
          record_ids: [...previewSelection],
          revision: session.revision,
          reviewed,
        }),
      );
      const next = await api<Session>(`/sessions/${session.id}`);
      setSession(next);
      setPreviewSelection(new Set());
      await load();
      setNotice(
        `${summary.added} rows saved. ${summary.already_present} already present. Your dataset now contains ${summary.total} rows.`,
      );
    });
  const runCheck = (ids: string[]) =>
    act(async () => {
      const run = await api<Run>("/checks", json("POST", { record_ids: ids }));
      setCurrentRun(run.id);
      await load();
      setTab("checks");
      setResultFilter(
        run.counts.needs_review
          ? "needs_review"
          : run.counts.difference
            ? "difference"
            : "match",
      );
      setNotice(
        `Check complete: ${run.counts.match} matched, ${run.counts.difference} differences, ${run.counts.needs_review} need review.`,
      );
    });
  const openEdit = (ids: string[]) => {
    setEditIds(ids);
    setEdit(ids.length === 1 ? details[ids[0]] || {} : {});
    setFinding(null);
    setPreviewRow(null);
  };
  const saveDetails = () =>
    act(async () => {
      const records = Object.fromEntries(
        editIds.map((id) => [
          id,
          editIds.length === 1
            ? edit
            : {
                ...(details[id] || {}),
                ...Object.fromEntries(
                  Object.entries(edit).filter(([, v]) => v),
                ),
              },
        ]),
      );
      await api("/records/details", json("POST", { records }));
      setEditIds([]);
      await load();
      setNotice(
        "Comparison details saved. Run the check again to update the findings.",
      );
    });
  const matchesFilters = (r: Row | Finding) =>
    (!contractorFilter || r.contractor === contractorFilter) &&
    (!projectFilter || r.project === projectFilter);
  const filteredRows = searchRows(rows, search).filter(matchesFilters);
  const differences =
    currentRun?.results.filter((r) => r.outcome === "difference") || [];
  const visibleFindings = searchRows(
    currentTab === "differences"
      ? differences
      : currentRun?.results.filter((r) => r.outcome === resultFilter) || [],
    search,
  ).filter(matchesFilters);
  const activeTable =
    session?.extraction?.tables.filter((t) => t.page === page) || [];
  const previewRows =
    session?.extraction?.records.filter(
      (r) => Number(r.source_page) === page,
    ) || [];
  const selectedForSave =
    session?.extraction?.records.filter((r) =>
      previewSelection.has(r.record_id),
    ) || [];
  const requiresReview =
    session?.extraction?.tables.some(
      (t) =>
        t.requires_review &&
        selectedForSave.some((r) => r.table_id === t.table_id) &&
        reviewed[t.table_id] !== session.review_tokens?.[t.table_id],
    ) || false;
  const filterBar = (
    records: (Row | Finding)[],
    placeholder = "Search records…",
  ) => (
    <div className="filter-bar">
      <div className="search">
        <Search size={17} />
        <input
          aria-label={placeholder}
          placeholder={placeholder}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <select
        aria-label="Filter contractor"
        value={contractorFilter}
        onChange={(e) => setContractorFilter(e.target.value)}
      >
        <option value="">All contractors</option>
        {[...new Set(records.map((r) => r.contractor).filter(Boolean))]
          .sort()
          .map((c) => (
            <option key={c}>{c}</option>
          ))}
      </select>
      <select
        aria-label="Filter project"
        value={projectFilter}
        onChange={(e) => setProjectFilter(e.target.value)}
      >
        <option value="">All projects</option>
        {[...new Set(records.map((r) => r.project).filter(Boolean))]
          .sort()
          .map((c) => (
            <option key={c}>{c}</option>
          ))}
      </select>
    </div>
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a href="#main" className="brand" aria-label="Warren review home">
          <span className="brand-symbol">
            <Building2 size={25} />
          </span>
          <span>
            WARREN<span className="brand-sub">PROJECT REVIEW</span>
          </span>
        </a>
        <div className="workspace">
          <div className="workspace-icon">
            <Building2 size={18} />
          </div>
          <div>
            <strong>Warren Towers</strong>
            <small>Labor review workspace</small>
          </div>
          <ChevronDown size={15} />
        </div>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation">
          {tabs.map(({ id, name, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={currentTab === id ? "active" : ""}
              aria-current={currentTab === id ? "page" : undefined}
            >
              <Icon size={19} />
              <span>{name}</span>
              {id === "differences" && differences.length > 0 && (
                <b>{differences.length}</b>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-note">
            <ShieldCheck size={20} />
            <strong>Private by design</strong>
            <p>Your documents and data stay on this computer.</p>
          </div>
          <button
            className="sidebar-reference"
            onClick={() => setReferenceOpen(true)}
          >
            <Settings2 size={17} /> Reference schedule{" "}
            <ChevronRight size={15} />
          </button>
          <div className="workspace-user">
            <span>WT</span>
            <div>
              <strong>Review workspace</strong>
              <small>Local application</small>
            </div>
            <span className="online-dot" />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div>
            <span className="breadcrumb">Workspace</span>
            <ChevronRight size={14} />
            <strong>{tabs.find((t) => t.id === currentTab)?.name}</strong>
          </div>
          <div>
            <span className="local-status">
              <span className="online-dot" />
              Local processing
            </span>
            <button
              className="icon-button"
              title="Refresh workspace"
              aria-label="Refresh workspace"
              disabled={busy}
              onClick={() => act(load)}
            >
              <RefreshCw size={17} />
            </button>
          </div>
        </header>
        <main id="main">
          <section className="page-heading">
            <div>
              <div className="eyebrow">WARREN TOWERS · LABOR RATE REVIEW</div>
              <h1>{titles[currentTab]}</h1>
              <p>{subtitles[currentTab]}</p>
            </div>
            {currentTab !== "upload" && (
              <button className="primary" onClick={() => setTab("upload")}>
                <Plus size={17} />
                Upload document
              </button>
            )}
          </section>
          {error && (
            <div className="message error" role="alert">
              <AlertCircle size={20} />
              <span>{error}</span>
              <button
                className="icon-button"
                aria-label="Dismiss error"
                onClick={() => setError("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="message success" role="status">
              <CheckCircle2 size={20} />
              <span>{notice}</span>
              <button
                className="icon-button"
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                <X size={16} />
              </button>
            </div>
          )}
          {!loaded ? (
            <div className="loading">
              <LoaderCircle className="spin" />
              Loading your workspace…
            </div>
          ) : (
            <>
              {currentTab === "upload" && (
                <>
                  {sessions.length > 0 && (
                    <section className="card recent">
                      <div className="card-heading">
                        <div>
                          <h2>Documents to review</h2>
                          <p>
                            Documents needing attention appear first. Select one
                            to continue its review.
                          </p>
                        </div>
                        <span className="muted">
                          {sessions.length} documents
                        </span>
                      </div>
                      <label className="review-filter">
                        <input
                          type="checkbox"
                          checked={attentionOnly}
                          onChange={(e) => setAttentionOnly(e.target.checked)}
                        />
                        Show only documents needing attention (
                        {
                          sessions.filter((s) =>
                            needsAttention(s.review_summary?.status),
                          ).length
                        }
                        )
                      </label>
                      {attentionOnly &&
                        !sessions.some((s) =>
                          needsAttention(s.review_summary?.status),
                        ) && (
                          <p className="review-clear">
                            No documents need additional source review.
                          </p>
                        )}
                      <div className="recent-list">
                        {[...sessions]
                          .sort(
                            (a, b) =>
                              Number(needsAttention(b.review_summary?.status)) -
                              Number(needsAttention(a.review_summary?.status)),
                          )
                          .filter(
                            (s) =>
                              !attentionOnly ||
                              needsAttention(s.review_summary?.status),
                          )
                          .map((s) => (
                            <button
                              key={s.id}
                              onClick={() =>
                                act(async () =>
                                  adoptSession(
                                    await api<Session>(`/sessions/${s.id}`),
                                    true,
                                  ),
                                )
                              }
                            >
                              <span className="document-icon">
                                <FileText size={20} />
                              </span>
                              <span className="recent-name">
                                <strong>{s.filename}</strong>
                                <small>
                                  {s.contractor} · {formatDate(s.created_at)}
                                </small>
                              </span>
                              <Pill
                                tone={
                                  needsAttention(s.review_summary?.status)
                                    ? "warn"
                                    : s.review_summary?.status === "saved"
                                      ? "good"
                                      : s.status === "failed"
                                        ? "bad"
                                        : "neutral"
                                }
                              >
                                {reviewLabel(s.review_summary)}
                              </Pill>
                              <ChevronRight size={17} />
                            </button>
                          ))}
                      </div>
                    </section>
                  )}
                  <div className="steps" aria-label="Document review steps">
                    {[
                      "Upload document",
                      "Review extracted rates",
                      "Save & check",
                    ].map((name, i) => (
                      <div
                        key={name}
                        className={
                          (i === 0 && !session?.extraction) ||
                          (i === 1 && session?.extraction)
                            ? "step current"
                            : "step"
                        }
                      >
                        <span>{i + 1}</span>
                        <div>
                          <strong>{name}</strong>
                          <small>
                            {
                              [
                                "PDF or printed image",
                                "Verify against the source",
                                "Compare approved schedules",
                              ][i]
                            }
                          </small>
                        </div>
                        {i < 2 && <ChevronRight size={17} />}
                      </div>
                    ))}
                  </div>
                  {session &&
                  ["processing", "queued"].includes(session.status) ? (
                    <section className="card">
                      <div className="processing">
                        <LoaderCircle className="spin" size={32} />
                        <h2>Reading your document</h2>
                        <p>{session.filename}</p>
                        <progress
                          max={session.total_pages || 1}
                          value={session.page}
                        />
                        <span>
                          {session.total_pages
                            ? `Processing page ${session.page} of ${session.total_pages}`
                            : "Waiting to begin…"}
                        </span>
                        <small>
                          You can switch tabs while the document is processed.
                        </small>
                      </div>
                    </section>
                  ) : session?.status === "ready" && session.extraction ? (
                    <>
                      <section className="document-banner">
                        <div className="document-icon">
                          <FileText />
                        </div>
                        <div>
                          <h3>{session.filename}</h3>
                          <p>
                            {session.project} <span>·</span>{" "}
                            {session.contractor} <span>·</span>{" "}
                            {session.extraction.records.length} extracted rows
                          </p>
                        </div>
                        <Pill
                          tone={
                            needsAttention(session.review_summary?.status)
                              ? "warn"
                              : "good"
                          }
                        >
                          {reviewLabel(session.review_summary)}
                        </Pill>
                        <button
                          className="secondary"
                          onClick={() => {
                            setSession(null);
                            localStorage.removeItem("warren-session");
                          }}
                        >
                          Upload another
                        </button>
                      </section>
                      {session.extraction.pages.some(
                        (p) => p.status === "scan_not_processed",
                      ) && (
                        <div className="message warning">
                          <Info size={20} />
                          <span>
                            Some pages were not processed in this earlier
                            review. Upload the document again to retry.
                          </span>
                        </div>
                      )}
                      {session.review_summary && (
                        <ReviewChecklist
                          summary={session.review_summary}
                          tableId={targetTable}
                          page={page}
                          onJump={jumpToTable}
                          onPage={(n) => {
                            setPage(n);
                            setTargetTable("");
                          }}
                        />
                      )}
                      <div className="review-layout">
                        <section className="card source-card">
                          <div className="card-heading">
                            <h2>Original document</h2>
                            <select
                              aria-label="Source page"
                              value={page}
                              onChange={(e) => {
                                setPage(Number(e.target.value));
                                setTargetTable("");
                              }}
                            >
                              {session.extraction.pages.map((p, i) => (
                                <option key={i} value={Number(p.page)}>
                                  Page {String(p.page)}
                                  {session.review_summary?.items.some(
                                    (i) =>
                                      i.page === Number(p.page) &&
                                      (i.status === "mapping" ||
                                        i.status === "needs_review"),
                                  )
                                    ? " · Needs review"
                                    : ""}
                                </option>
                              ))}
                            </select>
                          </div>
                          <Source
                            url={`/api/sessions/${session.id}/pages/${page}`}
                          />
                        </section>
                        <section className="card extracted-card">
                          <div className="card-heading">
                            <div>
                              <h2>Printed labor rates</h2>
                              <p>
                                Compare each value with the source before
                                saving.
                              </p>
                            </div>
                            <Pill>{previewRows.length} rows</Pill>
                          </div>
                          {activeTable.map((table) => (
                            <div
                              key={table.table_id}
                              id={`review-table-${table.table_id}`}
                              role="group"
                              aria-label={`Review table on page ${table.page}`}
                              tabIndex={-1}
                              className={`table-review ${targetTable === table.table_id ? "target-table" : ""}`}
                            >
                              <div className="table-review-heading">
                                <strong>
                                  Page {table.page} ·{" "}
                                  {table.kind === "unfamiliar"
                                    ? "Column mapping"
                                    : table.kind === "labor_detail"
                                      ? "Worker detail"
                                      : table.kind === "labor_tally"
                                        ? "Labor tally"
                                        : "Labor rates"}
                                </strong>
                                {table.requires_review && (
                                  <Pill tone="warn">Review required</Pill>
                                )}
                              </div>
                              {table.kind === "unfamiliar" && (
                                <>
                                  <div className="table-scroll raw-table">
                                    <table>
                                      <thead>
                                        <tr>
                                          {table.headers.map((h, i) => (
                                            <th key={i}>{h}</th>
                                          ))}
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {table.rows
                                          .slice(0, 10)
                                          .map((row, i) => (
                                            <tr key={i}>
                                              {row.map((c, j) => (
                                                <td key={j}>{c}</td>
                                              ))}
                                            </tr>
                                          ))}
                                      </tbody>
                                    </table>
                                  </div>
                                  <Mapping
                                    table={table}
                                    disabled={busy}
                                    onApply={(columns) =>
                                      act(async () => {
                                        const next = await api<Session>(
                                          `/sessions/${session.id}/tables/${table.table_id}`,
                                          json("PUT", {
                                            revision: session.revision,
                                            columns,
                                          }),
                                        );
                                        adoptSession(next);
                                      })
                                    }
                                  />
                                </>
                              )}
                              {table.requires_review && (
                                <label className="review-check">
                                  <input
                                    type="checkbox"
                                    checked={
                                      reviewed[table.table_id] ===
                                      session.review_tokens?.[table.table_id]
                                    }
                                    disabled={busy}
                                    onChange={(e) =>
                                      confirmTable(
                                        table.table_id,
                                        e.target.checked,
                                      )
                                    }
                                  />
                                  <span>
                                    I checked the original printed table.
                                    Selected rows exclude handwriting and
                                    corrections.
                                  </span>
                                </label>
                              )}
                            </div>
                          ))}
                          {previewRows.length ? (
                            <RowsTable
                              rows={previewRows}
                              selected={previewSelection}
                              onSelect={setPreviewSelection}
                              technical={technical}
                              knownIds={rows.map((r) => r.record_id)}
                            />
                          ) : (
                            <Empty title="No ready rows on this page">
                              Choose another page, map a detected table, or
                              upload a clearer printed document.
                            </Empty>
                          )}
                          <label className="technical">
                            <input
                              type="checkbox"
                              checked={technical}
                              onChange={(e) => setTechnical(e.target.checked)}
                            />
                            Show technical columns and full IDs
                          </label>
                          <details className="extraction-notes">
                            <summary>Extraction notes & skipped pages</summary>
                            <pre>
                              {JSON.stringify(
                                {
                                  issues: session.extraction.issues,
                                  pages: session.extraction.pages,
                                },
                                null,
                                2,
                              )}
                            </pre>
                          </details>
                        </section>
                      </div>
                      <div className="save-bar">
                        <div>
                          <strong>{previewSelection.size} rows selected</strong>
                          <p>
                            {requiresReview
                              ? "Confirm the required source reviews before saving."
                              : "Previously saved rows are skipped automatically."}
                          </p>
                        </div>
                        <a
                          className="secondary"
                          href={`/api/sessions/${session.id}/evidence`}
                          download
                        >
                          <ArrowDownToLine size={16} />
                          Evidence
                        </a>
                        <button
                          className="primary"
                          disabled={
                            busy || !previewSelection.size || requiresReview
                          }
                          onClick={saveRows}
                        >
                          {busy ? (
                            <LoaderCircle size={17} className="spin" />
                          ) : (
                            <Check size={17} />
                          )}
                          Save selected rows
                        </button>
                        <button
                          className="secondary"
                          disabled={
                            busy ||
                            !session.saved_ids?.some((id) =>
                              session.extraction?.records.some(
                                (r) => r.record_id === id,
                              ),
                            )
                          }
                          onClick={() =>
                            runCheck(
                              session
                                .extraction!.records.filter((r) =>
                                  session.saved_ids?.includes(r.record_id),
                                )
                                .map((r) => r.record_id),
                            )
                          }
                        >
                          Check saved document
                          <ArrowRight size={16} />
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="upload-layout">
                      <section className="card upload-card">
                        <div className="card-heading">
                          <div>
                            <h2>Upload a change request</h2>
                            <p>Start with the document you want to review.</p>
                          </div>
                          <span className="small-step">STEP 01</span>
                        </div>
                        {session?.status === "failed" && (
                          <div className="message error" role="alert">
                            <AlertCircle size={20} />
                            <span>{session.error}</span>
                          </div>
                        )}
                        <form
                          onSubmit={(e) => {
                            e.preventDefault();
                            startUpload();
                          }}
                        >
                          <div
                            className={`drop-zone ${file ? "has-file" : ""}`}
                            onDragOver={(e) => e.preventDefault()}
                            onDrop={(e) => {
                              e.preventDefault();
                              setFile(e.dataTransfer.files[0] || null);
                            }}
                          >
                            <div className="upload-icon">
                              {file ? (
                                <FileCheck2 size={30} />
                              ) : (
                                <UploadCloud size={30} />
                              )}
                            </div>
                            <h3>
                              {file ? file.name : "Drop your document here"}
                            </h3>
                            <p>
                              {file
                                ? `${(file.size / 1024 / 1024).toFixed(1)} MB · Ready to extract`
                                : "or choose a file from your computer"}
                            </p>
                            <button
                              type="button"
                              className="secondary"
                              onClick={() => uploadRef.current?.click()}
                            >
                              {file ? "Choose another file" : "Browse files"}
                              <ArrowUpRight size={15} />
                            </button>
                            <input
                              ref={uploadRef}
                              aria-label="Choose document"
                              type="file"
                              accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff"
                              onChange={(e) =>
                                setFile(e.target.files?.[0] || null)
                              }
                              className="sr-only"
                            />
                            <small>PDF, PNG, JPG or TIFF · Up to 200 MB</small>
                          </div>
                          <div className="form-grid">
                            <label>
                              Project name <span className="required">*</span>
                              <input
                                required
                                maxLength={300}
                                value={project}
                                onChange={(e) => setProject(e.target.value)}
                                placeholder="e.g. Warren Towers"
                              />
                              <small>
                                The project this request belongs to.
                              </small>
                            </label>
                            <label>
                              Contractor <span className="required">*</span>
                              <input
                                required
                                maxLength={300}
                                value={contractor}
                                onChange={(e) => setContractor(e.target.value)}
                                placeholder="Contractor as printed"
                                list="contractor-names"
                              />
                              <small>Use the name shown on the document.</small>
                            </label>
                          </div>
                          <div className="form-footer">
                            <span>
                              <ShieldCheck size={15} />
                              Processed on this computer
                            </span>
                            <button
                              className="primary"
                              type="submit"
                              disabled={
                                busy ||
                                !file ||
                                !project.trim() ||
                                !contractor.trim()
                              }
                            >
                              {busy ? (
                                <LoaderCircle size={17} className="spin" />
                              ) : (
                                <FileSearch size={17} />
                              )}
                              Extract labor rates
                              <ArrowRight size={16} />
                            </button>
                          </div>
                        </form>
                      </section>
                      <aside className="guide-column">
                        <section className="card guide-card">
                          <div className="guide-symbol">
                            <ClipboardCheck size={23} />
                          </div>
                          <h2>Instructions</h2>
                          {[
                            {
                              title: "Upload your document",
                              text: "Add the change request and identify the project and contractor.",
                            },
                            {
                              title: "Review the printed values",
                              text: "See extracted labor rates next to the original document.",
                            },
                            {
                              title: "Check for differences",
                              text: "Compare saved rates with the applicable approved schedule.",
                            },
                          ].map((s, i) => (
                            <div className="guide-step" key={s.title}>
                              <span>{i + 1}</span>
                              <div>
                                <h3>{s.title}</h3>
                                <p>{s.text}</p>
                              </div>
                            </div>
                          ))}
                        </section>
                        <section className="evidence-note">
                          <ShieldCheck size={22} />
                          <div>
                            <h3>Evidence behind every finding</h3>
                            <p>
                              Every rate stays linked to its source page. You
                              stay in control of the final review.
                            </p>
                          </div>
                        </section>
                      </aside>
                    </div>
                  )}
                </>
              )}
              {currentTab === "data" && (
                <section className="card">
                  <div className="card-heading">
                    <div>
                      <h2>
                        Saved labor records <Pill>{rows.length}</Pill>
                      </h2>
                      <p>Original extracted values, saved after review.</p>
                    </div>
                    <button
                      className="primary"
                      disabled={busy || !selected.size}
                      onClick={() => runCheck([...selected])}
                    >
                      <ClipboardCheck size={17} />
                      Check selected ({selected.size})
                    </button>
                  </div>
                  {rows.length ? (
                    <>
                      {filterBar(rows)}
                      <div className="table-actions">
                        <span>
                          {filteredRows.length} of {rows.length} records
                        </span>
                        <button
                          className="text-button"
                          disabled={!selected.size}
                          onClick={() => openEdit([...selected])}
                        >
                          <Settings2 size={15} />
                          Set comparison details ({selected.size})
                        </button>
                      </div>
                      <RowsTable
                        rows={filteredRows}
                        selected={selected}
                        onSelect={setSelected}
                        onOpen={setPreviewRow}
                        technical={technical}
                        knownIds={rows.map((r) => r.record_id)}
                      />
                      <label className="technical">
                        <input
                          type="checkbox"
                          checked={technical}
                          onChange={(e) => setTechnical(e.target.checked)}
                        />
                        Show technical columns and full IDs
                      </label>
                      <p className="table-note">
                        Blank values are unknown. Short record IDs are display
                        labels; full IDs are preserved in evidence and exports.
                      </p>
                    </>
                  ) : (
                    <Empty
                      title="Your dataset starts here"
                      action={
                        <button
                          className="primary"
                          onClick={() => setTab("upload")}
                        >
                          Upload a document
                          <ArrowRight size={16} />
                        </button>
                      }
                    >
                      Upload a document, review its printed labor rates, then
                      save selected rows to build your dataset.
                    </Empty>
                  )}
                </section>
              )}
              {(currentTab === "checks" || currentTab === "differences") && (
                <>
                  <div className="reference-banner">
                    <span className="reference-icon">
                      <ShieldCheck size={21} />
                    </span>
                    <div>
                      <strong>
                        {reference
                          ? "Approved rate reference"
                          : "No reference schedule active"}
                      </strong>
                      <p>
                        {reference
                          ? `${reference.name} · ${reference.rows.length} schedules · Version ${short(reference.id)}`
                          : "Upload a reference CSV to begin checking labor rates."}
                      </p>
                    </div>
                    <button
                      className="text-button"
                      disabled={busy || !reference}
                      onClick={() =>
                        act(async () => {
                          setClassificationMap(
                            await api<ClassificationGraph>(
                              "/classification-map",
                            ),
                          );
                        })
                      }
                    >
                      Classification map
                      <ArrowUpRight size={15} />
                    </button>
                    <button
                      className="text-button"
                      onClick={() => setReferenceOpen(true)}
                    >
                      Manage schedule
                      <ArrowUpRight size={15} />
                    </button>
                  </div>
                  {currentTab === "checks" && (
                    <div className="check-actions">
                      <span>{rows.length} saved records available</span>
                      <button
                        className="primary"
                        disabled={busy || !rows.length || !reference}
                        onClick={() => runCheck(rows.map((r) => r.record_id))}
                      >
                        <ClipboardCheck size={17} />
                        {busy ? "Checking…" : "Check all saved records"}
                      </button>
                    </div>
                  )}
                  {currentRun ? (
                    <>
                      <div className="run-toolbar">
                        <label>
                          Check run
                          <select
                            aria-label="Check run"
                            value={currentRun.id}
                            onChange={(e) => setCurrentRun(e.target.value)}
                          >
                            {runs.map((r) => (
                              <option key={r.id} value={r.id}>
                                {formatDate(r.created_at)} · {r.results.length}{" "}
                                rates · {r.counts.difference} differences
                              </option>
                            ))}
                          </select>
                        </label>
                        <span>
                          Reference version{" "}
                          <code>{short(currentRun.reference_version)}</code>
                        </span>
                      </div>
                      {currentRun.stale && (
                        <div className="message warning">
                          <AlertCircle size={20} />
                          <span>
                            This run is outdated. Rerun the check to use the
                            current reference, comparison details and
                            classification relationships.
                          </span>
                          <button
                            className="secondary"
                            disabled={busy}
                            onClick={() => runCheck(currentRun.record_ids)}
                          >
                            Rerun check
                          </button>
                        </div>
                      )}
                      {currentTab === "checks" ? (
                        <div className="stats-grid">
                          {[
                            {
                              id: "match",
                              title: "Matching rates",
                              icon: CheckCircle2,
                              tone: "good",
                              text: "Match an applicable approved schedule",
                            },
                            {
                              id: "difference",
                              title: "Rate differences",
                              icon: SlidersHorizontal,
                              tone: "bad",
                              text: "Submitted and approved rates differ",
                            },
                            {
                              id: "needs_review",
                              title: "Needs review",
                              icon: CircleHelp,
                              tone: "warn",
                              text: "More information or reference review needed",
                            },
                          ].map(({ id, title, icon: Icon, tone, text }) => (
                            <button
                              className={`stat-card ${resultFilter === id ? "selected" : ""}`}
                              key={id}
                              onClick={() => setResultFilter(id)}
                            >
                              <span className={`stat-icon ${tone}`}>
                                <Icon size={21} />
                              </span>
                              <span className="stat-number">
                                {currentRun.counts[id]}
                              </span>
                              <strong>{title}</strong>
                              <small>{text}</small>
                            </button>
                          ))}
                        </div>
                      ) : (
                        <div className="differences-intro">
                          <div>
                            <span className="difference-total">
                              {differences.length.toString().padStart(2, "0")}
                            </span>
                            <div>
                              <h2>Confirmed rate differences</h2>
                              <p>
                                Out of {currentRun.results.length} rates checked
                                · {currentRun.counts.needs_review} need review
                              </p>
                            </div>
                          </div>
                          <a
                            className="primary"
                            href={`/api/checks/${currentRun.id}/differences.csv`}
                            download
                          >
                            <ArrowDownToLine size={17} />
                            Download differences CSV
                          </a>
                        </div>
                      )}
                      <section className="card findings-card">
                        <div className="card-heading">
                          <div>
                            <h2>
                              {currentTab === "differences"
                                ? "Differences"
                                : resultFilter === "needs_review"
                                  ? "Items needing review"
                                  : resultFilter === "match"
                                    ? "Matching rates"
                                    : "Rate differences"}{" "}
                              <Pill>{visibleFindings.length}</Pill>
                            </h2>
                            <p>
                              {currentTab === "differences"
                                ? "Each row is one source record and one differing rate type."
                                : "Open a result to see its source evidence and comparison details."}
                            </p>
                          </div>
                          {currentTab === "checks" &&
                            resultFilter === "difference" && (
                              <button
                                className="text-button"
                                onClick={() => setTab("differences")}
                              >
                                Open Differences tab
                                <ArrowRight size={16} />
                              </button>
                            )}
                        </div>
                        {filterBar(
                          currentTab === "differences"
                            ? differences
                            : currentRun.results,
                          "Search findings…",
                        )}
                        {visibleFindings.length ? (
                          <div
                            className="table-scroll"
                            tabIndex={0}
                            role="region"
                            aria-label="Rate findings table"
                          >
                            <table>
                              <thead>
                                <tr>
                                  <th>Contractor / classification</th>
                                  <th>Source</th>
                                  <th>Rate type</th>
                                  <th>Submitted</th>
                                  <th>Approved</th>
                                  <th>
                                    {currentTab === "differences" ||
                                    resultFilter === "difference"
                                      ? "Difference / hour"
                                      : "Finding"}
                                  </th>
                                  <th>
                                    <span className="sr-only">Review</span>
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                {visibleFindings.map((f) => (
                                  <tr key={f.finding_id}>
                                    <td>
                                      <strong>{display(f.contractor)}</strong>
                                      <small>
                                        {f.classification ||
                                          "Checked by contractor and rate"}
                                      </small>
                                    </td>
                                    <td>
                                      <span
                                        className="source-filename"
                                        title={f.source_file}
                                      >
                                        {f.source_file}
                                      </span>
                                      <small>
                                        Page {f.source_page} ·{" "}
                                        <code>{short(f.record_id)}</code>
                                      </small>
                                    </td>
                                    <td>
                                      <Pill>{rateTypeLabel(f.rate_type)}</Pill>
                                    </td>
                                    <td className="numeric">
                                      {money(f.submitted_rate)}
                                    </td>
                                    <td className="numeric">
                                      {f.approved_rate
                                        ? money(f.approved_rate)
                                        : f.approved_rates?.length
                                          ? f.approved_rates
                                              .map(money)
                                              .join(" / ")
                                          : "—"}
                                    </td>
                                    <td>
                                      {f.finding_kind ===
                                      "rate_not_in_schedule" ? (
                                        <Pill tone="bad">
                                          Not in approved rates
                                        </Pill>
                                      ) : f.outcome === "difference" ? (
                                        <span className="delta">
                                          {Number(f.difference_per_hour) > 0
                                            ? "+"
                                            : ""}
                                          {money(f.difference_per_hour)}
                                        </span>
                                      ) : (
                                        <span
                                          className={`result-reason ${f.outcome === "match" ? "match-reason" : ""}`}
                                        >
                                          {currentRun?.rules_changed
                                            ? "Rerun this check to apply the current matching rules."
                                            : f.reason}
                                        </span>
                                      )}
                                    </td>
                                    <td>
                                      <button
                                        className="text-button"
                                        onClick={() => setFinding(f)}
                                      >
                                        Review
                                        <ArrowUpRight size={14} />
                                      </button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <Empty
                            title={
                              search || contractorFilter || projectFilter
                                ? "No findings match your filters"
                                : currentTab === "differences"
                                  ? "No confirmed rate differences"
                                  : "No results in this category"
                            }
                          >
                            {currentTab === "differences" &&
                            currentRun.counts.needs_review > 0
                              ? `${currentRun.counts.needs_review} checks still need review. Resolve them in Labor checks to complete the comparison.`
                              : "Try another category or clear your filters to see more results."}
                          </Empty>
                        )}
                      </section>
                    </>
                  ) : (
                    <section className="card">
                      <Empty
                        title={
                          currentTab === "differences"
                            ? "Differences will appear here"
                            : "Ready for your first rate check"
                        }
                        action={
                          <button
                            className="primary"
                            disabled={busy || !rows.length || !reference}
                            onClick={() =>
                              runCheck(rows.map((r) => r.record_id))
                            }
                          >
                            Check saved labor rates
                            <ArrowRight size={16} />
                          </button>
                        }
                      >
                        Save reviewed labor records and activate a reference
                        schedule, then run a check. Matches and unresolved
                        checks stay in Labor checks.
                      </Empty>
                    </section>
                  )}
                </>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              <ShieldCheck size={14} />
              Local processing · Human-reviewed decisions
            </span>
            <span>Warren Towers / Labor review</span>
          </footer>
        </main>
      </div>
      {classificationMap && (
        <ClassificationMap
          graph={classificationMap}
          initialContractor={currentRun?.results[0]?.contractor || ""}
          busy={busy}
          error={error}
          onClose={() => setClassificationMap(null)}
          onSave={(contractor, source, target) =>
            act(async () => {
              await api(
                "/classification-aliases",
                json("PUT", {
                  contractor,
                  source_label: source,
                  target_position: target,
                }),
              );
              setClassificationMap(
                await api<ClassificationGraph>("/classification-map"),
              );
              await load();
              setNotice(
                "Classification relationship saved. Rerun checks to use it.",
              );
            })
          }
          onDelete={(id) =>
            act(async () => {
              await api(`/classification-aliases/${id}`, { method: "DELETE" });
              setClassificationMap(
                await api<ClassificationGraph>("/classification-map"),
              );
              await load();
            })
          }
        />
      )}
      <datalist id="contractor-names">
        {[
          ...new Set(
            reference?.rows.map((r) => r.subcontractor).filter(Boolean) || [],
          ),
        ]
          .sort()
          .map((c) => (
            <option key={c} value={c} />
          ))}
      </datalist>
      <datalist id="classification-names">
        {[
          ...new Set(
            reference?.rows.map((r) => r.position).filter(Boolean) || [],
          ),
        ]
          .sort()
          .map((c) => (
            <option key={c} value={c} />
          ))}
      </datalist>
      {referenceOpen && (
        <ReferenceDialog
          reference={reference}
          preview={referencePreview}
          busy={busy}
          error={error}
          onClose={() => {
            setReferenceOpen(false);
            setReferencePreview(null);
          }}
          onDiscard={() => setReferencePreview(null)}
          onPreview={(file) =>
            act(async () => {
              const form = new FormData();
              form.append("file", file);
              setReferencePreview(
                await api<Reference>("/reference/preview", {
                  method: "POST",
                  body: form,
                }),
              );
            })
          }
          onActivate={() =>
            act(async () => {
              if (!referencePreview) return;
              await api(
                "/reference/activate",
                json("POST", { reference_id: referencePreview.id }),
              );
              setReferencePreview(null);
              await load();
              setReferenceOpen(false);
              setNotice(
                "Reference schedule activated. Previous checks retain their original schedule version.",
              );
            })
          }
        />
      )}
      {(previewRow || finding) && (
        <FindingDialog
          finding={finding}
          previewRow={previewRow}
          records={rows}
          rulesChanged={currentRun?.rules_changed}
          onClose={() => {
            setFinding(null);
            setPreviewRow(null);
          }}
          onEdit={openEdit}
        />
      )}
      {editIds.length > 0 && (
        <ComparisonDetailsDialog
          recordIds={editIds}
          records={rows}
          edit={edit}
          busy={busy}
          error={error}
          onChange={setEdit}
          onSave={saveDetails}
          onClose={() => setEditIds([])}
        />
      )}
    </div>
  );
}
