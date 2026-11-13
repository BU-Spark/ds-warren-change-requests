import type { Finding } from "./types";

export type Outcome = Finding["outcome"];
export function metrics(results: Finding[]) {
  return {
    total: results.length,
    match: results.filter((r) => r.outcome === "match").length,
    difference: results.filter((r) => r.outcome === "difference").length,
    needs_review: results.filter((r) => r.outcome === "needs_review").length,
  };
}
export const percent = (count: number, total: number) =>
  total
    ? `${((count / total) * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%`
    : "—";

export function documents(results: Finding[]) {
  const groups = new Map<string, Finding[]>();
  for (const result of results) {
    const key = result.document_id;
    const group = groups.get(key);
    if (group) group.push(result);
    else groups.set(key, [result]);
  }
  return [...groups]
    .map(([id, findings]) => ({
      id,
      filename: findings[0].source_file || "Unnamed document",
      references: [
        ...new Set(findings.map((f) => f.document_reference).filter(Boolean)),
      ],
      projects: [...new Set(findings.map((f) => f.project).filter(Boolean))],
      findings,
      counts: metrics(findings),
    }))
    .sort(
      (a, b) =>
        a.filename.localeCompare(b.filename) || a.id.localeCompare(b.id),
    );
}
