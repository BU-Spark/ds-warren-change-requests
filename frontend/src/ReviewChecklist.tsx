import { ArrowRight, CheckCircle2, CircleHelp } from "lucide-react";
import { Pill } from "./components";
import type { ReviewSummary, ReviewItem } from "./types";
export const needsAttention = (status?: string) =>
  ["needs_review", "check_pages", "failed", "no_rates"].includes(status || "");
export const reviewLabel = (summary?: ReviewSummary) => {
  if (!summary) return "Processing";
  if (summary.pending_tables)
    return `${summary.pending_tables} ${summary.pending_tables === 1 ? "table needs" : "tables need"} review`;
  return (
    (
      {
        ready_to_save: "Ready to save",
        saved: "Saved",
        no_rates: "No rates found",
        check_pages: "Check skipped pages",
        failed: "Could not process",
        queued: "Queued",
        processing: "Processing",
      } as Record<string, string>
    )[summary.status] || "Ready to review"
  );
};
export default function ReviewChecklist({
  summary,
  page,
  onJump,
  onPage,
  tableId,
}: {
  summary: ReviewSummary;
  tableId?: string;
  page: number;
  onJump: (item: ReviewItem) => void;
  onPage: (page: number) => void;
}) {
  const pending = summary.items.filter(
    (i) => i.status === "mapping" || i.status === "needs_review",
  );
  const activeId =
    tableId ||
    summary.items.find(
      (i) =>
        i.page === page &&
        (i.status === "mapping" || i.status === "needs_review"),
    )?.table_id ||
    summary.items.find((i) => i.page === page)?.table_id;
  const required = summary.pending_tables + summary.reviewed_tables;
  const statusLabels = {
    mapping: "Match columns",
    needs_review: "Review required",
    reviewed: "Reviewed",
    ready: "Ready to save",
    saved: "Saved",
  };
  return (
    <section
      className="card review-checklist"
      aria-label="Review checklist"
      id="review-checklist"
      tabIndex={-1}
    >
      <div className="card-heading">
        <div>
          <h2>
            Review checklist{" "}
            <Pill tone={pending.length ? "warn" : "good"}>
              {pending.length} need attention
            </Pill>
          </h2>
          <p>
            {required
              ? `${summary.reviewed_tables} of ${required} required table reviews complete. `
              : ""}
            {pending.length
              ? "Start with the highlighted tables. Select an item to open its source page."
              : "No required table reviews remain. Select and save the rows you need."}
          </p>
        </div>
        {pending.length > 0 && (
          <button className="primary" onClick={() => onJump(pending[0])}>
            Next table to review
            <ArrowRight size={16} />
          </button>
        )}
      </div>
      <div className="review-queue">
        {summary.items.map((item) => (
          <button
            key={item.table_id}
            className={`review-queue-item ${item.table_id === activeId ? "current" : ""}`}
            aria-current={item.table_id === activeId ? "step" : undefined}
            onClick={() => onJump(item)}
          >
            <span className="queue-page">
              {item.status === "reviewed" || item.status === "saved" ? (
                <CheckCircle2 size={20} />
              ) : (
                <CircleHelp size={20} />
              )}
              Page {item.page}
            </span>
            <span>
              <strong>{item.label}</strong>
              <small>{item.reason}</small>
            </span>
            <Pill
              tone={
                item.status === "mapping" || item.status === "needs_review"
                  ? "warn"
                  : item.status === "reviewed" || item.status === "saved"
                    ? "good"
                    : "neutral"
              }
            >
              {statusLabels[item.status]}
            </Pill>
            <ArrowRight size={16} />
          </button>
        ))}
      </div>
      {summary.problem_pages.length > 0 && (
        <div className="review-problems">
          <strong>Some pages could not be read.</strong>
          <p>Check the original pages or upload a clearer document to retry.</p>
          {summary.problem_pages.map((n) => (
            <button className="secondary" key={n} onClick={() => onPage(n)}>
              Check page {n}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
