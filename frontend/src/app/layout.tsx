import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "Bitunix Trader",
  description: "Bitunix Futures kereskedő dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="hu" className="dark">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
