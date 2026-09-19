import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Fleet" };

export default function FleetLayout({ children }: { children: ReactNode }) {
  return children;
}
