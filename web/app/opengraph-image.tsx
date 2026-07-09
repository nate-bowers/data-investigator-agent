import { ImageResponse } from "next/og";

// Social card generated at build/request time — system fonts only, no network
// fetches. Brand palette: paper, ink, teal accent, amber.
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px 80px",
          background: "#f4f2ec",
          color: "#22201b",
          fontFamily: "monospace",
        }}
      >
        {/* subtle trace motif across the top */}
        <svg width="1040" height="90" viewBox="0 0 1040 90" style={{ opacity: 0.35 }}>
          <path
            d="M0 60 L120 60 L170 20 L220 78 L270 44 L320 58 L360 60 L620 60 L680 24 L740 82 L790 40 L840 60 L1040 60"
            fill="none"
            stroke="#0d7a8a"
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>

        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              fontSize: 26,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "#b8460f",
            }}
          >
            {/* magnifying glass mark */}
            <svg width="34" height="34" viewBox="0 0 32 32" style={{ marginRight: 16 }}>
              <circle cx="14.5" cy="15.5" r="7" fill="none" stroke="#0d7a8a" strokeWidth="2.4" />
              <line x1="19.6" y1="20.6" x2="26" y2="27" stroke="#0d7a8a" strokeWidth="2.8" strokeLinecap="round" />
            </svg>
            Autonomous agent
          </div>
          <div style={{ fontSize: 92, fontWeight: 700, letterSpacing: "-0.02em", marginTop: 18 }}>
            Data Investigator
          </div>
          <div style={{ fontSize: 34, lineHeight: 1.4, color: "#4a463d", marginTop: 24, maxWidth: 900 }}>
            An autonomous data-analysis agent that investigates a dataset one question at a time
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", fontSize: 24, color: "#8f897c" }}>
          <div style={{ display: "flex", width: 14, height: 14, borderRadius: 7, background: "#0d7a8a", marginRight: 14 }} />
          writes and runs its own pandas · reads each result · self-corrects · stops when it has the answer
        </div>
      </div>
    ),
    size,
  );
}
