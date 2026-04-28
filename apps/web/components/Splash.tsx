"use client";

/**
 * Splash · "ESTABLISHING GEOFENCE…" intro shown once per browser session.
 *
 * Mounted in the root layout. Auto-dismisses after 1.8s; sets a sessionStorage
 * flag so subsequent navigations within the tab skip it. Clicking anywhere
 * dismisses immediately.
 */
import { useEffect, useState } from "react";

const STORAGE_KEY = "reliefops:splash-seen";

export function Splash() {
  const [visible, setVisible] = useState(false);
  const [fadingOut, setFadingOut] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (sessionStorage.getItem(STORAGE_KEY) === "1") return;
    setVisible(true);
    sessionStorage.setItem(STORAGE_KEY, "1");
    const fadeTimer = window.setTimeout(() => setFadingOut(true), 1500);
    const hideTimer = window.setTimeout(() => setVisible(false), 2100);
    return () => {
      window.clearTimeout(fadeTimer);
      window.clearTimeout(hideTimer);
    };
  }, []);

  if (!visible) return null;

  return (
    <div
      role="presentation"
      onClick={() => setFadingOut(true)}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 9999,
        background: "#0b1120",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        opacity: fadingOut ? 0 : 1,
        transition: "opacity 600ms ease-out",
        pointerEvents: fadingOut ? "none" : "auto",
        cursor: "pointer",
      }}
    >
      <style>{`
        @keyframes splash-pulse {
          0%   { transform: scale(1);   opacity: 1;   }
          70%  { transform: scale(2.4); opacity: 0;   }
          100% { transform: scale(2.4); opacity: 0;   }
        }
        @keyframes splash-spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        @keyframes splash-bar {
          0%   { width: 0%; }
          100% { width: 100%; }
        }
      `}</style>

      {/* Center logo with two pulse rings + dashed orbit */}
      <div style={{ position: "relative", width: 160, height: 160, marginBottom: 32 }}>
        {/* Dashed rotating outer ring */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            borderRadius: "9999px",
            border: "2px dashed #10b981",
            opacity: 0.55,
            animation: "splash-spin 7s linear infinite",
          }}
        />
        {/* Inner pulse rings */}
        <div
          style={{
            position: "absolute",
            inset: "32%",
            borderRadius: "9999px",
            background: "#3b82f6",
            opacity: 0.35,
            animation: "splash-pulse 1.6s ease-out infinite",
          }}
        />
        <div
          style={{
            position: "absolute",
            inset: "32%",
            borderRadius: "9999px",
            background: "#3b82f6",
            opacity: 0.35,
            animation: "splash-pulse 1.6s ease-out infinite",
            animationDelay: "0.8s",
          }}
        />
        {/* Solid core */}
        <div
          style={{
            position: "absolute",
            inset: "44%",
            borderRadius: "9999px",
            background: "#60a5fa",
            boxShadow: "0 0 28px #3b82f6, 0 0 60px #3b82f6",
          }}
        />
      </div>

      {/* Wordmark */}
      <div
        style={{
          fontFamily: "Inter, system-ui, sans-serif",
          fontWeight: 800,
          fontSize: 28,
          letterSpacing: "0.32em",
          color: "white",
          marginBottom: 16,
        }}
      >
        RELIEF<span style={{ color: "#3b82f6" }}>OPS</span>
      </div>

      {/* Subtitle + indeterminate bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11,
          letterSpacing: "0.18em",
          color: "#94a3b8",
          textTransform: "uppercase",
        }}
      >
        <span
          style={{
            display: "inline-block",
            width: 8,
            height: 14,
            background: "#10b981",
            boxShadow: "0 0 6px #10b981",
          }}
        />
        Establishing geofence…
      </div>

      {/* Loading bar */}
      <div
        style={{
          marginTop: 22,
          width: 220,
          height: 2,
          background: "rgba(148,163,184,0.15)",
          borderRadius: 999,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            background: "linear-gradient(90deg, #10b981, #3b82f6)",
            animation: "splash-bar 1.5s ease-out forwards",
          }}
        />
      </div>
    </div>
  );
}
