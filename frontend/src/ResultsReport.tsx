import { useState } from "react";
import { createPortal } from "react-dom";
import { Printer } from "lucide-react";
import { Modal } from "./components";
import type { Finding, Run } from "./types";
import { documents, metrics, percent } from "./results";
import { money, rateTypeLabel, short } from "./presentation";

const timestamp = (date: string) =>
  new Date(date).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });

function FindingTable({
  findings,
  unresolved = false,
}: {
  findings: Finding[];
  unresolved?: boolean;
}) {
  return (
    <table className="report-findings">
      <thead>
        <tr>
          <th>Source / work period</th>
          <th>Contractor / classification</th>
          <th>Rate type</th>
          <th>Submitted</th>
          <th>Approved</th>
          <th>Difference / hour</th>
        </tr>
      </thead>
      <tbody>
        {findings.map((f) => (
          <tr key={f.finding_id}>
            <td>
              <strong>Source page {f.source_page || "Unknown"}</strong>
              <span>{f.ticket_id ? `Ticket ${f.ticket_id}` : ""}</span>
              <span>
                {f.work_start || "Work date unresolved"}
                {f.work_end && f.work_end !== f.work_start
                  ? ` → ${f.work_end}`
                  : ""}
              </span>
              <small>Record {short(f.record_id)}</small>
            </td>
            <td>
              <strong>{f.contractor || "Contractor unresolved"}</strong>
              <span>{f.classification || "Classification not printed"}</span>
              <p>{f.reason}</p>
              <small>
                Tracker rows:{" "}
                {f.reference_rows?.join(", ") ||
                  f.reference_row ||
                  "Unresolved"}{" "}
                · {f.approval_status || "Approval unresolved"}
              </small>
            </td>
            <td>{rateTypeLabel(f.rate_type)}</td>
            <td>{money(f.submitted_rate)}</td>
            <td>
              {f.approved_rate
                ? money(f.approved_rate)
                : f.approved_rates?.map(money).join(" / ") || "Unresolved"}
            </td>
            <td>
              {unresolved
                ? "Not determined"
                : f.difference_per_hour
                  ? `${Number(f.difference_per_hour) > 0 ? "+" : ""}${money(f.difference_per_hour)}`
                  : "No single approved rate"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Content({
  run,
  results,
  filters,
  includeUnresolved,
  preparedAt,
}: {
  run: Run;
  results: Finding[];
  filters: string[];
  includeUnresolved: boolean;
  preparedAt: string;
}) {
  const counts = metrics(results);
  return (
    <article className="pci-report-content">
      <header className="report-title">
        <span>WARREN TOWERS · LABOR REVIEW</span>
        <h1>PCI labor-rate review report</h1>
        <p>
          {filters.length
            ? filters.join(" · ")
            : "All documents, contractors and projects in this check run"}
        </p>
      </header>
      {run.stale && (
        <p className="report-outdated">
          <strong>OUTDATED CHECK — RERUN REQUIRED.</strong> These findings use
          an earlier reference, comparison details, classifications, or checker
          rules.
        </p>
      )}
      <dl className="report-metadata">
        <div>
          <dt>Checked</dt>
          <dd>{timestamp(run.created_at)}</dd>
        </div>
        <div>
          <dt>Report prepared</dt>
          <dd>{timestamp(preparedAt)}</dd>
        </div>
        <div>
          <dt>Reference schedule</dt>
          <dd>
            {run.reference_name} · {run.reference_version}
          </dd>
        </div>
        <div>
          <dt>Check run</dt>
          <dd>{run.id}</dd>
        </div>
      </dl>
      <div className="report-metrics">
        <div>
          <strong>{counts.total}</strong>
          <span>Rates checked</span>
        </div>
        <div>
          <strong>
            {counts.match} · {percent(counts.match, counts.total)}
          </strong>
          <span>Matching rates</span>
        </div>
        <div>
          <strong>
            {counts.difference} · {percent(counts.difference, counts.total)}
          </strong>
          <span>Rate differences</span>
        </div>
        <div>
          <strong>
            {counts.needs_review} · {percent(counts.needs_review, counts.total)}
          </strong>
          <span>Needs review</span>
        </div>
      </div>
      <p className="report-method">
        Match percentage is matching rates divided by total rates checked for
        each document, within the selected contractor/project scope.{" "}
        {results.some((r) => r.rate_type !== "REG")
          ? "This saved run counts each regular, overtime and double-time rate separately."
          : "Only regular/ST rates are counted; overtime and double-time are excluded."}{" "}
        Unresolved checks remain in the denominator and are not confirmed
        differences. Only saved comparisons in this run are counted; unsaved
        rows and extraction failures are outside this report.
      </p>
      {documents(results).map((d) => (
        <section key={d.id} className="report-document">
          <header>
            <span>PCI / SOURCE DOCUMENT</span>
            <h2>{d.filename}</h2>
            <p>
              <strong>PCI reference:</strong>{" "}
              {d.references.join(", ") || "Not provided"} ·{" "}
              <strong>Project:</strong>{" "}
              {d.projects.join(", ") || "Not provided"}
            </p>
            <p className="report-document-id">Document identity: {d.id}</p>
            <p>
              {d.counts.total} rates checked · {d.counts.match} matched (
              {percent(d.counts.match, d.counts.total)}) · {d.counts.difference}{" "}
              differences · {d.counts.needs_review} need review
            </p>
          </header>
          <h3>Confirmed rate differences ({d.counts.difference})</h3>
          {d.counts.difference ? (
            <FindingTable
              findings={d.findings.filter((f) => f.outcome === "difference")}
            />
          ) : (
            <p>No confirmed rate differences in this document and scope.</p>
          )}
          {includeUnresolved && (
            <>
              <h3>Items needing review ({d.counts.needs_review})</h3>
              {d.counts.needs_review ? (
                <FindingTable
                  findings={d.findings.filter(
                    (f) => f.outcome === "needs_review",
                  )}
                  unresolved
                />
              ) : (
                <p>No unresolved checks in this document and scope.</p>
              )}
            </>
          )}
        </section>
      ))}
      {!includeUnresolved && counts.needs_review > 0 && (
        <p className="report-outdated">
          Unresolved item details were excluded from this printout.{" "}
          {counts.needs_review} checks still need review.
        </p>
      )}
      <footer>
        This report identifies submitted labor-rate differences and unresolved
        checks. It does not approve or reject the PCI or calculate total
        financial impact. Original printed submissions are compared; later
        corrections require separate confirmation.
      </footer>
    </article>
  );
}

export default function ResultsReport({
  run,
  results,
  filters,
  onClose,
}: {
  run: Run;
  results: Finding[];
  filters: string[];
  onClose: () => void;
}) {
  const [includeUnresolved, setIncludeUnresolved] = useState(true);
  const [preparedAt] = useState(() => new Date().toISOString());
  const content = (
    <Content
      run={run}
      results={results}
      filters={filters}
      includeUnresolved={includeUnresolved}
      preparedAt={preparedAt}
    />
  );
  return (
    <>
      <Modal
        title="Print PCI report"
        wide
        className="pci-report-dialog"
        onClose={onClose}
      >
        <div className="report-controls">
          <div>
            <p>
              Print the selected documents and contractor/project scope, or
              choose Save as PDF in your browser.
            </p>
            <label>
              <input
                type="checkbox"
                checked={includeUnresolved}
                onChange={(e) => setIncludeUnresolved(e.target.checked)}
              />{" "}
              Include items needing review
            </label>
          </div>
          <button className="primary" onClick={() => window.print()}>
            <Printer size={17} /> Print / Save PDF
          </button>
        </div>
        {content}
      </Modal>
      {createPortal(<div id="pci-print-root">{content}</div>, document.body)}
    </>
  );
}
