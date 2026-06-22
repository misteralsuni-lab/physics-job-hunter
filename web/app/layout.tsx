import type { Metadata, Viewport } from "next";
import { ToastViewport } from "@/app/components/ui/Toast";
import { Sidebar } from "@/app/components/layout/Sidebar";
import "./globals.css";

export const metadata: Metadata = {
  title: "Physics Job Hunter",
  description:
    "Reactive, touch-friendly dashboard for the Physics Job Hunter scraping and LLM-scoring pipeline.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Allow the OS to tint the browser chrome to match the brand on mobile.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8fafc" },
    { media: "(prefers-color-scheme: dark)", color: "#020617" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en-GB">
      <body>
        <div className="flex min-h-dvh flex-col md:flex-row">
          <Sidebar />
          {/* Bottom padding on mobile clears the fixed tab bar. */}
          <main className="flex-1 pb-24 md:pb-0">
            <div className="mx-auto w-full max-w-7xl px-4 py-6 md:px-8 md:py-8">
              {children}
            </div>
          </main>
          <ToastViewport />
        </div>
      </body>
    </html>
  );
}
