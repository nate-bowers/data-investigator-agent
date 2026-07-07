import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Data Investigator",
  description: "Watch an agent investigate a dataset and explain its reasoning.",
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
