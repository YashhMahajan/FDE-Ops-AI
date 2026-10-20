"use client";

import { useEffect, useState } from "react";
import type { GateResult } from "@/lib/types";
import { label } from "@/lib/format";

const STATE_TEXT: Record<GateResult["status"], string> = {
  pass: "pass",
  fail: "fail",
  not_measured: "not measured",
  not_applicable: "n / a",
};

/**
 * Release gates as a cockpit annunciator panel. On mount it does a short "lamp test": every lamp
 * lights white, then each lamp settles to its real state, the way a crew checks the panel.
 */
export function Annunciator({
  gates,
  selected,
  onSelect,
  stateText = STATE_TEXT,
  ariaLabel = "Release gates",
}: {
  gates: GateResult[];
  selected?: string | null;
  onSelect?: (gate: string) => void;
  stateText?: Record<GateResult["status"], string>;
  ariaLabel?: string;
}) {
  const [lampTest, setLampTest] = useState(true);
  const key = gates.map((g) => `${g.gate}:${g.status}`).join("|");
  useEffect(() => {
    setLampTest(true);
    const t = window.setTimeout(() => setLampTest(false), 420);
    return () => window.clearTimeout(t);
  }, [key]);
  return (
    <div className="annunciator" data-lamp-test={lampTest} role="list" aria-label={ariaLabel}>
      {gates.map((g) => (
        <div key={g.gate} role="listitem" className="lamp-cell">
          <button
            type="button"
            className="lamp"
            data-state={g.status}
            aria-pressed={selected === g.gate}
            onClick={() => onSelect?.(g.gate)}
            title={g.why}
          >
            <span className="lamp-face">{label(g.gate)}</span>
            <span className="lamp-state">{stateText[g.status]}</span>
            <span className="lamp-detail">{g.observed}</span>
          </button>
        </div>
      ))}
    </div>
  );
}
