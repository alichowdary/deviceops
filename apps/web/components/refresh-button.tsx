import { RefreshCw } from "lucide-react";

export function RefreshButton({
  loading,
  onClick,
}: {
  loading: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className="button button-secondary"
      disabled={loading}
      onClick={onClick}
      type="button"
    >
      <RefreshCw
        aria-hidden="true"
        className={loading ? "icon-spin" : undefined}
        size={13}
      />
      <span className="button-label">Refresh</span>
    </button>
  );
}
