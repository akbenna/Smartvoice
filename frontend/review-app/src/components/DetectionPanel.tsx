"use client";

import type { DetectionResult } from "@/lib/api";

interface DetectionPanelProps {
  detection: DetectionResult | null;
}

const ERNST_COLORS: Record<string, string> = {
  kritiek: "bg-red-100 text-red-800 border-red-200",
  hoog: "bg-orange-100 text-orange-800 border-orange-200",
  middel: "bg-yellow-100 text-yellow-800 border-yellow-200",
  laag: "bg-blue-100 text-blue-800 border-blue-200",
};

const PRIORITEIT_COLORS: Record<string, string> = {
  hoog: "bg-red-100 text-red-700",
  middel: "bg-yellow-100 text-yellow-700",
  laag: "bg-gray-100 text-gray-600",
};

export default function DetectionPanel({ detection }: DetectionPanelProps) {
  if (!detection) return null;

  const { rode_vlaggen, ontbrekende_info } = detection;
  const hasFlags = rode_vlaggen.length > 0;
  const hasMissing = ontbrekende_info.length > 0;

  return (
    <div className="space-y-4">
      {/* Rode Vlaggen */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-4 border-b border-gray-200">
          <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${hasFlags ? "bg-red-500" : "bg-green-500"}`} />
            Rode Vlaggen
          </h3>
        </div>
        <div className="p-4">
          {hasFlags ? (
            <ul className="space-y-3">
              {rode_vlaggen.map((flag) => (
                <li
                  key={flag.id}
                  className={`p-3 rounded-lg border ${ERNST_COLORS[flag.ernst] || ERNST_COLORS.middel}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-bold uppercase">
                      {flag.ernst}
                    </span>
                    <span className="text-xs opacity-75">{flag.categorie}</span>
                  </div>
                  <p className="text-sm">{flag.beschrijving}</p>
                  {flag.nhg_referentie && (
                    <p className="text-xs opacity-75 mt-1">
                      {flag.nhg_referentie}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-green-600">
              Geen rode vlaggen gedetecteerd.
            </p>
          )}
        </div>
      </div>

      {/* Ontbrekende Informatie */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-4 border-b border-gray-200">
          <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${hasMissing ? "bg-yellow-500" : "bg-green-500"}`} />
            Ontbrekende Informatie
          </h3>
        </div>
        <div className="p-4">
          {hasMissing ? (
            <ul className="space-y-2">
              {ontbrekende_info.map((info) => (
                <li
                  key={info.id}
                  className="flex items-start gap-3 p-2 rounded-lg hover:bg-gray-50"
                >
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-medium mt-0.5 ${
                      PRIORITEIT_COLORS[info.prioriteit] || PRIORITEIT_COLORS.laag
                    }`}
                  >
                    {info.prioriteit}
                  </span>
                  <div>
                    <p className="text-sm text-gray-800">{info.beschrijving}</p>
                    <p className="text-xs text-gray-500">Veld: {info.veld}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-green-600">
              Alle verwachte informatie is aanwezig.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
