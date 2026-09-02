import type { Metadata } from "next";
import "./globals.css";
import { CommandPalette } from "@/components/CommandPalette";

export const metadata: Metadata = {
  title: "Arbiter — Cockpit",
  description: "A verification layer for money movement.",
};

// Restore the viewer's theme choice before first paint (no FOUC).
const THEME_INIT = `try{var t=localStorage.getItem('arbiter-theme');if(t==='light'||t==='dark')document.documentElement.setAttribute('data-theme',t);}catch(e){}`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className="min-h-screen">
        {children}
        <CommandPalette />
      </body>
    </html>
  );
}
