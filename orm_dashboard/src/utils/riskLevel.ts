// D3: single source of truth for risk severity bands, matching
// orm_collection/app/core/risk_config.py's RISK_THRESHOLDS and
// risk_engine.py's get_risk_level() exactly. At least 4 different band
// definitions previously existed independently across the frontend (e.g.
// >=20/>=50/>=80, >=45/>=75), none matching the backend's <=25/<=50/<=75,
// causing confirmed live mislabeling of events. Every component computing a
// LOW/MEDIUM/HIGH/CRITICAL risk severity label should use this instead of a
// locally-defined threshold.
export const RISK_THRESHOLDS = {
  LOW_TO_MEDIUM: 25,
  MEDIUM_TO_HIGH: 50,
  HIGH_TO_CRITICAL: 75,
} as const;

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export function getRiskLevel(score: number): RiskLevel {
  const s = score ?? 0;
  if (s <= RISK_THRESHOLDS.LOW_TO_MEDIUM) return "LOW";
  if (s <= RISK_THRESHOLDS.MEDIUM_TO_HIGH) return "MEDIUM";
  if (s <= RISK_THRESHOLDS.HIGH_TO_CRITICAL) return "HIGH";
  return "CRITICAL";
}
