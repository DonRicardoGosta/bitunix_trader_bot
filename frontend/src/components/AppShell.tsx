"use client";

import type { ReactNode } from "react";
import { RefreshIntervalProvider } from "@/contexts/RefreshIntervalContext";
import { Navbar } from "@/components/Navbar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <RefreshIntervalProvider>
      <Navbar />
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </RefreshIntervalProvider>
  );
}
