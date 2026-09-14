import type { LucideIcon } from "lucide-react";

export function MetricValue({
  label,
  value,
  unit,
  icon: Icon,
}: {
  label: string;
  value: string;
  unit?: string;
  icon: LucideIcon;
}) {
  return (
    <div className="metric-value">
      <div className="metric-heading">
        <span>{label}</span>
        <Icon aria-hidden="true" size={14} strokeWidth={1.7} />
      </div>
      <div className="metric-number">
        {value}
        {unit ? <span className="metric-unit">{unit}</span> : null}
      </div>
    </div>
  );
}
