import DocumentWorkflowNav, { type DocumentView } from "./DocumentWorkflowNav";
import ReferenceDialog from "./ReferenceDialog";
import FindingDialog from "./FindingDialog";
import SavedDocuments from "./SavedDocuments";
import DeleteDocumentDialog from "./DeleteDocumentDialog";
import DocumentSourceDialog from "./DocumentSourceDialog";
import WorkDatesDialog, {
  WorkPeriodFields,
  type WorkDatesTarget,
  type WorkDatesUpdate,
} from "./WorkDatesDialog";
import "./documents.css";
import ResultsOverview from "./ResultsOverview";
import ResultsReport from "./ResultsReport";
import { documents, metrics } from "./results";
import "./results.css";
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
  Printer,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  UploadCloud,
  X,
  AlertCircle,
} from "lucide-react";
import { api, json } from "./api";
import type {
  Row,
  Session,
  Reference,
  Run,
  Finding,
  SavedDocument,
  DeletionPreview,
} from "./types";

import {
  formatDate,
  withWorkDates,
  money,
  display,
  short,
  rateTypeLabel,
  searchRows,
} from "./presentation";
import { Pill, Empty, Source, RowsTable, Mapping } from "./components";

type Tab = "upload" | "documents" | "data" | "checks" | "differences";
const tabs: { id: Tab; name: string; icon: typeof FileText }[] = [
  { id: "upload", name: "Upload & review", icon: UploadCloud },
  { id: "documents", name: "Saved documents", icon: FolderOpen },
  { id: "data", name: "Saved data", icon: FolderOpen },
  { id: "checks", name: "Labor checks", icon: ClipboardCheck },
  { id: "differences", name: "Differences", icon: SlidersHorizontal },
];
const titles = {
  upload: "Upload & review",
  documents: "Saved documents",
  data: "Saved data",
  checks: "Labor checks",
  differences: "Differences",
};
const subtitles = {
  upload: "Upload a change request and review its extracted labor rates.",
  documents:
    "Browse saved documents, inspect their source, or start a fresh review.",
  data: "Search saved labor records or select records to check.",
  checks:
    "Compare document rates against approved rates for the contractor and work dates.",
  differences:
    "Review and export rates that differ from the applicable approved schedules.",
};
export default function App({
  account,
}: {
  account?: {
    email: string;
    onLogout: () => void;
    onManageAccounts?: () => void;
    busy: boolean;
    error: string;
  };
}) {
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
  const [documentView, setDocumentViewState] = useState<DocumentView>(() => {
    const saved = localStorage.getItem("warren-document-view");
    return saved === "upload" || saved === "review"
      ? saved
      : localStorage.getItem("warren-session")
        ? "review"
        : "upload";
  });
  const [processStep, setProcessStep] = useState(
    documentView === "upload" ? 0 : 1,
  );
  const setDocumentView = (view: DocumentView) => {
    setDocumentViewState(view);
    setProcessStep(view === "upload" ? 0 : 1);
    localStorage.setItem("warren-document-view", view);
  };
  const openUpload = () => {
    setTab("upload");
    setDocumentView("upload");
  };
  const reviewDrafts = useRef(
    new Map<
      string,
      { revision: number; page: number; selected: string[]; target: string }
    >(),
  );
  const [reviewDestination, setReviewDestination] = useState<
    "checklist" | "save" | null
  >(null);
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
  const [workStart, setWorkStart] = useState("");
  const [workEnd, setWorkEnd] = useState("");
  const [dateTarget, setDateTarget] = useState<WorkDatesTarget | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set()),
    [previewSelection, setPreviewSelection] = useState<Set<string>>(new Set()),
    [reviewed, setReviewed] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1),
    [search, setSearch] = useState(""),
    [contractorFilter, setContractorFilter] = useState(""),
    [projectFilter, setProjectFilter] = useState(""),
    [technical, setTechnical] = useState(false),
    [resultFilter, setResultFilter] = useState("needs_review");
  const [resultDocument, setResultDocument] = useState("");
  const [savedDocuments, setSavedDocuments] = useState<SavedDocument[]>([]);
  const [focusedDocument, setFocusedDocument] = useState("");
  const [savedDataDocument, setSavedDataDocument] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{
    route: string;
    preview: DeletionPreview;
  } | null>(null);
  const [sourceDocument, setSourceDocument] = useState<{
    document_id: string;
    filename: string;
    page_count: number;
  } | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
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
  useEffect(() => {
    if (documentView !== "review" || !reviewDestination) return;
    const element = document.getElementById(
      reviewDestination === "save"
        ? "document-save-actions"
        : "review-checklist",
    );
    if (element) {
      element.focus({ preventScroll: true });
      element.scrollIntoView({ block: "start", behavior: "smooth" });
      setReviewDestination(null);
    }
  }, [documentView, reviewDestination, session?.status]);
  const [classificationMap, setClassificationMap] =
    useState<ClassificationGraph | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);
  const currentRun = runs.find((r) => r.id === runId) || runs[0];
  const reviewSessions = sessions.filter(
    (s) => s.review_summary?.status !== "saved",
  );
  const currentTab = tabs.some((t) => t.id === tab) ? tab : "upload";
  const setCurrentRun = (id: string) => {
    setRunId(id);
    setResultDocument("");
    setReportOpen(false);
    localStorage.setItem("warren-run", id);
  };
  const load = async () => {
    const [data, history, refs, checks, documents] = await Promise.all([
      api<{ records: Row[]; details: Record<string, Row> }>("/records"),
      api<Session[]>("/sessions"),
      api<{ active: Reference | null }>("/reference"),
      api<Run[]>("/checks"),
      api<SavedDocument[]>("/documents"),
    ]);
    setRows(data.records);
    setSavedDocuments(documents);
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
        e instanceof Error ? e.message : "The request failed. Try again.",
      );
    } finally {
      setBusy(false);
    }
  };
  const adoptSession = (next: Session, openReview = false) => {
    if (!openReview && next.review_summary?.status === "saved") {
      setSession(null);
      localStorage.removeItem("warren-session");
      if (currentTab === "upload" && documentView === "review") {
        setFocusedDocument(next.extraction!.document_id);
        setTab("documents");
        setDocumentView("upload");
      }
      return;
    }
    if (session?.extraction)
      reviewDrafts.current.set(session.id, {
        revision: session.revision,
        page,
        selected: [...previewSelection],
        target: targetTable,
      });
    const draft = reviewDrafts.current.get(next.id);
    const restore = draft?.revision === next.revision ? draft : undefined;
    setSession(next);
    localStorage.setItem("warren-session", next.id);
    setReviewed(next.reviewed || {});
    setTargetTable(restore?.target || "");
    const available = new Set(
      (next.extraction?.records || [])
        .filter((r) => !next.saved_ids?.includes(r.record_id))
        .map((r) => r.record_id),
    );
    setPreviewSelection(
      new Set(
        restore
          ? restore.selected.filter((id) => available.has(id))
          : [...available],
      ),
    );
    setPage(
      restore?.page ||
        next.review_summary?.items.find(
          (i) => i.status === "mapping" || i.status === "needs_review",
        )?.page ||
        next.extraction?.tables[0]?.page ||
        1,
    );
    if (openReview) setDocumentView("review");
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
                adoptSession(next, documentView === "review");
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
  }, [session?.id, session?.status, documentView]);
  const hasProcessingDocuments = sessions.some((document) =>
    ["queued", "processing"].includes(document.status),
  );
  useEffect(() => {
    if (!loaded || currentTab !== "upload" || documentView !== "review") return;
    let active = true;
    const refreshDocuments = () =>
      api<Session[]>("/sessions")
        .then((documents) => {
          if (active) setSessions(documents);
        })
        .catch((error) => {
          if (active) setError(error.message);
        });
    void refreshDocuments();
    const timer = hasProcessingDocuments
      ? setInterval(refreshDocuments, 2000)
      : undefined;
    return () => {
      active = false;
      if (timer) clearInterval(timer);
    };
  }, [loaded, currentTab, documentView, hasProcessingDocuments]);
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
      form.append("work_start", workStart);
      form.append("work_end", workEnd);
      const next = await api<Session>("/sessions", {
        method: "POST",
        body: form,
      });
      adoptSession(next, true);
      setFile(null);
      setWorkStart("");
      setWorkEnd("");
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
      if (next.review_summary?.status === "saved") {
        setFocusedDocument(next.extraction!.document_id);
        setTab("documents");
        setDocumentView("upload");
        setSession(null);
        localStorage.removeItem("warren-session");
        reviewDrafts.current.delete(next.id);
      }
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
  const openWorkDates = (
    scope: WorkDatesTarget["scope"],
    ids = [...previewSelection],
  ) => {
    if (!session?.extraction) return;
    setError("");
    setDateTarget({
      route: `/sessions/${session.id}`,
      filename: session.filename,
      records: session.extraction.records,
      details: session.comparison_details || {},
      selected: ids,
      page,
      scope,
      revision: session.revision,
    });
  };
  const applyWorkDates = (body: WorkDatesUpdate) =>
    act(async () => {
      if (!dateTarget) return;
      const result = await api<{ updated: number; targeted: number }>(
        `${dateTarget.route}/work-dates`,
        json("POST", body),
      );
      if (session && dateTarget.route === `/sessions/${session.id}`) {
        setSession(await api<Session>(`/sessions/${session.id}`));
      }
      await load();
      setDateTarget(null);
      setNotice(
        `${body.clear ? "Entered dates removed from" : "Work dates applied to"} ${result.updated} of ${result.targeted} rows. Run the check again to update results.`,
      );
    });
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
  const openDelete = (route: string) =>
    act(async () => {
      const preview = await api<DeletionPreview>(`${route}/deletion-preview`);
      setDeleteTarget({ route, preview });
    });
  const removeDocument = () =>
    act(async () => {
      if (!deleteTarget) return;
      const removed = await api<{
        session_ids: string[];
        record_ids: string[];
        run_ids: string[];
      }>(
        deleteTarget.route,
        json("DELETE", { confirmation: deleteTarget.preview.confirmation }),
      );
      for (const id of removed.session_ids) reviewDrafts.current.delete(id);
      if (session && removed.session_ids.includes(session.id)) {
        setSession(null);
        setPreviewSelection(new Set());
        setReviewed({});
        setTargetTable("");
        localStorage.removeItem("warren-session");
        setDocumentView("upload");
      }
      setSelected(
        (previous) =>
          new Set(
            [...previous].filter((id) => !removed.record_ids.includes(id)),
          ),
      );
      if (currentRun && removed.run_ids.includes(currentRun.id)) {
        setRunId("");
        localStorage.removeItem("warren-run");
        setReportOpen(false);
      }
      if (savedDataDocument === deleteTarget.preview.document_id)
        setSavedDataDocument("");
      if (resultDocument === deleteTarget.preview.document_id)
        setResultDocument("");
      setFinding(null);
      setPreviewRow(null);
      await load();
      setDeleteTarget(null);
      setNotice(
        `${deleteTarget.preview.filename} deleted. Upload it again to start a fresh review.`,
      );
    });
  const filteredRows = searchRows(
    rows.map((r) => withWorkDates(r, details[r.record_id])),
    search,
  )
    .filter(matchesFilters)
    .filter((r) => !savedDataDocument || r.document_id === savedDataDocument);
  const scopedResults = (currentRun?.results || [])
    .filter(matchesFilters)
    .filter((r) => !resultDocument || r.document_id === resultDocument);
  const scopedCounts = metrics(scopedResults);
  const differences = scopedResults.filter((r) => r.outcome === "difference");
  const visibleFindings = searchRows(
    currentTab === "differences"
      ? differences
      : scopedResults.filter((r) => r.outcome === resultFilter),
    search,
  ).filter(matchesFilters);
  const activeTable =
    session?.extraction?.tables.filter((t) => t.page === page) || [];
  const previewRows =
    session?.extraction?.records
      .filter((r) => Number(r.source_page) === page)
      .map((r) =>
        withWorkDates(r, session.comparison_details?.[r.record_id]),
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
      {currentTab !== "checks" && currentTab !== "differences" && (
        <>
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
        </>
      )}
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
            <strong>{account ? "Shared workspace" : "Local storage"}</strong>
            <p>
              {account
                ? "Files are available to approved workspace members."
                : "Files are stored on this computer."}
            </p>
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
              <small className="account-email">
                {account?.email ?? "Local application"}
              </small>
            </div>
            <span className="online-dot" />
          </div>
          {account && (
            <>
              {account.onManageAccounts && (
                <button
                  className="secondary account-signout"
                  onClick={account.onManageAccounts}
                >
                  Manage accounts
                </button>
              )}
              <button
                className="secondary account-signout"
                onClick={account.onLogout}
                disabled={account.busy}
              >
                Sign out
              </button>
              {account.error && (
                <p role="alert" className="account-error">
                  {account.error}
                </p>
              )}
            </>
          )}
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
              {account ? "Private processing" : "Local processing"}
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
            {(currentTab !== "upload" || documentView === "review") && (
              <button className="primary" disabled={busy} onClick={openUpload}>
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
                  <DocumentWorkflowNav
                    view={documentView}
                    count={reviewSessions.length}
                    busy={busy}
                    onChange={setDocumentView}
                  />
                  <section
                    id="document-workflow-panel"
                    role="tabpanel"
                    aria-labelledby={`document-tab-${documentView}`}
                  >
                    {documentView === "review" && reviewSessions.length > 0 && (
                      <section className="card recent">
                        <div className="card-heading">
                          <div>
                            <h2>Documents to review</h2>
                            <p>
                              Documents needing attention appear first. Select
                              one to continue its review.
                            </p>
                          </div>
                          <span className="muted">
                            {reviewSessions.length} documents
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
                            reviewSessions.filter((s) =>
                              needsAttention(s.review_summary?.status),
                            ).length
                          }
                          )
                        </label>
                        {attentionOnly &&
                          !reviewSessions.some((s) =>
                            needsAttention(s.review_summary?.status),
                          ) && (
                            <p className="review-clear">
                              No documents need additional source review.
                            </p>
                          )}
                        <div className="recent-list">
                          {[...reviewSessions]
                            .sort(
                              (a, b) =>
                                Number(
                                  needsAttention(b.review_summary?.status),
                                ) -
                                Number(
                                  needsAttention(a.review_summary?.status),
                                ),
                            )
                            .filter(
                              (s) =>
                                !attentionOnly ||
                                needsAttention(s.review_summary?.status),
                            )
                            .map((s) => (
                              <div className="review-document-row" key={s.id}>
                                <button
                                  className="review-document-open"
                                  disabled={busy}
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
                                      {s.contractor} ·{" "}
                                      {formatDate(s.created_at)}
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
                                <button
                                  className="icon-button delete-document"
                                  aria-label={`Delete ${s.filename}`}
                                  disabled={busy}
                                  onClick={() =>
                                    openDelete(`/sessions/${s.id}`)
                                  }
                                >
                                  <Trash2 size={17} />
                                </button>
                              </div>
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
                        <button
                          type="button"
                          key={name}
                          disabled={busy || (i === 2 && !session?.extraction)}
                          aria-current={i === processStep ? "step" : undefined}
                          onClick={() => {
                            setDocumentView(i === 0 ? "upload" : "review");
                            setProcessStep(i);
                            setReviewDestination(
                              i === 2 ? "save" : i === 1 ? "checklist" : null,
                            );
                          }}
                          className={
                            i === processStep ? "step current" : "step"
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
                        </button>
                      ))}
                    </div>
                    {documentView === "review" && !session ? (
                      <section className="card">
                        <Empty title="Select a document">
                          Choose a document from the list to continue reviewing,
                          or open Upload document to add a file.
                        </Empty>
                      </section>
                    ) : documentView === "review" &&
                      session?.status === "failed" ? (
                      <section className="card">
                        <div className="message error" role="alert">
                          <AlertCircle size={20} />
                          <span>{session.error}</span>
                        </div>
                        <button
                          className="secondary retry-upload"
                          onClick={openUpload}
                        >
                          Upload document again
                        </button>
                      </section>
                    ) : documentView === "review" &&
                      session &&
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
                    ) : documentView === "review" &&
                      session?.status === "ready" &&
                      session.extraction ? (
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
                          <button className="secondary" onClick={openUpload}>
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
                            <div
                              className="work-date-panel"
                              role="region"
                              aria-label="Document work dates"
                            >
                              <strong>Work dates</strong>
                              <p>
                                Set a range once for the document, this page, or
                                selected rows. Missing dates can be resolved
                                later.
                              </p>
                              <div className="saved-document-actions">
                                <button
                                  className="secondary"
                                  disabled={
                                    busy || !session.extraction.records.length
                                  }
                                  onClick={() => openWorkDates("document")}
                                >
                                  Set document dates
                                </button>
                                <button
                                  className="secondary"
                                  disabled={busy || !previewRows.length}
                                  onClick={() => openWorkDates("page")}
                                >
                                  Set dates for this page
                                </button>
                                <button
                                  className="secondary"
                                  disabled={busy || !previewSelection.size}
                                  onClick={() => openWorkDates("rows")}
                                >
                                  Set dates for selected rows (
                                  {previewSelection.size})
                                </button>
                              </div>
                              <small>
                                {
                                  session.extraction.records.filter(
                                    (r) =>
                                      !(
                                        session.comparison_details?.[
                                          r.record_id
                                        ]?.work_start || r.work_start
                                      ),
                                  ).length
                                }{" "}
                                of {session.extraction.records.length} rows
                                still need work dates. Dates shown below include
                                entered comparison dates.
                              </small>
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
                                onOpen={(r) =>
                                  openWorkDates("rows", [r.record_id])
                                }
                                openLabel="Set dates"
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
                              <summary>
                                Extraction notes & skipped pages
                              </summary>
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
                        <div
                          className="save-bar"
                          id="document-save-actions"
                          tabIndex={-1}
                          role="region"
                          aria-label="Save and check document"
                        >
                          <div>
                            <strong>
                              {previewSelection.size} rows selected
                            </strong>
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
                              <p>
                                Select a PDF or image to extract labor rates.
                              </p>
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
                              <small>
                                PDF, PNG, JPG or TIFF · Up to 200 MB
                              </small>
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
                                  onChange={(e) =>
                                    setContractor(e.target.value)
                                  }
                                  placeholder="Contractor as printed"
                                  list="contractor-names"
                                />
                                <small>
                                  Use the name shown on the document.
                                </small>
                              </label>
                            </div>
                            <fieldset className="upload-work-dates">
                              <legend>
                                Work dates{" "}
                                <span className="muted">(optional)</span>
                              </legend>
                              <p>
                                Know the work period for this document? Enter it
                                once to fill rows missing printed dates. Leave
                                both blank to set dates by page or row later.
                              </p>
                              <WorkPeriodFields
                                start={workStart}
                                end={workEnd}
                                onStart={setWorkStart}
                                onEnd={setWorkEnd}
                              />
                              <small>
                                Existing printed work dates are kept. Use the
                                actual work period, rather than the invoice or
                                approval date.
                              </small>
                            </fieldset>
                            <div className="form-footer">
                              <span>
                                <ShieldCheck size={15} />
                                {account
                                  ? "Processed in this workspace"
                                  : "Processed on this computer"}
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
                                title: "Upload document",
                                text: "Choose a document and enter its project and contractor.",
                              },
                              {
                                title: "Review the printed values",
                                text: "Compare the extracted values with the source page.",
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
                              <h3>Source documents</h3>
                              <p>
                                Open a result to view its source page and
                                reference schedule.
                              </p>
                            </div>
                          </section>
                        </aside>
                      </div>
                    )}
                  </section>
                </>
              )}
              {currentTab === "documents" && (
                <SavedDocuments
                  documents={savedDocuments}
                  busy={busy}
                  canCheck={Boolean(reference)}
                  focused={focusedDocument}
                  onUpload={openUpload}
                  onDelete={(id) => openDelete(`/documents/${id}`)}
                  onDates={(doc) =>
                    act(async () => {
                      const review =
                        doc.status === "partially_saved" && doc.session_id
                          ? await api<Session>(`/sessions/${doc.session_id}`)
                          : null;
                      const documentRows =
                        review?.extraction?.records ||
                        rows.filter((r) => r.document_id === doc.document_id);
                      setDateTarget({
                        route: review?.extraction
                          ? `/sessions/${review.id}`
                          : `/documents/${doc.document_id}`,
                        filename: doc.filename,
                        records: documentRows,
                        details: review?.comparison_details || details,
                        selected: [],
                        page: Number(documentRows[0]?.source_page || 1),
                        scope: "document",
                        revision: review?.revision,
                      });
                    })
                  }
                  onRates={(id) => {
                    setSavedDataDocument(id);
                    setSelected(new Set());
                    setTab("data");
                  }}
                  onSource={(doc) =>
                    act(async () => {
                      const info = await api<{ page_count: number }>(
                        `/documents/${doc.document_id}/source-info`,
                      );
                      setSourceDocument({ ...doc, ...info });
                    })
                  }
                  onReview={(id) =>
                    act(async () => {
                      adoptSession(await api<Session>(`/sessions/${id}`), true);
                      setTab("upload");
                    })
                  }
                  onCheck={runCheck}
                />
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
                      <label className="saved-document-filter">
                        Document
                        <select
                          aria-label="Filter saved document"
                          value={savedDataDocument}
                          onChange={(e) => {
                            setSavedDataDocument(e.target.value);
                            setSelected(new Set());
                          }}
                        >
                          <option value="">All saved documents</option>
                          {savedDocuments.map((d) => (
                            <option key={d.document_id} value={d.document_id}>
                              {d.filename} · {short(d.document_id)}
                            </option>
                          ))}
                        </select>
                      </label>
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
                        onOpen={(r) =>
                          setPreviewRow(
                            rows.find(
                              (original) => original.record_id === r.record_id,
                            ) || r,
                          )
                        }
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
                        Dates include reviewer entries used for comparisons;
                        open a record to inspect original printed values. Blank
                        values are unknown. Short record IDs are display labels;
                        full IDs are preserved in evidence and exports.
                      </p>
                    </>
                  ) : (
                    <Empty
                      title="No saved records"
                      action={
                        <button className="primary" onClick={openUpload}>
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
                        <button
                          className="secondary"
                          disabled={!scopedResults.length}
                          onClick={() => setReportOpen(true)}
                        >
                          <Printer size={17} /> Print PCI report
                        </button>
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
                      <ResultsOverview
                        results={currentRun.results}
                        scopeResults={scopedResults}
                        documentId={resultDocument}
                        contractor={contractorFilter}
                        project={projectFilter}
                        category={
                          currentTab === "differences"
                            ? "difference"
                            : resultFilter
                        }
                        onDocument={setResultDocument}
                        onContractor={setContractorFilter}
                        onProject={setProjectFilter}
                        onCategory={(outcome) => {
                          setResultFilter(outcome);
                          if (
                            currentTab === "differences" &&
                            outcome !== "difference"
                          )
                            setTab("checks");
                        }}
                      />
                      {currentTab === "differences" && (
                        <div className="differences-intro">
                          <div>
                            <span className="difference-total">
                              {differences.length.toString().padStart(2, "0")}
                            </span>
                            <div>
                              <h2>Confirmed rate differences</h2>
                              <p>
                                Out of {scopedResults.length} rates checked ·{" "}
                                {scopedCounts.needs_review} need review
                              </p>
                              <p className="csv-scope-note">
                                CSV includes the full run; the printable report
                                follows your document and contractor/project
                                filters.
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
                              search ||
                              contractorFilter ||
                              projectFilter ||
                              resultDocument
                                ? "No findings match your filters"
                                : currentTab === "differences"
                                  ? "No confirmed rate differences"
                                  : "No results in this category"
                            }
                          >
                            {currentTab === "differences" &&
                            scopedCounts.needs_review > 0
                              ? `${scopedCounts.needs_review} checks still need review. Resolve them in Labor checks to complete the comparison.`
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
                            ? "No check results"
                            : "No check results"
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
              {account ? "Private workspace" : "Local application"}
            </span>
            <span>Warren Towers</span>
          </footer>
        </main>
      </div>
      {reportOpen && currentRun && (
        <ResultsReport
          run={currentRun}
          results={scopedResults}
          filters={[
            resultDocument
              ? documents(currentRun.results).find(
                  (d) => d.id === resultDocument,
                )?.filename || "Selected document"
              : "All documents",
            contractorFilter || "All contractors",
            projectFilter || "All projects",
          ]}
          onClose={() => setReportOpen(false)}
        />
      )}
      {deleteTarget && (
        <DeleteDocumentDialog
          preview={deleteTarget.preview}
          busy={busy}
          error={error}
          onClose={() => {
            setDeleteTarget(null);
            setError("");
          }}
          onDelete={removeDocument}
        />
      )}
      {dateTarget && (
        <WorkDatesDialog
          target={dateTarget}
          busy={busy}
          error={error}
          onClose={() => {
            setDateTarget(null);
            setError("");
          }}
          onApply={applyWorkDates}
        />
      )}
      {sourceDocument && (
        <DocumentSourceDialog
          source={sourceDocument}
          onClose={() => setSourceDocument(null)}
        />
      )}
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
