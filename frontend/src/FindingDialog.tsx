import { Settings2 } from "lucide-react";
import { Modal, Pill, Source } from "./components";
import { labels, money, rateTypeLabel, short } from "./presentation";
import type { Finding, Row } from "./types";

type Props = {
  finding: Finding | null;
  previewRow: Row | null;
  records: Row[];
  rulesChanged?: boolean;
  onClose: () => void;
  onEdit: (ids: string[]) => void;
};
export default function FindingDialog({
  finding,
  previewRow,
  records,
  rulesChanged,
  onClose,
  onEdit,
}: Props) {
  if (!finding && !previewRow) return null;
  return (
    <Modal
      title={finding ? "Labor rate finding" : "Saved labor record"}
      onClose={onClose}
      wide
    >
      <div className="modal-body">
        <div className="finding-summary">
          <div>
            <span className="eyebrow">
              {finding ? "COMPARISON RESULT" : "SOURCE RECORD"}
            </span>
            <h3>
              {finding?.contractor ||
                previewRow?.contractor ||
                "Contractor needed"}
            </h3>
            <p>
              {finding?.classification ||
                previewRow?.position_original ||
                "Checked by contractor and rate"}
            </p>
          </div>
          {finding && (
            <Pill
              tone={
                finding.outcome === "difference"
                  ? "bad"
                  : finding.outcome === "match"
                    ? "good"
                    : "warn"
              }
            >
              {finding.outcome === "needs_review"
                ? "Needs review"
                : finding.outcome === "match"
                  ? "Rate matches"
                  : "Rate difference"}
            </Pill>
          )}
        </div>
        {finding && (
          <>
            <p className="notice">
              {rulesChanged
                ? "Rerun this check to apply the current matching rules."
                : finding.reason}
            </p>
            {finding.match_explanation && (
              <div className="notice">
                <strong>How schedules were selected</strong>
                <p>{finding.match_explanation}</p>
              </div>
            )}
            <div className="finding-values">
              <div>
                <small>Submitted {rateTypeLabel(finding.rate_type)}</small>
                <strong>{money(finding.submitted_rate)}</strong>
              </div>
              <div>
                <small>Approved rate</small>
                <strong>
                  {finding.approved_rate
                    ? money(finding.approved_rate)
                    : finding.approved_rates?.map(money).join(" / ") || "—"}
                </strong>
              </div>
              <div>
                <small>Difference / hour</small>
                <strong>{money(finding.difference_per_hour)}</strong>
              </div>
            </div>
            <p>
              <strong>Work period:</strong> {finding.work_start || "Unknown"} →{" "}
              {finding.work_end || "Unknown"}
            </p>
            <p>
              <strong>Reference:</strong> {short(finding.reference_version)} ·
              Tracker row{" "}
              {finding.reference_rows?.join(", ") ||
                finding.reference_row ||
                "Unresolved"}{" "}
              · {finding.approval_status || "Approval unresolved"}
            </p>
            {finding.candidates.length > 0 && (
              <details>
                <summary>
                  Reference schedule evidence ({finding.candidates.length})
                </summary>
                <div className="candidate-list">
                  {finding.candidates.map((c) => (
                    <div className="notice" key={c.source_csv_row_number}>
                      <strong>
                        Tracker row {c.source_csv_row_number} ·{" "}
                        {c.status || "No approval status"}
                      </strong>
                      <p>
                        {c.subcontractor} · {c.position}
                        <br />
                        {c.effective_time_period_start || "Unknown"} →{" "}
                        {c.effective_time_period_finish || "Unknown"}
                        <br />
                        REG {money(c.reg_rate)} / OT {money(c.ot_rate)} / DT{" "}
                        {money(c.dt_rate)}
                        <br />
                        BU approval received:{" "}
                        {c.bu_approval_received || "Unknown"}
                      </p>
                      {c.issues.join(" · ")}
                    </div>
                  ))}
                </div>
              </details>
            )}
            {Object.values(finding.review_details).some(Boolean) && (
              <p className="notice">
                Reviewer-supplied details were used for this check:{" "}
                {Object.entries(finding.review_details)
                  .filter(([key, value]) => key !== "rate_basis_raw" && value)
                  .map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`)
                  .join(" · ")}
              </p>
            )}
          </>
        )}
        {previewRow && (
          <dl className="record-details">
            {Object.entries(previewRow)
              .filter(([key, value]) => key !== "rate_basis_raw" && value)
              .map(([k, v]) => (
                <div key={k}>
                  <dt>{labels[k] || k.replaceAll("_", " ")}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
          </dl>
        )}
        <p className="fine-print">
          {(finding || previewRow)!.source_file} · Page{" "}
          {(finding || previewRow)!.source_page} · Full record ID:{" "}
          {(finding || previewRow)!.record_id}
        </p>
        <Source
          url={`/api/documents/${(finding || previewRow)!.document_id}/pages/${(finding || previewRow)!.source_page}`}
        />
        <div className="modal-actions">
          {!(finding || previewRow)!.contractor && (
            <button
              className="secondary"
              onClick={() =>
                onEdit(
                  records
                    .filter(
                      (r) =>
                        r.document_id === (finding || previewRow)!.document_id,
                    )
                    .map((r) => r.record_id),
                )
              }
            >
              Set contractor for this document
            </button>
          )}
          <button
            className="primary"
            onClick={() => onEdit([(finding || previewRow)!.record_id])}
          >
            Set comparison details
            <Settings2 size={16} />
          </button>
        </div>
      </div>
    </Modal>
  );
}
