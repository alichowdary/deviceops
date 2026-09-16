import { formatExactTime, formatUptime } from "@/lib/format";
import type { DeviceCommand } from "@/lib/types";


const commandLabels: Record<DeviceCommand["type"], string> = {
  set_led: "Set LED",
  set_reporting_interval: "Set reporting interval",
  request_diagnostics: "Request diagnostics",
};

function commandDetail(command: DeviceCommand): string {
  if (command.status === "failed" && typeof command.result?.error === "string") {
    return command.result.error;
  }
  if (command.type === "set_led") {
    const state = command.result?.on ?? command.arguments.on;
    return `LED ${state === true ? "on" : "off"}`;
  }
  if (command.type === "set_reporting_interval") {
    const interval = command.result?.interval_s ?? command.arguments.interval_s;
    return `${String(interval)} seconds`;
  }
  if (command.result) {
    const led = command.result.led_on === true ? "LED on" : "LED off";
    const interval = command.result.reporting_interval_s;
    const uptime = command.result.uptime_s;
    return [
      led,
      typeof interval === "number" ? `${interval}s interval` : null,
      typeof uptime === "number" ? `${formatUptime(uptime)} uptime` : null,
    ]
      .filter(Boolean)
      .join(" · ");
  }
  return "Awaiting acknowledgement";
}

export function RecentCommands({ commands }: { commands: DeviceCommand[] }) {
  return (
    <section className="panel commands-panel">
      <div className="section-header">
        <h2 className="section-title">Recent commands</h2>
        <span className="section-meta">newest first · 10 shown</span>
      </div>
      {commands.length === 0 ? (
        <div className="commands-empty">No commands have been issued to this device.</div>
      ) : (
        <div className="data-table-wrap">
          <table className="data-table commands-table">
            <thead>
              <tr>
                <th scope="col">Command</th>
                <th scope="col">Issued</th>
                <th scope="col">Status</th>
                <th scope="col">Arguments / result</th>
              </tr>
            </thead>
            <tbody>
              {commands.map((command) => (
                <tr key={command.command_id}>
                  <td>
                    <span className="table-primary">{commandLabels[command.type]}</span>
                    <span className="table-secondary mono" title={command.command_id}>
                      {command.command_id.slice(0, 8)}
                    </span>
                  </td>
                  <td className="mono">{formatExactTime(command.issued_at)}</td>
                  <td>
                    <span className={`command-status command-status-${command.status}`}>
                      {command.status}
                    </span>
                  </td>
                  <td className="command-detail">{commandDetail(command)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
