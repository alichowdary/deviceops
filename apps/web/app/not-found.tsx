import Link from "next/link";

import { StatePanel } from "@/components/state-panel";

export default function NotFound() {
  return (
    <StatePanel
      eyebrow="404"
      title="Page not found"
      description="The requested DeviceOps page does not exist."
      action={<Link className="button button-secondary" href="/">Return home</Link>}
    />
  );
}
