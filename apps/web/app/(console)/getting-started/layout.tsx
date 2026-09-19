import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Getting Started" };

export default function GettingStartedLayout({
  children,
}: {
  children: ReactNode;
}) {
  return children;
}
