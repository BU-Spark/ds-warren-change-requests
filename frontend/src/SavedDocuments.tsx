import { useState } from "react";
import { FileText, Search, Trash2 } from "lucide-react";
import { Empty, Pill } from "./components";
import { formatDate, short } from "./presentation";
import type { SavedDocument } from "./types";

export default function SavedDocuments({
  documents,
  busy,
  canCheck,
  focused,
  onRates,
  onSource,
  onReview,
  onCheck,
  onDelete,
  onUpload,
}: {
  documents: SavedDocument[];
  busy: boolean;
  canCheck: boolean;
  focused: string;
  onRates: (id: string) => void;
  onSource: (doc: SavedDocument) => void;
  onReview: (id: string) => void;
  onCheck: (ids: string[]) => void;
  onDelete: (id: string) => void;
  onUpload: () => void;
}) {
  const [search, setSearch] = useState("");
  const visible = documents.filter((d) =>
    `${d.filename} ${d.projects.join(" ")} ${d.contractors.join(" ")}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <section
      className="card saved-documents"
      aria-label="Saved document library"
    >
      <div className="card-heading">
        <div>
          <h2>
            Saved document library <Pill>{documents.length}</Pill>
          </h2>
          <p>
            Saved files and their accepted rates. Fully saved documents leave
            the review queue; partially saved documents can still be reviewed.
          </p>
        </div>
      </div>
      <div className="filter-bar">
        <div className="search">
          <Search size={17} />
          <input
            aria-label="Search saved documents"
            placeholder="Search documents, projects or contractors…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>
      <div className="saved-document-list">
        {visible.map((doc) => (
          <article
            key={doc.document_id}
            className={`saved-document ${doc.document_id === focused ? "focused" : ""}`}
          >
            <div className="saved-document-title">
              <FileText size={24} />
              <div>
                <h3>{doc.filename}</h3>
                <p>
                  {doc.projects.join(", ") || "Project not provided"} ·{" "}
                  {doc.contractors.join(", ") ||
                    "Contractor comparison details needed"}
                </p>
                <small>
                  Document {short(doc.document_id)}
                  {doc.uploaded_at
                    ? ` · Uploaded ${formatDate(doc.uploaded_at)}`
                    : ""}
                </small>
              </div>
              <Pill tone={doc.status === "saved" ? "good" : "warn"}>
                {doc.status === "saved" ? "Saved" : "Partially saved"}
              </Pill>
            </div>
            <p className="saved-document-count">
              {doc.saved_rows} saved rows
              {doc.unsaved_rows
                ? ` · ${doc.unsaved_rows} extracted rows still to save`
                : ""}
            </p>
            <div className="saved-document-actions">
              <button
                className="secondary"
                disabled={busy}
                onClick={() => onRates(doc.document_id)}
              >
                View saved rates
              </button>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => onSource(doc)}
              >
                View source
              </button>
              {doc.status !== "saved" && doc.session_id && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() => onReview(doc.session_id!)}
                >
                  Continue review
                </button>
              )}
              <button
                className="primary"
                disabled={busy || !canCheck}
                onClick={() => onCheck(doc.record_ids)}
              >
                {doc.document_id === focused
                  ? "Check saved document"
                  : "Check rates"}
              </button>
              <button
                className="text-button delete-document"
                disabled={busy}
                onClick={() => onDelete(doc.document_id)}
              >
                <Trash2 size={15} /> Delete document
              </button>
            </div>
          </article>
        ))}
      </div>
      {!visible.length && (
        <Empty
          title={
            search ? "No documents match your search" : "No saved documents yet"
          }
          action={
            !search && (
              <button className="primary" onClick={onUpload}>
                Upload document
              </button>
            )
          }
        >
          {search
            ? "Try another filename, project or contractor."
            : "Review an upload and save its rates to add it to this library."}
        </Empty>
      )}
    </section>
  );
}
