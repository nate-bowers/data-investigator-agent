import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  // Update this once a custom domain is live.
  metadataBase: new URL("https://web-mu-three-lu56la822j.vercel.app"),
  title: "Data Investigator",
  description: "Watch an agent investigate a dataset and explain its reasoning.",
  openGraph: {
    title: "Data Investigator",
    description: "Watch an agent investigate a dataset and explain its reasoning.",
    url: "https://web-mu-three-lu56la822j.vercel.app",
    siteName: "Data Investigator",
  },
  twitter: {
    card: "summary_large_image",
    title: "Data Investigator",
    description: "Watch an agent investigate a dataset and explain its reasoning.",
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
