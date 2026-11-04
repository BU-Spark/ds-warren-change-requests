import type { KeyboardEvent } from "react";
export type DocumentView = "upload" | "review";
export default function DocumentWorkflowNav({
  view,
  count,
  busy,
  onChange,
}: {
  view: DocumentView;
  count: number;
  busy: boolean;
  onChange: (view: DocumentView) => void;
}) {
  const select = (event: KeyboardEvent<HTMLButtonElement>) => {
    const target =
      event.key === "Home"
        ? "upload"
        : event.key === "End"
          ? "review"
          : ["ArrowLeft", "ArrowRight"].includes(event.key)
            ? view === "upload"
              ? "review"
              : "upload"
            : null;
    if (target) {
      event.preventDefault();
      onChange(target);
      document.getElementById(`document-tab-${target}`)?.focus();
    }
  };
  return (
    <div
      className="document-workflow-nav"
      role="tablist"
      aria-label="Document workflow"
    >
      <button
        id="document-tab-upload"
        role="tab"
        aria-selected={view === "upload"}
        aria-controls="document-workflow-panel"
        tabIndex={view === "upload" ? 0 : -1}
        disabled={busy}
        onClick={() => onChange("upload")}
        onKeyDown={select}
      >
        Upload document
      </button>
      <button
        id="document-tab-review"
        role="tab"
        aria-selected={view === "review"}
        aria-controls="document-workflow-panel"
        tabIndex={view === "review" ? 0 : -1}
        disabled={busy}
        onClick={() => onChange("review")}
        onKeyDown={select}
      >
        Documents in review <span>{count}</span>
      </button>
    </div>
  );
}
