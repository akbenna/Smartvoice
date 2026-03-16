"use client";

import { useState } from "react";
import AudioUpload from "@/components/AudioUpload";
import SOEPEditor from "@/components/SOEPEditor";
import DetectionPanel from "@/components/DetectionPanel";
import TranscriptViewer from "@/components/TranscriptViewer";
import type { SOEPConcept, DetectionResult, TranscriptSegment } from "@/lib/api";

type AppState = "upload" | "processing" | "review" | "approved";

export default function Home() {
  const [state, setState] = useState<AppState>("upload");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [soep, setSoep] = useState<SOEPConcept | null>(null);
  const [detection, setDetection] = useState<DetectionResult | null>(null);
  const [transcript, setTranscript] = useState<TranscriptSegment[]>([]);

  const handleUploadComplete = (newSessionId: string) => {
    setSessionId(newSessionId);
    setState("processing");
    // Simuleer verwerking (in productie: poll status endpoint)
    setTimeout(() => {
      setSoep({
        S: "Patient klaagt over hoofdpijn sinds 3 dagen, drukkend karakter, geen koorts. Paracetamol helpt onvoldoende.",
        O: "Geen LO verricht",
        E: "Spanningshoofdpijn (ICPC N02)",
        P: "Advies: rust, voldoende drinken. Ibuprofen 400mg 3dd zo nodig. Controle bij aanhouden >1 week.",
        icpc_code: "N02",
        icpc_titel: "Spanningshoofdpijn",
        confidence: 0.87,
      });
      setDetection({
        rode_vlaggen: [],
        ontbrekende_info: [
          {
            id: "mi_1",
            veld: "vitale_parameters",
            beschrijving: "Bloeddruk niet gemeten",
            prioriteit: "middel",
          },
        ],
      });
      setTranscript([
        { spreker: "arts", start: 0, eind: 5, tekst: "Goedemorgen, waarmee kan ik u helpen?", confidence: 0.95 },
        { spreker: "patient", start: 5, eind: 15, tekst: "Ik heb al drie dagen hoofdpijn, het is een drukkend gevoel.", confidence: 0.92 },
        { spreker: "arts", start: 15, eind: 22, tekst: "Heeft u ook koorts of last van uw nek?", confidence: 0.94 },
        { spreker: "patient", start: 22, eind: 30, tekst: "Nee, geen koorts. Ik heb paracetamol geprobeerd maar dat helpt niet goed.", confidence: 0.91 },
      ]);
      setState("review");
    }, 2000);
  };

  const handleApprove = () => {
    setState("approved");
  };

  return (
    <div className="space-y-6">
      {/* Status bar */}
      <div className="flex items-center gap-2 text-sm">
        <Step label="1. Upload" active={state === "upload"} done={state !== "upload"} />
        <Connector />
        <Step label="2. Verwerking" active={state === "processing"} done={state === "review" || state === "approved"} />
        <Connector />
        <Step label="3. Review" active={state === "review"} done={state === "approved"} />
        <Connector />
        <Step label="4. Goedgekeurd" active={state === "approved"} done={false} />
      </div>

      {/* Upload */}
      {state === "upload" && <AudioUpload onComplete={handleUploadComplete} />}

      {/* Processing */}
      {state === "processing" && (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <div className="animate-spin w-12 h-12 border-4 border-primary-200 border-t-primary-600 rounded-full mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-gray-900">Verwerking bezig...</h2>
          <p className="text-gray-500 mt-2">
            Audio wordt getranscribeerd en geanalyseerd. Dit duurt enkele minuten.
          </p>
        </div>
      )}

      {/* Review */}
      {state === "review" && soep && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <SOEPEditor soep={soep} onChange={setSoep} onApprove={handleApprove} />
            <TranscriptViewer segments={transcript} />
          </div>
          <div>
            <DetectionPanel detection={detection} />
          </div>
        </div>
      )}

      {/* Approved */}
      {state === "approved" && (
        <div className="bg-white rounded-lg shadow p-8 text-center">
          <div className="w-16 h-16 bg-success-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-success-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-gray-900">SOEP goedgekeurd</h2>
          <p className="text-gray-500 mt-2">Het SOEP-verslag is opgeslagen en klaar voor export naar het HIS.</p>
          <div className="mt-6 flex gap-3 justify-center">
            <button
              onClick={() => navigator.clipboard.writeText(`S: ${soep?.S}\nO: ${soep?.O}\nE: ${soep?.E}\nP: ${soep?.P}`)}
              className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700"
            >
              Kopieer naar klembord
            </button>
            <button
              onClick={() => { setState("upload"); setSoep(null); setDetection(null); setTranscript([]); }}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
            >
              Nieuw consult
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Step({ label, active, done }: { label: string; active: boolean; done: boolean }) {
  return (
    <span
      className={`px-3 py-1 rounded-full text-xs font-medium ${
        active
          ? "bg-primary-100 text-primary-700 ring-2 ring-primary-500"
          : done
          ? "bg-success-100 text-success-700"
          : "bg-gray-100 text-gray-500"
      }`}
    >
      {label}
    </span>
  );
}

function Connector() {
  return <div className="w-8 h-px bg-gray-300" />;
}
