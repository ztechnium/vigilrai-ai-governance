import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "RAI Control Plane — Govern AI Actions at Runtime",
    template: "%s | RAI Control Plane",
  },
  description:
    "Runtime governance for AI agents — register, authorize, enforce policies, and produce audit-ready evidence for every consequential action.",
  keywords: [
    "AI governance",
    "runtime enforcement",
    "responsible AI",
    "agent governance",
    "AI policy",
    "audit trail",
  ],
  openGraph: {
    title: "RAI Control Plane — Govern AI Actions at Runtime",
    description:
      "Register agents, authorize tool calls, enforce policies, and produce audit-ready evidence.",
    type: "website",
  },
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
