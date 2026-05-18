"use client";

import type { ReactNode } from "react";
import { RefreshIntervalProvider } from "@/contexts/RefreshIntervalContext";
import { LiveUpdatesProvider } from "@/contexts/LiveUpdatesContext";
import { NavigationLoadingProvider } from "@/contexts/NavigationLoadingContext";
import { ChunkLoadRecovery } from "@/components/ChunkLoadRecovery";
import { Navbar } from "@/components/Navbar";
import { MainContentArea } from "@/components/MainContentArea";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <RefreshIntervalProvider>
      <LiveUpdatesProvider>
        <NavigationLoadingProvider>
          <ChunkLoadRecovery />
          <Navbar />
          <MainContentArea>{children}</MainContentArea>
        </NavigationLoadingProvider>
      </LiveUpdatesProvider>
    </RefreshIntervalProvider>
  );
}
