import { useState } from "react";
import { ArrowRight, Check, X } from "lucide-react";
import { Modal, Pill } from "./components";
import { money } from "./presentation";
export type ClassificationAlias = {
  id: string;
  contractor: string;
  source_label: string;
  target_position: string;
};
export type ClassificationGraph = {
  reference_version: string;
  aliases: ClassificationAlias[];
  contractors: {
    name: string;
    families: {
      id: string;
      label: string;
      aliases: string[];
      classifications: {
        name: string;
        level: string;
        aliases: string[];
        schedules: {
          row: string;
          reg_rate: string;
          status: string;
          start: string;
          finish: string;
          issues: string[];
        }[];
      }[];
    }[];
  }[];
};
export default function ClassificationMap({
  graph,
  initialContractor,
  busy,
  error,
  onSave,
  onDelete,
  onClose,
}: {
  graph: ClassificationGraph;
  initialContractor: string;
  busy: boolean;
  error: string;
  onSave: (contractor: string, source: string, target: string) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}) {
  const [contractor, setContractor] = useState(
    graph.contractors.some((c) => c.name === initialContractor)
      ? initialContractor
      : graph.contractors[0]?.name || "",
  );
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const selected = graph.contractors.find((c) => c.name === contractor);
  return (
    <Modal title="Classification map" onClose={onClose} wide>
      <div className="modal-body">
        <p>
          The active tracker supplies the classifications and schedules below.
          Trade families connect related descriptions, such as Masons → Masonry
          → Bricklayer. Different levels can have different rates; the checker
          compares only applicable approved schedules for the selected
          contractor.
        </p>
        {error && (
          <div className="message error" role="alert">
            {error}
          </div>
        )}
        <label>
          Contractor
          <select
            value={contractor}
            onChange={(e) => {
              setContractor(e.target.value);
              setTarget("");
            }}
          >
            {graph.contractors.map((c) => (
              <option key={c.name}>{c.name}</option>
            ))}
          </select>
        </label>
        <div className="classification-path">
          <Pill>{contractor}</Pill>
          <ArrowRight size={15} />
          <span>Trade family</span>
          <ArrowRight size={15} />
          <span>Tracker classification</span>
          <ArrowRight size={15} />
          <span>Approved schedule & regular rate</span>
        </div>
        <div className="classification-tree">
          {selected?.families.map((group) => (
            <details key={group.id} open>
              <summary>
                {group.label}{" "}
                <Pill>{group.classifications.length} classifications</Pill>
              </summary>
              {group.aliases.length > 0 && (
                <p className="family-aliases">
                  Recognized descriptions: {group.aliases.join(", ")}
                </p>
              )}
              <ul>
                {group.classifications.map((c) => (
                  <li key={c.name}>
                    <strong>{c.name}</strong>
                    {c.level && <Pill>{c.level}</Pill>}
                    {c.aliases.length > 0 && (
                      <small>Saved equivalents: {c.aliases.join(", ")}</small>
                    )}
                    <div className="schedule-chips">
                      {c.schedules.map((s) => (
                        <span key={s.row} title={s.issues.join(" · ")}>
                          Row {s.row} · REG {money(s.reg_rate)} ·{" "}
                          {s.status || "No approval status"}
                          <small>
                            {s.start || "Unknown start"} →{" "}
                            {s.finish || "Unknown finish"}
                          </small>
                        </span>
                      ))}
                    </div>
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </div>
        <form
          className="alias-form"
          onSubmit={(e) => {
            e.preventDefault();
            onSave(contractor, source, target);
          }}
        >
          <h3>Add an equivalent job title</h3>
          <p>
            This relationship applies only to {contractor}. Choose an actual
            tracker classification; it will be used for future checks.
          </p>
          <div className="form-grid">
            <label>
              Title printed in the document
              <input
                required
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="e.g. Mason foreman"
                maxLength={300}
              />
            </label>
            <label>
              Equivalent tracker classification
              <select
                required
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                <option value="">Choose classification</option>
                {selected?.families
                  .flatMap((g) => g.classifications)
                  .map((c) => (
                    <option key={c.name}>{c.name}</option>
                  ))}
              </select>
            </label>
          </div>
          {source && target && (
            <p className="notice">
              {source} → {target} · {contractor}
            </p>
          )}
          <button
            className="primary"
            disabled={busy || !source.trim() || !target}
          >
            <Check size={16} />
            Save relationship
          </button>
        </form>
        {graph.aliases.filter((a) => a.contractor === contractor).length >
          0 && (
          <section className="saved-aliases">
            <h3>Saved relationships</h3>
            {graph.aliases
              .filter((a) => a.contractor === contractor)
              .map((a) => (
                <div key={a.id}>
                  <span>
                    {a.source_label} → {a.target_position}
                  </span>
                  <button
                    className="icon-button"
                    disabled={busy}
                    onClick={() => onDelete(a.id)}
                    aria-label={`Remove relationship ${a.source_label}`}
                  >
                    <X size={16} />
                  </button>
                </div>
              ))}
          </section>
        )}
      </div>
    </Modal>
  );
}
