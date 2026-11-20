import { AlertCircle, Trash2 } from "lucide-react";
import { Modal } from "./components";
import type { DeletionPreview } from "./types";

export default function DeleteDocumentDialog({
  preview,
  busy,
  error,
  onClose,
  onDelete,
}: {
  preview: DeletionPreview;
  busy: boolean;
  error: string;
  onClose: () => void;
  onDelete: () => void;
}) {
  return (
    <Modal
      title="Delete document?"
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <div className="modal-body">
        <h3>{preview.filename}</h3>
        <p>
          This permanently removes this document from the shared workspace. You
          can upload the original file again to start over.
        </p>
        <ul className="delete-impact">
          <li>{preview.saved_rows} saved rows and their comparison details</li>
          <li>{preview.uploads} upload/review sessions for this exact file</li>
          <li>Saved source copies and extraction evidence</li>
          <li>
            {preview.check_runs} check-history runs containing this document
          </li>
        </ul>
        {preview.shared_runs > 0 && (
          <p className="notice">
            {preview.shared_runs} affected check runs also include other
            documents. Those historical runs will be removed too; the other
            documents and their saved rows stay available to check again.
          </p>
        )}
        <p>
          Your approved reference schedule and other source documents are kept.
        </p>
        {error && (
          <div role="alert" className="message error">
            <AlertCircle size={18} />
            {error}
          </div>
        )}
        <div className="modal-actions">
          <button className="secondary" disabled={busy} onClick={onClose}>
            Cancel
          </button>
          <button className="primary danger" disabled={busy} onClick={onDelete}>
            <Trash2 size={16} />
            {busy ? "Deleting…" : "Delete permanently"}
          </button>
        </div>
      </div>
    </Modal>
  );
}
