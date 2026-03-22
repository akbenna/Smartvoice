"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { useAudioRecorder, RecorderState } from "@/lib/useAudioRecorder";

interface ConsultRecorderProps {
  onComplete: (sessionId: string) => void;
}

/**
 * Spreekkamer-recorder: opnemen → automatisch uploaden → SOEP pipeline.
 * Vergelijkbaar met Juvely/Dragon Medical workflow.
 */
export default function ConsultRecorder({ onComplete }: ConsultRecorderProps) {
  const {
    state,
    duration,
    audioBlob,
    audioUrl,
    analyserNode,
    error: recorderError,
    start,
    pause,
    resume,
    stop,
    reset,
  } = useAudioRecorder();

  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animFrameRef = useRef<number>(0);

  // ---------------------------------------------------------------------------
  // Waveform visualisatie
  // ---------------------------------------------------------------------------
  const drawWaveform = useCallback(() => {
    const canvas = canvasRef.current;
    const analyser = analyserNode;
    if (!canvas || !analyser) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const draw = () => {
      animFrameRef.current = requestAnimationFrame(draw);
      analyser.getByteTimeDomainData(dataArray);

      const { width, height } = canvas;
      ctx.fillStyle = "#f9fafb";
      ctx.fillRect(0, 0, width, height);

      ctx.lineWidth = 2;
      ctx.strokeStyle = "#dc2626"; // Rood = opname actief
      ctx.beginPath();

      const sliceWidth = width / bufferLength;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const v = dataArray[i] / 128.0;
        const y = (v * height) / 2;

        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);

        x += sliceWidth;
      }

      ctx.lineTo(width, height / 2);
      ctx.stroke();
    };

    draw();
  }, [analyserNode]);

  useEffect(() => {
    if (state === "recording" && analyserNode) {
      drawWaveform();
    } else {
      cancelAnimationFrame(animFrameRef.current);
    }
    return () => cancelAnimationFrame(animFrameRef.current);
  }, [state, analyserNode, drawWaveform]);

  // ---------------------------------------------------------------------------
  // Upload naar backend
  // ---------------------------------------------------------------------------
  const handleUpload = async () => {
    if (!audioBlob) return;
    setUploading(true);
    setUploadError(null);

    try {
      // Converteer blob naar File object met timestamp als naam
      const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
      const ext = audioBlob.type.includes("webm") ? "webm" : "m4a";
      const file = new File([audioBlob], `consult-${timestamp}.${ext}`, {
        type: audioBlob.type,
      });

      const formData = new FormData();
      formData.append("file", file);

      const apiUrl =
        process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

      // JWT token meesturen
      const token =
        typeof window !== "undefined"
          ? localStorage.getItem("ca_token")
          : null;
      const headers: Record<string, string> = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;

      const response = await fetch(`${apiUrl}/api/consult/upload`, {
        method: "POST",
        headers,
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Upload mislukt: ${response.status}`);
      }

      const data = await response.json();
      onComplete(data.session_id);
    } catch (err) {
      setUploadError(
        err instanceof Error ? err.message : "Upload mislukt"
      );
    } finally {
      setUploading(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------
  const formatTime = (seconds: number): string => {
    const m = Math.floor(seconds / 60)
      .toString()
      .padStart(2, "0");
    const s = (seconds % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  const error = recorderError || uploadError;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <div className="bg-white rounded-lg shadow p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Consult opnemen
          </h2>
          <p className="text-sm text-gray-500">
            Neem het gesprek op en ontvang automatisch een SOEP-concept.
          </p>
        </div>
        {state !== "idle" && (
          <div className="flex items-center gap-2">
            {state === "recording" && (
              <span className="flex items-center gap-1.5 text-sm font-medium text-red-600">
                <span className="w-2.5 h-2.5 bg-red-500 rounded-full animate-pulse" />
                Opname
              </span>
            )}
            {state === "paused" && (
              <span className="text-sm font-medium text-amber-600">
                Gepauzeerd
              </span>
            )}
            {state === "stopped" && (
              <span className="text-sm font-medium text-gray-600">
                Gestopt
              </span>
            )}
          </div>
        )}
      </div>

      {/* Timer */}
      <div className="text-center my-6">
        <div
          className={`text-5xl font-mono font-light tracking-wider ${
            state === "recording"
              ? "text-red-600"
              : state === "paused"
              ? "text-amber-600"
              : "text-gray-700"
          }`}
        >
          {formatTime(duration)}
        </div>
        {duration > 0 && state !== "idle" && (
          <p className="text-xs text-gray-400 mt-1">
            {state === "recording" && "Spreek duidelijk in de microfoon"}
            {state === "paused" && "Opname gepauzeerd — druk op hervat"}
            {state === "stopped" && "Opname voltooid — klaar voor verwerking"}
          </p>
        )}
      </div>

      {/* Waveform */}
      {(state === "recording" || state === "paused") && (
        <div className="mb-6 bg-gray-50 rounded-lg p-2">
          <canvas
            ref={canvasRef}
            width={600}
            height={80}
            className="w-full h-20 rounded"
          />
        </div>
      )}

      {/* Audio preview na stop */}
      {state === "stopped" && audioUrl && (
        <div className="mb-6 bg-gray-50 rounded-lg p-4">
          <p className="text-sm text-gray-600 mb-2">Beluister de opname:</p>
          <audio src={audioUrl} controls className="w-full" />
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center justify-center gap-3">
        {/* IDLE: Start knop */}
        {state === "idle" && (
          <button
            onClick={start}
            className="flex items-center gap-2 px-8 py-4 bg-red-600 text-white rounded-full font-medium text-lg hover:bg-red-700 transition-colors shadow-lg hover:shadow-xl"
          >
            <MicIcon />
            Start opname
          </button>
        )}

        {/* RECORDING: Pauze + Stop */}
        {state === "recording" && (
          <>
            <button
              onClick={pause}
              className="flex items-center gap-2 px-5 py-3 bg-amber-100 text-amber-700 rounded-full font-medium hover:bg-amber-200 transition-colors"
            >
              <PauseIcon />
              Pauzeer
            </button>
            <button
              onClick={stop}
              className="flex items-center gap-2 px-5 py-3 bg-gray-800 text-white rounded-full font-medium hover:bg-gray-900 transition-colors"
            >
              <StopIcon />
              Stop opname
            </button>
          </>
        )}

        {/* PAUSED: Hervat + Stop */}
        {state === "paused" && (
          <>
            <button
              onClick={resume}
              className="flex items-center gap-2 px-5 py-3 bg-red-600 text-white rounded-full font-medium hover:bg-red-700 transition-colors"
            >
              <MicIcon />
              Hervat
            </button>
            <button
              onClick={stop}
              className="flex items-center gap-2 px-5 py-3 bg-gray-800 text-white rounded-full font-medium hover:bg-gray-900 transition-colors"
            >
              <StopIcon />
              Stop opname
            </button>
          </>
        )}

        {/* STOPPED: Verwerk + Opnieuw */}
        {state === "stopped" && (
          <>
            <button
              onClick={handleUpload}
              disabled={uploading || !audioBlob}
              className="flex items-center gap-2 px-8 py-4 bg-primary-600 text-white rounded-full font-medium text-lg hover:bg-primary-700 transition-colors shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {uploading ? (
                <>
                  <span className="animate-spin w-5 h-5 border-2 border-white border-t-transparent rounded-full" />
                  Verwerken...
                </>
              ) : (
                <>
                  <SendIcon />
                  Start SOEP-verwerking
                </>
              )}
            </button>
            <button
              onClick={reset}
              disabled={uploading}
              className="flex items-center gap-2 px-5 py-3 bg-gray-100 text-gray-700 rounded-full font-medium hover:bg-gray-200 transition-colors disabled:opacity-50"
            >
              <RetryIcon />
              Opnieuw
            </button>
          </>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="mt-4 p-3 bg-danger-50 text-danger-600 text-sm rounded-lg">
          {error}
        </div>
      )}

      {/* Privacy notice */}
      <p className="mt-6 text-xs text-gray-400 text-center">
        Audio wordt volledig lokaal verwerkt en automatisch verwijderd na
        goedkeuring van het transcript.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Icons (inline SVG — geen externe dependency)
// ---------------------------------------------------------------------------
function MicIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 10v2a7 7 0 01-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <rect x="6" y="4" width="4" height="16" rx="1" />
      <rect x="14" y="4" width="4" height="16" rx="1" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
      <rect x="4" y="4" width="16" height="16" rx="2" />
    </svg>
  );
}

function SendIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M13 7l5 5m0 0l-5 5m5-5H6" />
    </svg>
  );
}

function RetryIcon() {
  return (
    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
    </svg>
  );
}
