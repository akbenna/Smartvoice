import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI-Consultassistent — Review",
  description:
    "Privacy-first AI-systeem voor consultdocumentatie in de huisartsenpraktijk",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="nl">
      <body className="min-h-screen bg-gray-50">
        {/* Header */}
        <header className="bg-white border-b border-gray-200 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-sm">AI</span>
              </div>
              <div>
                <h1 className="text-lg font-semibold text-gray-900">
                  AI-Consultassistent
                </h1>
                <p className="text-xs text-gray-500">
                  SOEP-dossiervoering Review
                </p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-gray-600">Dr. Arts</span>
              <div className="w-8 h-8 bg-gray-300 rounded-full" />
            </div>
          </div>
        </header>

        {/* Main content */}
        <main className="max-w-7xl mx-auto px-4 py-6">{children}</main>

        {/* Footer */}
        <footer className="border-t border-gray-200 mt-auto">
          <div className="max-w-7xl mx-auto px-4 py-3 text-center text-xs text-gray-400">
            AI-Consultassistent v0.1.0 — Volledig lokale verwerking — NEN
            7510/7513 conform
          </div>
        </footer>
      </body>
    </html>
  );
}
