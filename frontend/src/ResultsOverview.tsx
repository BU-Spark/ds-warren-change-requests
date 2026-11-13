import { CheckCircle2, CircleHelp, SlidersHorizontal } from "lucide-react";
import type { Finding } from "./types";
import { documents, metrics, percent, type Outcome } from "./results";
import { short } from "./presentation";

type Props = {
  results: Finding[];
  scopeResults: Finding[];
  documentId: string;
  contractor: string;
  project: string;
  category: string;
  onDocument: (id: string) => void;
  onContractor: (value: string) => void;
  onProject: (value: string) => void;
  onCategory: (value: Outcome) => void;
};

export default function ResultsOverview(props: Props) {
  const allDocuments = documents(props.results);
  const filtered = props.results.filter(
    (r) =>
      (!props.contractor || r.contractor === props.contractor) &&
      (!props.project || r.project === props.project),
  );
  const byDocument = documents(filtered);
  const counts = metrics(props.scopeResults);
  return (
    <section className="results-overview" aria-label="Results summary">
      <div className="summary-heading">
        <div>
          <span className="eyebrow">PCI REVIEW SUMMARY</span>
          <h2>Results at a glance</h2>
        </div>
        <span>
          <strong>{counts.total}</strong> rate comparisons ·{" "}
          {documents(props.scopeResults).length} documents
        </span>
      </div>
      <div className="result-scope">
        <label>
          Document
          <select
            aria-label="Filter check document"
            value={props.documentId}
            onChange={(e) => props.onDocument(e.target.value)}
          >
            <option value="">All documents</option>
            {allDocuments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.filename} · {short(d.id)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Contractor
          <select
            aria-label="Filter contractor"
            value={props.contractor}
            onChange={(e) => props.onContractor(e.target.value)}
          >
            <option value="">All contractors</option>
            {[
              ...new Set(
                props.results.map((r) => r.contractor).filter(Boolean),
              ),
            ]
              .sort()
              .map((c) => (
                <option key={c}>{c}</option>
              ))}
          </select>
        </label>
        <label>
          Project
          <select
            aria-label="Filter project"
            value={props.project}
            onChange={(e) => props.onProject(e.target.value)}
          >
            <option value="">All projects</option>
            {[...new Set(props.results.map((r) => r.project).filter(Boolean))]
              .sort()
              .map((c) => (
                <option key={c}>{c}</option>
              ))}
          </select>
        </label>
      </div>
      <div className="stats-grid">
        {(
          [
            {
              id: "match",
              title: "Matching rates",
              icon: CheckCircle2,
              tone: "good",
            },
            {
              id: "difference",
              title: "Rate differences",
              icon: SlidersHorizontal,
              tone: "bad",
            },
            {
              id: "needs_review",
              title: "Needs review",
              icon: CircleHelp,
              tone: "warn",
            },
          ] as const
        ).map(({ id, title, icon: Icon, tone }) => (
          <button
            key={id}
            className={`stat-card ${props.category === id ? "selected" : ""}`}
            onClick={() => props.onCategory(id)}
            aria-pressed={props.category === id}
          >
            <span className={`stat-icon ${tone}`}>
              <Icon size={21} />
            </span>
            <span className="stat-number">{counts[id]}</span>
            <strong>{title}</strong>
            <small>
              <b>{percent(counts[id], counts.total)}</b> · {counts[id]} /{" "}
              {counts.total} checked
            </small>
          </button>
        ))}
      </div>
      <p className="metrics-note">
        Match percentage = matching rates ÷ total rates checked. Each regular,
        overtime, or double-time rate is one comparison; unresolved checks stay
        in the total. Document, contractor, and project filters apply to metrics
        and reports. Search filters the findings list only.
      </p>
      <div className="document-breakdown">
        <div className="document-breakdown-heading">
          <h3>Results by document</h3>
          {props.documentId && (
            <button
              className="text-button"
              onClick={() => props.onDocument("")}
            >
              Show all documents
            </button>
          )}
        </div>
        <div className="document-results-header" aria-hidden="true">
          <span>Document / PCI</span>
          <span>Checked</span>
          <span>Matched</span>
          <span>Differences</span>
          <span>Needs review</span>
        </div>
        <div
          className="document-results-list"
          role="list"
          aria-label="Document results"
        >
          {byDocument.map((d) => (
            <div role="listitem" key={d.id}>
              <button
                className={`document-result ${props.documentId === d.id ? "selected" : ""}`}
                onClick={() => props.onDocument(d.id)}
                aria-pressed={props.documentId === d.id}
                aria-label={`${d.filename}, ${d.counts.difference} differences, ${d.counts.needs_review} need review. Show this document`}
              >
                <span>
                  <strong>{d.filename}</strong>
                  <small>
                    {d.references.join(", ") || "PCI reference not provided"} ·{" "}
                    {short(d.id)}
                  </small>
                </span>
                <span>
                  <small>Checked</small>
                  {d.counts.total}
                </span>
                <span>
                  <small>Matched</small>
                  {d.counts.match} / {d.counts.total}{" "}
                  <b>{percent(d.counts.match, d.counts.total)}</b>
                </span>
                <span>
                  <small>Differences</small>
                  {d.counts.difference}
                </span>
                <span>
                  <small>Needs review</small>
                  {d.counts.needs_review}
                </span>
              </button>
            </div>
          ))}
          {!byDocument.length && (
            <p>No comparisons match the selected contractor and project.</p>
          )}
        </div>
      </div>
    </section>
  );
}
