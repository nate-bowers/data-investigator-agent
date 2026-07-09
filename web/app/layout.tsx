import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://investigator.natebowers.dev"),
  title: "Data Investigator",
  description: "An autonomous data-analysis agent that investigates a dataset one question at a time, choosing each step from the last result.",
  openGraph: {
    title: "Data Investigator",
    description: "An autonomous data-analysis agent that investigates a dataset one question at a time, choosing each step from the last result.",
    url: "https://investigator.natebowers.dev",
    siteName: "Data Investigator",
  },
  twitter: {
    card: "summary_large_image",
    title: "Data Investigator",
    description: "An autonomous data-analysis agent that investigates a dataset one question at a time, choosing each step from the last result.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
