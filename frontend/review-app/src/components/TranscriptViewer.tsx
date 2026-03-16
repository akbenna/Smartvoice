"use client";

import type { TranscriptSegment } from "@/lib/api";

interface TranscriptViewerProps {
  segments: TranscriptSegment[];
}

const SPREKER_COLORS: Record<string, string> = {
  arts: "bg-blue-100 text-blue-800",
  patient: "bg-green-100 text-green-800",
  onbekend: "bg-gray-100 text-gray-600",
};

function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export default function TranscriptViewer({ segments }: TranscriptViewerProps) {
  if (segments.length === 0) return null;

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-gray-900">Transcript</h2>
        <p className="text-xs text-gray-500 mt-1">
          {segments.length} segmenten
        </p>
      </div>
      <div className="p-4 space-y-3 max-h-96 overflow-y-auto">
        {segments.map((seg, i) => (
          <div key={i} className="flex gap-3">
            <span className="text-xs text-gray-400 w-10 pt-1 shrink-0">
              {formatTime(seg.start)}
            </span>
            <div className="flex-1">
              <span
                className={`inline-block text-xs font-medium px-2 py-0.5 rounded mb-1 ${
                  SPREKER_COLORS[seg.spreker] || SPREKER_COLORS.onbekend
                }`}
              >
                {seg.spreker}
              </span>
              <p className="text-sm text-gray-800">{seg.tekst}</p>
            </div>
            <span className="text-xs text-gray-300 pt-1 shrink-0">
              {(seg.confidence * 100).toFixed(0)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
