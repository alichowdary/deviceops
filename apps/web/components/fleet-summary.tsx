import type { Device } from "@/lib/types";

export function FleetSummary({ devices }: { devices: Device[] }) {
  const counts = devices.reduce(
    (totals, device) => {
      if (device.status === "online") totals.online += 1;
      else if (device.status === "offline") totals.offline += 1;
      else totals.unknown += 1;
      return totals;
    },
    { online: 0, offline: 0, unknown: 0 },
  );

  const summaries = [
    { label: "Total devices", value: devices.length, tone: "" },
    { label: "Online", value: counts.online, tone: "summary-online" },
    { label: "Offline", value: counts.offline, tone: "summary-offline" },
    { label: "Unknown", value: counts.unknown, tone: "summary-unknown" },
  ];

  return (
    <section aria-label="Fleet status summary" className="summary-strip">
      {summaries.map((summary) => (
        <div className="summary-item" key={summary.label}>
          <span className="summary-label">
            {summary.tone ? (
              <span
                aria-hidden="true"
                className={`summary-indicator ${summary.tone}`}
              />
            ) : null}
            {summary.label}
          </span>
          <strong className="summary-value">{summary.value}</strong>
        </div>
      ))}
    </section>
  );
}
