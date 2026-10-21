import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Data Redundancy Removal System",
  description: "CodeAlpha Cloud Computing Task 1 - validate records and store only unique, verified data.",
};

const nav = [
  { href: "/", label: "Dashboard" },
  { href: "/add", label: "Add Student" },
  { href: "/records", label: "Student Records" },
];

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-100 text-slate-900 antialiased">
        <header className="bg-gradient-to-r from-[#0b3a63] to-[#0f4c81] text-white">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
            <Link href="/" className="flex items-center gap-2 font-semibold">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-white/15 text-sm font-bold">DR</span>
              Data Redundancy Removal
            </Link>
            <nav className="flex gap-1 text-sm" aria-label="Main">
              {nav.map((n) => (
                <Link key={n.href} href={n.href} className="rounded-md px-3 py-1.5 hover:bg-white/15">
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-6xl px-4 pb-6 text-xs text-slate-500">
          CodeAlpha Cloud Computing Internship · Task 1 · Live preview (Next.js + PostgreSQL). The Flask
          submission project is in <code>CodeAlpha_DataRedundancyRemoval/</code>.
        </footer>
      </body>
    </html>
  );
}
