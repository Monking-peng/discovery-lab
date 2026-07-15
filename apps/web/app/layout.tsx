import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Discovery Lab · Evidence Explorer / 证据工作台",
  description: "Turn fragmented product research into traceable, reviewable evidence. 将零散产品研究整理为可追溯、可复核的证据。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
