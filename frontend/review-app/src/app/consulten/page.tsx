"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import type { ConsultListItem } from "@/lib/api";
import LoginPage from "@/components/LoginPage";

export default function ConsultenPage() {
  const { user, isLoading } = useAuth();
  const [consults, setConsults] = useState<ConsultListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    loadConsults();
  }, [user]);

  const loadConsults = async () => {
    setLoading(true);
    try {
      const result = await api.listConsults(20, 0);
      setConsults(result.consults);
      setTotal(result.total);
    } catch {
      // Fout bij laden
    } finally {
      setLoading(false);
    }
  };

  if (isLoading) return null;
  if (!user) return <LoginPage />;

  const statusLabel: Record<string, { text: string; color: string }> = {
    recording: { text: "Opname", color: "bg-blue-100 text-blue-700" },
    transcribing: { text: "Transcriberen", color: "bg-yellow-100 text-yellow-700" },
    extracting: { text: "Analyseren", color: "bg-orange-100 text-orange-700" },
    reviewing: { text: "Review", color: "bg-purple-100 text-purple-700" },
    approved: { text: "Goedgekeurd", color: "bg-success-100 text-success-600" },
    exported: { text: "Geexporteerd", color: "bg-gray-100 text-gray-600" },
    failed: { text: "Mislukt", color: "bg-danger-100 text-danger-600" },
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Consulten</h1>
        <a href="/" className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 text-sm">
          Nieuw consult
        </a>
      </div>

      {loading ? (
        <div className="text-center py-12">
          <div className="animate-spin w-8 h-8 border-4 border-primary-200 border-t-primary-600 rounded-full mx-auto" />
        </div>
      ) : consults.length === 0 ? (
        <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
          Nog geen consulten. Start een nieuw consult om te beginnen.
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Datum</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Patient</th>
                <th className="text-left px-4 py-3 text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="text-right px-4 py-3 text-xs font-medium text-gray-500 uppercase">Actie</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {consults.map((c) => {
                const status = statusLabel[c.status] || { text: c.status, color: "bg-gray-100 text-gray-600" };
                return (
                  <tr key={c.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-700">
                      {c.started_at ? new Date(c.started_at).toLocaleString("nl-NL", { dateStyle: "medium", timeStyle: "short" }) : "-"}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500 font-mono">{c.patient_hash}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${status.color}`}>
                        {status.text}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {c.status === "reviewing" && (
                        <a href={`/?session=${c.id}`} className="text-sm text-primary-600 hover:underline">
                          Review
                        </a>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {total > 20 && (
            <div className="px-4 py-3 border-t text-sm text-gray-500">
              {total} consulten totaal
            </div>
          )}
        </div>
      )}
    </div>
  );
}
