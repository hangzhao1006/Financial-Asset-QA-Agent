import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FinQ — Financial Asset QA System",
  description: "AI-powered financial asset question answering with real-time market data and RAG",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
