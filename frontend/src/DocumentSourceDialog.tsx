import { useState } from "react";
import { Modal, Source } from "./components";

export default function DocumentSourceDialog({
  source,
  onClose,
}: {
  source: { document_id: string; filename: string; page_count: number };
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  return (
    <Modal title={source.filename} wide onClose={onClose}>
      <div className="modal-body">
        <div className="document-source-pages">
          <button
            className="secondary"
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
          >
            Previous page
          </button>
          <span>
            Source page {page} of {source.page_count}
          </span>
          <button
            className="secondary"
            disabled={page >= source.page_count}
            onClick={() => setPage(page + 1)}
          >
            Next page
          </button>
        </div>
        <Source url={`/api/documents/${source.document_id}/pages/${page}`} />
      </div>
    </Modal>
  );
}
