import { CircleCheck, CircleHelp, CircleX } from "lucide-react";

import type { DeviceStatus } from "@/lib/types";

const statusPresentation = {
  online: { icon: CircleCheck, className: "status-online" },
  offline: { icon: CircleX, className: "status-offline" },
  unknown: { icon: CircleHelp, className: "status-unknown" },
} as const;

export function StatusBadge({ status }: { status: DeviceStatus }) {
  const presentation = statusPresentation[status] ?? statusPresentation.unknown;
  const Icon = presentation.icon;

  return (
    <span className={`status-badge ${presentation.className}`}>
      <Icon aria-hidden="true" size={12} strokeWidth={2.2} />
      {status}
    </span>
  );
}
