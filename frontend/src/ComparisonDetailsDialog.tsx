import { AlertCircle, Check, Info, LoaderCircle } from "lucide-react";
import { Modal } from "./components";
import type { Row } from "./types";

type Props = {
  recordIds: string[];
  records: Row[];
  edit: Row;
  busy: boolean;
  error: string;
  onChange: (value: Row) => void;
  onSave: () => void;
  onClose: () => void;
};
export default function ComparisonDetailsDialog({
  recordIds,
  records,
  edit,
  busy,
  error,
  onChange,
  onSave,
  onClose,
}: Props) {
  return (
    <Modal
      title={
        recordIds.length === 1
          ? "Comparison details"
          : `Comparison details · ${recordIds.length} records`
      }
      onClose={onClose}
    >
      <form
        className="modal-body"
        onSubmit={(e) => {
          e.preventDefault();
          onSave();
        }}
      >
        {error && (
          <div className="message error" role="alert">
            <AlertCircle size={17} />
            {error}
          </div>
        )}
        <p>
          These details help choose the right schedule. Original printed values
          remain unchanged.{" "}
          {recordIds.length > 1
            ? "Only filled fields are applied to the selected records."
            : "Leave fields blank to use the original printed values."}
        </p>
        <div className="form-grid">
          <label>
            Contractor
            <input
              list="contractor-names"
              value={edit.contractor || ""}
              onChange={(e) =>
                onChange({ ...edit, contractor: e.target.value })
              }
              placeholder={
                recordIds.length === 1
                  ? records.find((r) => r.record_id === recordIds[0])
                      ?.contractor || "Choose reference contractor"
                  : "Choose reference contractor"
              }
            />
          </label>
          <label>
            Classification
            <input
              list="classification-names"
              value={edit.classification || ""}
              onChange={(e) =>
                onChange({ ...edit, classification: e.target.value })
              }
              placeholder={
                recordIds.length === 1
                  ? records.find((r) => r.record_id === recordIds[0])
                      ?.position_original || "Choose classification"
                  : "Choose reference classification"
              }
            />
          </label>
          <label>
            Work start
            <input
              type="date"
              value={edit.work_start || ""}
              onChange={(e) =>
                onChange({ ...edit, work_start: e.target.value })
              }
            />
          </label>
          <label>
            Work finish
            <input
              type="date"
              value={edit.work_end || ""}
              onChange={(e) => onChange({ ...edit, work_end: e.target.value })}
            />
          </label>
        </div>
        <div className="notice">
          <Info size={17} />
          Confirm that the selected reference classification describes the work.
          Trade relationships preserve stated grades and apply only within the
          selected contractor.
        </div>
        <div className="modal-actions">
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="primary" disabled={busy}>
            {busy ? (
              <LoaderCircle className="spin" size={16} />
            ) : (
              <Check size={16} />
            )}
            Save comparison details
          </button>
        </div>
      </form>
    </Modal>
  );
}
