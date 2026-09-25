import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Recoverix | Forensic Evidence Recovery Workspace",
  description: "Deterministic digital evidence recovery and grounded AI interpretation",
};

import { TopNav } from "@/components/layout/TopNav";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
    >
      <body className="font-sans antialiased bg-slate-950 text-slate-100 min-h-full flex flex-col">
        <TopNav />
        {children}
      </body>
    </html>
  );
}
