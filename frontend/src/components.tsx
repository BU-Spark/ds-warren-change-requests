import { useEffect, useRef, useState, useId, type ReactNode } from "react";
import { ArrowUpRight, FileSearch, X } from "lucide-react";
import type { Row, Table } from "./types";
import { labels, money, display, short } from "./presentation";

export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`pill ${tone}`}>{children}</span>;
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <FileSearch size={28} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
  className = "",
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const headingId = useId();
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby={headingId}
      onCancel={onClose}
      className={`${wide ? "modal wide" : "modal"} ${className}`.trim()}
    >
      <header>
        <div>
          <h2 id={headingId}>{title}</h2>
        </div>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Close dialog"
        >
          <X />
        </button>
      </header>
      {children}
    </dialog>
  );
}
export function Source({ url }: { url: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [url]);
  return (
    <div className="source-frame">
      {failed ? (
        <p className="notice">
          The source page is unavailable. Reupload the original document to
          restore access.
        </p>
      ) : (
        <img
          src={url}
          alt="Original printed source page"
          onError={() => setFailed(true)}
        />
      )}
      <p className="fine-print">
        PDF annotations are hidden. Flattened marks may still be visible;
        compare against the original printed values.
      </p>
    </div>
  );
}
export function RowsTable({
  rows,
  selected,
  onSelect,
  onOpen,
  technical = false,
  knownIds = [],
}: {
  rows: Row[];
  selected?: Set<string>;
  onSelect?: (ids: Set<string>) => void;
  onOpen?: (row: Row) => void;
  technical?: boolean;
  knownIds?: string[];
}) {
  const base = [
    "record_id",
    "project",
    "project_id",
    "contractor",
    "position_original",
    "worker_name",
    "description",
    "work_start",
    "work_end",
    "reg_hours",
    "ot_hours",
    "dt_hours",
    "hours",
    "reg_rate",
    "ot_rate",
    "dt_rate",
    "document_reference",
    "ticket_id",
    "source_file",
    "source_page",
  ];
  const ids = [...new Set([...knownIds, ...rows.map((r) => r.record_id)])];
  const displayId = (id: string) => {
    let n = 12;
    while (
      n < id.length &&
      ids.some((other) => other !== id && other.slice(0, n) === id.slice(0, n))
    )
      n++;
    return id.slice(0, n);
  };
  const fields = technical
    ? Object.keys(rows[0] || {}).filter((field) => field !== "rate_basis_raw")
    : base.filter(
        (f) =>
          [
            "record_id",
            "contractor",
            "position_original",
            "source_page",
          ].includes(f) ||
          f === "project_id" ||
          rows.some((r) => r[f] || (f === "reg_rate" && r.rate)),
      );
  function toggleAll() {
    const next = new Set(selected);
    const all = rows.every((r) => next.has(r.record_id));
    rows.forEach((r) =>
      all ? next.delete(r.record_id) : next.add(r.record_id),
    );
    onSelect?.(next);
  }
  return (
    <div
      className="table-scroll"
      tabIndex={0}
      role="region"
      aria-label="Labor records table"
    >
      <table>
        <thead>
          <tr>
            {onSelect && (
              <th>
                <input
                  type="checkbox"
                  aria-label="Select all visible records"
                  checked={
                    rows.length > 0 &&
                    rows.every((r) => selected?.has(r.record_id))
                  }
                  onChange={toggleAll}
                />
              </th>
            )}
            {fields.map((f) => (
              <th key={f}>{labels[f] || f.replaceAll("_", " ")}</th>
            ))}
            {onOpen && (
              <th>
                <span className="sr-only">Review</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.record_id}>
              {onSelect && (
                <td>
                  <input
                    type="checkbox"
                    aria-label={`Select record ${short(r.record_id)}`}
                    checked={selected?.has(r.record_id) || false}
                    onChange={() => {
                      const next = new Set(selected);
                      next.has(r.record_id)
                        ? next.delete(r.record_id)
                        : next.add(r.record_id);
                      onSelect(new Set(next));
                    }}
                  />
                </td>
              )}
              {fields.map((f) => (
                <td
                  key={f}
                  title={r[f] || ""}
                  className={
                    f.includes("rate")
                      ? "numeric"
                      : f === "record_id"
                        ? "mono"
                        : ""
                  }
                >
                  {f === "record_id" && !technical
                    ? displayId(r[f])
                    : f === "project_id"
                      ? (r.source_file || "")
                          .replace(/\.[^.]+$/, "")
                          .split("-")[0]
                          .trim()
                      : f.includes("rate")
                        ? money(
                            !technical && f === "reg_rate"
                              ? r.reg_rate || r.rate
                              : r[f],
                          )
                        : display(r[f])}
                </td>
              ))}
              {onOpen && (
                <td>
                  <button className="text-button" onClick={() => onOpen(r)}>
                    Review <ArrowUpRight size={14} />
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
const mappingChoices = [
  "description",
  "position_original",
  "worker_name",
  "hours",
  "reg_hours",
  "ot_hours",
  "dt_hours",
  "reg_rate",
  "ot_rate",
  "dt_rate",
  "work_start",
  "work_end",
  "ticket_id",
  "document_reference",
];
export function Mapping({
  table,
  onApply,
  disabled,
}: {
  table: Table;
  onApply: (columns: Record<number, string>) => void;
  disabled: boolean;
}) {
  const [columns, setColumns] = useState<Record<number, string>>({});
  return (
    <div className="mapping">
      <p>
        Match each printed column to the information it contains. Ignore
        handwriting and corrections.
      </p>
      <div className="form-grid">
        {table.headers.map((h, i) => (
          <label key={i}>
            {h || `Column ${i + 1}`}
            <select
              value={columns[i] || ""}
              onChange={(e) => setColumns({ ...columns, [i]: e.target.value })}
            >
              <option value="">Ignore column</option>
              {mappingChoices.map((f) => (
                <option key={f} value={f}>
                  {labels[f] || f.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <button
        className="secondary"
        disabled={disabled}
        onClick={() =>
          onApply(
            Object.fromEntries(Object.entries(columns).filter(([, v]) => v)),
          )
        }
      >
        Apply column mapping
      </button>
    </div>
  );
}
