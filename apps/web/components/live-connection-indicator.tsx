import type { LiveConnectionState } from "@/lib/types";

const labels: Record<LiveConnectionState, string> = {
  connecting: "Connecting",
  live: "Live",
  reconnecting: "Reconnecting",
};

export function LiveConnectionIndicator({
  state,
}: {
  state: LiveConnectionState;
}) {
  return (
    <span className={`live-indicator live-${state}`}>
      <span aria-hidden="true" className="live-dot" />
      {labels[state]}
    </span>
  );
}
