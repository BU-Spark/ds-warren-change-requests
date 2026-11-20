import { useState } from "react";
import { Modal } from "./components";
import type { Row } from "./types";

export type WorkDatesTarget = {
  route: string;
  filename: string;
  records: Row[];
  details: Record<string, Row>;
  selected: string[];
  page: number;
  scope: "document" | "page" | "rows";
  revision?: number;
};
export type WorkDatesUpdate = {
  scope: "document" | "page" | "rows";
  work_start: string;
  work_end: string;
  page: number;
  record_ids: string[];
  revision?: number;
  only_missing: boolean;
  clear: boolean;
};
export function WorkPeriodFields({
  start,
  end,
  onStart,
  onEnd,
  required = false,
}: {
  start: string;
  end: string;
  onStart: (value: string) => void;
  onEnd: (value: string) => void;
  required?: boolean;
}) {
  return (
    <div className="form-grid">
      <label>
        Work start
        <input
          type="date"
          value={start}
          onChange={(e) => onStart(e.target.value)}
          required={required || Boolean(end)}
          max={end || undefined}
        />
      </label>
      <label>
        Work finish
        <input
          type="date"
          value={end}
          onChange={(e) => onEnd(e.target.value)}
          required={required || Boolean(start)}
          min={start || undefined}
        />
      </label>
    </div>
  );
}

export default function WorkDatesDialog({
  target,
  busy,
  error,
  onClose,
  onApply,
}: {
  target: WorkDatesTarget;
  busy: boolean;
  error: string;
  onClose: () => void;
  onApply: (body: WorkDatesUpdate) => void;
}) {
  const [scope, setScope] = useState(target.scope);
  const [page, setPage] = useState(target.page);
  const single =
    target.scope === "rows" && target.selected.length === 1
      ? target.records.find((r) => r.record_id === target.selected[0])
      : undefined;
  const supplied = single ? target.details[single.record_id] || {} : {};
  const [start, setStart] = useState(
    supplied.work_start || single?.work_start || "",
  );
  const [end, setEnd] = useState(
    supplied.work_end ||
      single?.work_end ||
      supplied.work_start ||
      single?.work_start ||
      "",
  );
  const [onlyMissing, setOnlyMissing] = useState(!single);
  const pages = [
    ...new Set(target.records.map((r) => Number(r.source_page))),
  ].sort((a, b) => a - b);
  const scoped = target.records.filter(
    (r) =>
      scope === "document" ||
      (scope === "page"
        ? Number(r.source_page) === page
        : target.selected.includes(r.record_id)),
  );
  const missing = scoped.filter(
    (r) => !(target.details[r.record_id]?.work_start || r.work_start),
  );
  const entered = scoped.filter(
    (r) =>
      target.details[r.record_id]?.work_start ||
      target.details[r.record_id]?.work_end,
  );
  const body = (clear: boolean): WorkDatesUpdate => ({
    scope,
    page,
    work_start: start,
    work_end: end,
    record_ids: target.selected,
    revision: target.revision,
    only_missing: onlyMissing,
    clear,
  });
  return (
    <Modal
      title="Set work dates"
      className="work-dates-modal"
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <form
        className="work-dates-form"
        onSubmit={(e) => {
          e.preventDefault();
          onApply(body(false));
        }}
      >
        <div className="modal-body work-dates-content">
          <p>
            <strong>{target.filename}</strong>
          </p>
          <p>
            Use the dates when the work occurred. Enter the same date twice for
            one day. You can skip this and resolve dates later.
          </p>
          <label>
            Apply dates to
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as typeof scope)}
              disabled={busy}
            >
              <option value="document">Entire document</option>
              <option value="page">One page</option>
              <option value="rows" disabled={!target.selected.length}>
                Selected rows ({target.selected.length})
              </option>
            </select>
          </label>
          {scope === "page" && (
            <label>
              Source page
              <select
                value={page}
                onChange={(e) => setPage(Number(e.target.value))}
              >
                {pages.map((p) => (
                  <option key={p} value={p}>
                    Page {p}
                  </option>
                ))}
              </select>
            </label>
          )}
          <WorkPeriodFields
            start={start}
            end={end}
            onStart={setStart}
            onEnd={setEnd}
            required
          />
          <label className="technical">
            <input
              type="checkbox"
              checked={onlyMissing}
              onChange={(e) => setOnlyMissing(e.target.checked)}
            />
            Only fill rows missing work dates
          </label>
          <p role="status">
            {onlyMissing ? missing.length : scoped.length} of {scoped.length}{" "}
            rows will receive this range.
            {!onlyMissing &&
              " Existing work dates in this scope will be replaced for comparisons."}
          </p>
          <p className="table-note">
            Printed values stay unchanged. Entered dates are used for rate
            checks; existing check results must be rerun. Removing entered dates
            restores printed dates, or leaves the dates unresolved.
          </p>
          {error && (
            <p className="message error" role="alert">
              {error}
            </p>
          )}
        </div>
        <div className="modal-actions work-date-actions">
          <button
            type="button"
            className="text-button"
            disabled={busy || !entered.length}
            onClick={() => onApply(body(true))}
          >
            Remove entered dates ({entered.length})
          </button>
          <button
            type="button"
            className="secondary"
            disabled={busy}
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            className="primary"
            type="submit"
            disabled={
              busy || !scoped.length || (onlyMissing && !missing.length)
            }
          >
            {busy ? "Saving…" : "Apply work dates"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
