export const labels: Record<string, string> = {
  position_original: "Classification",
  reg_rate: "Regular rate",
  ot_rate: "Overtime",
  dt_rate: "Double time",
  rate: "Regular rate (source)",
  work_start: "Work start",
  work_end: "Work finish",
  work_date_source: "Date source",
  worker_name: "Worker",
  description: "Description",
  record_id: "Record ID",
  source_file: "Source document",
  source_page: "Page",
  project_id: "Project ID (filename)",
  contractor: "Contractor",
  project: "Project",
  document_reference: "Reference",
  ticket_id: "Ticket",
  reg_hours: "ST hours",
  ot_hours: "OT hours",
  dt_hours: "DT hours",
  hours: "Hours",
};
export const formatDate = (date: string) =>
  new Date(date).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
export const money = (value: string) => {
  if (value === "" || value == null) return "—";
  const [whole, fraction = ""] = value.split(".");
  const sign = whole.startsWith("-") ? "-" : "";
  return `${sign}$${whole.replace("-", "").replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction.padEnd(2, "0")}`;
};
export const display = (value: string) => value || "—";
export const short = (value: string) => value.slice(0, 12);
export const searchRows = <T>(rows: T[], search: string) =>
  rows.filter((row) =>
    JSON.stringify(row).toLowerCase().includes(search.toLowerCase()),
  );

export const rateTypeLabel = (type: string) =>
  ({
    REG: "Regular (REG)",
    ST: "Regular (REG)",
    OT: "Overtime (OT)",
    DT: "Double time (DT)",
  })[type] || "Recheck required";

export function withWorkDates(
  row: Record<string, string>,
  supplied: Record<string, string> = {},
): Record<string, string> {
  const start = supplied.work_start || row.work_start;
  return {
    ...row,
    work_start: start,
    work_end: supplied.work_end || row.work_end || start,
    work_date_source:
      supplied.work_start || supplied.work_end
        ? "Reviewer entered"
        : start
          ? "Printed"
          : "Missing — needs review",
  };
}
