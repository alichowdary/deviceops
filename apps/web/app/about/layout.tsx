import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "About",
  description:
    "Learn how DeviceOps monitors and controls heterogeneous IoT devices through a secure, capability-driven architecture.",
};

export default function AboutLayout({ children }: { children: ReactNode }) {
  return children;
}
