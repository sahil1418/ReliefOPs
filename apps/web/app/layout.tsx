import type { Metadata } from "next";

import { AuthProvider } from "@/components/providers/AuthProvider";
import { Splash } from "@/components/Splash";

import "./globals.css";

export const metadata: Metadata = {
  title: "ReliefOps — AI Disaster Logistics",
  description:
    "AI dispatcher that turns chaos into coordinated relief in the first 72 hours of a disaster.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        <Splash />
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
