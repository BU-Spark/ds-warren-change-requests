import { AlertCircle, ArrowDownToLine, Check } from "lucide-react";
import { Modal } from "./components";
import { display, money, short } from "./presentation";
import type { Reference } from "./types";

type Props = {
  reference: Reference | null;
  preview: Reference | null;
  busy: boolean;
  error: string;
  onPreview: (file: File) => void;
  onActivate: () => void;
  onDiscard: () => void;
  onClose: () => void;
};
export default function ReferenceDialog({
  reference,
  preview,
  busy,
  error,
  onPreview,
  onActivate,
  onDiscard,
  onClose,
}: Props) {
  return (
    <Modal title="Reference rate schedule" onClose={onClose} wide>
      <div className="modal-body">
        <p>
          Use the cleaned rate tracker CSV. Uploading previews a new version; it
          becomes active only when you confirm.
        </p>
        {reference && (
          <div className="notice">
            <strong>Active: {reference.name}</strong>
            <a
              className="text-button reference-download"
              href={`/api/reference/${reference.id}/source`}
              download
            >
              Download original CSV <ArrowDownToLine size={14} />
            </a>
            <br />
            {reference.rows.length} schedules · {reference.issues.length} rows
            with reference issues · Version {short(reference.id)}
          </div>
        )}
        <label className="file-label">
          Upload replacement schedule
          <input
            aria-label="Upload reference CSV"
            type="file"
            accept=".csv"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) onPreview(file);
            }}
          />
        </label>
        {error && (
          <div className="message error" role="alert">
            <AlertCircle size={17} />
            {error}
          </div>
        )}
        {(preview || reference) && (
          <>
            <h3>{preview ? "Preview: " + preview.name : "Current schedule"}</h3>
            <p>
              {(preview || reference)!.rows.length} schedules.{" "}
              {(preview || reference)!.issues.length} incomplete or invalid rows
              cannot qualify for a successful check.
            </p>
            <div className="table-scroll reference-table">
              <table>
                <thead>
                  <tr>
                    <th>Row</th>
                    <th>Contractor</th>
                    <th>Classification</th>
                    <th>Effective period</th>
                    <th>REG</th>
                    <th>Status / issues</th>
                  </tr>
                </thead>
                <tbody>
                  {(preview || reference)!.rows.map((r) => (
                    <tr key={r.source_csv_row_number}>
                      <td>{r.source_csv_row_number}</td>
                      <td>{display(r.subcontractor)}</td>
                      <td>{display(r.position)}</td>
                      <td>
                        {r.effective_time_period_start || "Unknown"} →{" "}
                        {r.effective_time_period_finish || "Unknown"}
                      </td>
                      <td>{money(r.reg_rate)}</td>
                      <td>
                        {r.status || "No status"}
                        {r.issues.map((i) => (
                          <small className="issue-text" key={i}>
                            {i}
                          </small>
                        ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {preview && (
          <div className="modal-actions">
            <button className="secondary" onClick={onDiscard}>
              Discard preview
            </button>
            <button className="primary" disabled={busy} onClick={onActivate}>
              Activate this schedule
              <Check size={17} />
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}
