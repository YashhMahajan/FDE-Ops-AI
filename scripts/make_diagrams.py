"""Make the diagrams of the README as SVG files (light theme). Standard library only.

Each number in a figure comes from a record of this repository: the flagship demo
(`fdeops demo`, label pipeline-test) or the example agents (label measured-in-simulation).
Render the PNG files with `node scripts/render_diagrams.mjs`.

Usage: python3 scripts/make_diagrams.py
"""

from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(__file__).resolve().parents[1] / "docs" / "images"

INK, MUTED, LINE, SURF = "#111827", "#4b5563", "#cbd5e1", "#f8fafc"
BLUE, BLUE_L = "#1d4ed8", "#dbeafe"
GREEN, GREEN_L = "#15803d", "#dcfce7"
RED, RED_L = "#b91c1c", "#fee2e2"
AMBER, AMBER_L = "#b45309", "#fef3c7"
GREY, GREY_L = "#6b7280", "#e5e7eb"
FONT = "Inter, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "'JetBrains Mono', 'DejaVu Sans Mono', Menlo, Consolas, monospace"


def t(x, y, s, size=16, weight=400, fill=INK, anchor="start", mono=False):
    family = MONO if mono else FONT
    return (
        f'<text x="{x}" y="{y}" font-family="{family}" font-size="{size}" '
        f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>'
    )


def box(x, y, w, h, fill=SURF, stroke=LINE, r=12, sw=1.5, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="{sw}"{d}/>'
    )


def line(points, color=INK, sw=2, dash=None, arrow=True):
    pts = " ".join(f"{x},{y}" for x, y in points)
    d = f' stroke-dasharray="{dash}"' if dash else ""
    m = f' marker-end="url(#arrow-{_name(color)})"' if arrow else ""
    return (
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{sw}" '
        f'stroke-linejoin="round" stroke-linecap="round"{d}{m}/>'
    )


def _name(color):
    return {INK: "ink", BLUE: "blue", GREEN: "green", RED: "red", GREY: "grey", MUTED: "ink"}.get(
        color, "ink"
    )


def defs():
    marks = ""
    for name, color in (("ink", INK), ("blue", BLUE), ("green", GREEN), ("red", RED), ("grey", GREY)):
        marks += (
            f'<marker id="arrow-{name}" viewBox="0 0 10 10" refX="8.5" refY="5" '
            f'markerWidth="9" markerHeight="9" orient="auto-start-reverse">'
            f'<path d="M1,1 L9,5 L1,9 z" fill="{color}"/></marker>'
        )
    return f"<defs>{marks}</defs>"


def svg(name, w, h, label, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'role="img" aria-label="{escape(label)}">\n<title>{escape(label)}</title>\n{defs()}\n'
        f'<rect width="{w}" height="{h}" fill="#ffffff"/>\n{body}\n</svg>\n'
    )


def heading(title, sub):
    return t(40, 52, title, 28, 700) + t(40, 82, sub, 17, 400, MUTED)


# ---------------------------------------------------------------------------- figure 1
def closed_loop():
    cards = [
        ("Monitor", ["Reads live signals.", "It needs no", "answer key."], "1 ticket", "to the first alarm", "(about 4 minutes)", BLUE),
        ("Evaluate", ["Replays the cases.", "The oracle scores", "each one."], "−10.1 pts", "success change", "95% CI −17.4 to −4.3", RED),
        ("Diagnose", ["Tests the cause", "with a replay and", "a changed setting."], "7 of 7", "cases fixed", "0 of 20 controls hurt", GREEN),
        ("Fix", ["The improvement", "loop picks a change", "on the dev split."], "+10.1 pts", "on the test split", "CI +4.3 to +17.4", GREEN),
        ("Gate", ["Uses confidence", "limits, not point", "estimates."], "8 of 8", "release gates", "passed", GREEN),
        ("Approve", ["A person decides.", "Rollback is", "one command."], "1 person", "with the", "approver role", INK),
    ]
    x0, w, gap, y, h = 40, 170, 20, 116, 240
    b = heading(
        "One loop, from the first alarm to an approved fix",
        "Each step ends in a number. Incident: the refund window drifts after a policy change.",
    )
    for i, (title, desc, big, sub1, sub2, color) in enumerate(cards):
        x = x0 + i * (w + gap)
        b += box(x, y, w, h, "#ffffff", LINE, 14, 1.5)
        b += f'<rect x="{x}" y="{y}" width="{w}" height="6" rx="3" fill="{color}"/>'
        b += t(x + 16, y + 42, title, 23, 700)
        for j, ln in enumerate(desc):
            b += t(x + 16, y + 70 + j * 21, ln, 14.5, 400, MUTED)
        b += f'<line x1="{x + 16}" y1="{y + 142}" x2="{x + w - 16}" y2="{y + 142}" stroke="{LINE}"/>'
        b += t(x + 16, y + 184, big, 28, 700, color)
        b += t(x + 16, y + 208, sub1, 13.5, 400, MUTED)
        b += t(x + 16, y + 226, sub2, 13.5, 400, MUTED)
        if i < len(cards) - 1:
            b += line([(x + w + 3, y + h / 2), (x + w + gap - 3, y + h / 2)], INK, 2)
    # return path: the fixed release goes back to production, and the monitor watches it again
    last = x0 + 5 * (w + gap) + w / 2
    first = x0 + w / 2
    b += line([(last, y + h + 4), (last, y + h + 40), (first, y + h + 40), (first, y + h + 6)], BLUE, 2.5, "7 6")
    b += t((first + last) / 2, y + h + 68, "v2 runs in production. The monitor watches it again: 0 alerts.", 16, 600, BLUE, "middle")
    b += t(40, 450, "Source: flagship demo (fdeops demo), fictional tenant Ledgerloop, stand-in model. Label: pipeline-test.", 13.5, 400, GREY)
    return svg("closed-loop", 1200, 474, "The closed loop: monitor, evaluate, diagnose, fix, gate, approve, then monitor again", b)


# ---------------------------------------------------------------------------- figure 2
def architecture():
    b = heading(
        "Your agent's tool calls pass the same checks as ours",
        "The oracle decides what was correct. A model never writes the answer key.",
    )
    # row A
    b += box(40, 130, 200, 140, BLUE_L, BLUE, 14, 2)
    b += t(140, 176, "Your agent", 22, 700, INK, "middle")
    b += t(140, 204, "Any framework,", 15.5, 400, MUTED, "middle")
    b += t(140, 226, "any model, or the", 15.5, 400, MUTED, "middle")
    b += t(140, 248, "reference agent", 15.5, 400, MUTED, "middle")
    b += line([(244, 200), (326, 200)], BLUE, 2.5)
    b += t(285, 186, "tool call", 14.5, 600, BLUE, "middle")

    b += box(330, 110, 350, 270, "#ffffff", LINE, 14, 1.5)
    b += t(352, 142, "Connector stack", 20, 700)
    rows = [
        ("Permission guard", "checks the scopes"),
        ("Policy monitor", "flags each violation"),
        ("Resilience", "retry, breaker, idempotency key"),
        ("Fault injection", "timeouts, bad data, outages"),
        ("Audit log", "hash chain, tamper evident"),
    ]
    for i, (name, what) in enumerate(rows):
        y = 158 + i * 42
        b += box(348, y, 314, 36, SURF, LINE, 8, 1)
        b += t(360, y + 23, name, 15.5, 650)
        b += t(652, y + 23, what, 13.5, 400, MUTED, "end")
    b += line([(684, 245), (766, 245)], INK, 2.5)
    b += t(725, 231, "API call", 14.5, 600, INK, "middle")

    b += box(770, 110, 390, 270, "#ffffff", LINE, 14, 1.5)
    b += t(792, 142, "Tenant world (simulated)", 20, 700)
    for i, (name, what) in enumerate(
        [
            ("Business APIs and data", "customers, invoices, shipments"),
            ("Knowledge base", "each version has a date"),
            ("Incidents", "drift, outage, dirty data"),
        ]
    ):
        y = 160 + i * 68
        b += box(788, y, 354, 56, SURF, LINE, 8, 1)
        b += t(802, y + 25, name, 15.5, 650)
        b += t(802, y + 45, what, 13.5, 400, MUTED)

    # row B
    steps = [
        ("Oracle", "policy + state give the", "correct end state"),
        ("Evaluators", "end state, trace,", "and policy flags"),
        ("Statistics", "95% intervals, paired", "tests, pass^k"),
        ("Gates and reports", "release or reject,", "with the reason"),
    ]
    for i, (name, a, c) in enumerate(steps):
        x = 40 + i * 290
        b += box(x, 450, 260, 100, GREEN_L if i == 0 else "#ffffff", GREEN if i == 0 else LINE, 14, 2 if i == 0 else 1.5)
        b += t(x + 18, 484, name, 20, 700)
        b += t(x + 18, 512, a, 15, 400, MUTED)
        b += t(x + 18, 532, c, 15, 400, MUTED)
        if i < 3:
            b += line([(x + 264, 500), (x + 286, 500)], INK, 2.5)
    b += line([(965, 384), (965, 418), (460, 418), (460, 446)], INK, 2.5)
    b += t(712, 410, "end state and trace", 14.5, 600, INK, "middle")
    b += box(60, 398, 220, 34, SURF, LINE, 8, 1)
    b += t(170, 420, "policy.yaml of the tenant", 13.5, 600, MUTED, "middle")
    b += line([(170, 434), (170, 446)], GREEN, 2.5)
    b += t(40, 598, "The tenant files (policy, knowledge base, gates, monitors) hold all customer rules. Platform code names no tenant.", 13.5, 400, GREY)
    return svg("architecture", 1200, 622, "Your agent calls tools through a connector stack into a simulated tenant world. An oracle, evaluators, statistics and gates judge the result.", b)


# ---------------------------------------------------------------------------- figure 3
def diagnosis():
    b = heading(
        "A cause is confirmed only when the fix works and breaks nothing",
        "The platform replays the failing cases with one change at a time, and it replays control cases too.",
    )
    b += box(40, 150, 270, 190, RED_L, RED, 14, 2)
    b += t(60, 188, "Failing cluster", 21, 700)
    b += t(60, 218, "stale_knowledge", 15.5, 650, RED, mono=True)
    b += t(60, 242, "on refund_outside_window", 14, 400, MUTED, mono=True)
    b += t(60, 278, "7 trials, 7 cases", 16, 600)
    b += t(60, 304, "The agent got the superseded", 14.5, 400, MUTED)
    b += t(60, 324, "section refund-policy@v1.", 14.5, 400, MUTED)

    ivs = [
        ("freshness_filter", "Drop superseded sections"),
        ("current_index_only", "Index only the current version"),
        ("oracle_retrieval", "Give the correct section (upper bound)"),
    ]
    ys = [128, 218, 308]
    for (name, what), y in zip(ivs, ys, strict=True):
        b += line([(314, 245), (372, y + 36)], GREY, 1.8)
        b += box(376, y, 400, 74, "#ffffff", LINE, 12, 1.5)
        b += t(394, y + 32, name, 16, 650, BLUE, mono=True)
        b += t(394, y + 56, what, 14.5, 400, MUTED)
        b += line([(780, y + 37), (812, y + 37)], INK, 2)
        b += box(816, y + 8, 150, 58, GREEN_L, GREEN, 10, 1.5)
        b += t(891, y + 33, "7 of 7", 20, 700, GREEN, "middle")
        b += t(891, y + 54, "cluster cases fixed", 12.5, 400, MUTED, "middle")
        b += box(978, y + 8, 182, 58, GREEN_L, GREEN, 10, 1.5)
        b += t(1069, y + 33, "0 of 20", 20, 700, GREEN, "middle")
        b += t(1069, y + 54, "control cases broken", 12.5, 400, MUTED, "middle")
    b += t(891, 114, "Does it fix the cluster?", 14.5, 600, INK, "middle")
    b += t(1069, 114, "Does it break a control?", 14.5, 600, INK, "middle")

    b += box(376, 416, 784, 96, "#ffffff", GREEN, 14, 2.5)
    b += f'<rect x="376" y="416" width="8" height="96" rx="4" fill="{GREEN}"/>'
    b += t(404, 452, "Verdict: confirmed by intervention", 22, 700, GREEN)
    b += t(404, 480, "Rule: the change fixes the cluster and breaks no control case.", 15.5, 400, MUTED)
    b += t(404, 500, "If it fixes the cluster but breaks a control, the verdict is supported. If it does not fix, inconclusive.", 14, 400, MUTED)
    b += line([(891, 386), (891, 400), (1069, 400), (1069, 386)], GREEN, 2, None, False)
    b += line([(980, 400), (980, 412)], GREEN, 2.5)
    b += t(40, 560, "Source: flagship demo, fictional tenant Ledgerloop, stand-in model. Label: pipeline-test.", 13.5, 400, GREY)
    return svg("diagnosis", 1200, 584, "A failing cluster is replayed with three interventions. The cause is confirmed only when the cluster is fixed and no control case breaks.", b)


# ---------------------------------------------------------------------------- figure 4
def gates():
    b = heading(
        "A release moves only through gates, then a person",
        "Gates use confidence limits. A gate that the platform cannot measure fails.",
    )
    b += box(40, 150, 250, 210, "#ffffff", LINE, 14, 1.5)
    b += t(60, 188, "Release bundle", 21, 700)
    for i, s in enumerate(["model", "prompt", "retrieval settings", "tools", "knowledge base", "dataset"]):
        b += t(60, 218 + i * 22, "+ " + s if i else s, 15, 400, MUTED)
    b += t(60, 352, "one hash: sha256:…", 14, 600, BLUE, mono=True)
    b += line([(294, 255), (338, 255)], INK, 2.5)

    gates_list = [
        ("Task success", "95% lower limit ≥ 85%"),
        ("Critical violations", "0 trials, upper limit ≤ 6%"),
        ("Non-inferiority", "no slice worse by > 3 pts"),
        ("Latency", "p95 ≤ 8 s"),
        ("Cost", "≤ $0.05 for each resolution"),
        ("Integration suite", "faults, no double refund"),
        ("Regression suite", "each past incident passes"),
        ("Judge calibration", "agreement kappa ≥ 0.6"),
    ]
    b += box(342, 118, 520, 290, SURF, LINE, 14, 1.5)
    b += t(362, 148, "8 gates, from tenants/ledgerloop/gates.yaml", 16, 650)
    for i, (name, rule) in enumerate(gates_list):
        col, row = divmod(i, 4)
        x, y = 358 + col * 248, 166 + row * 58
        b += box(x, y, 238, 50, "#ffffff", LINE, 8, 1)
        b += f'<circle cx="{x + 20}" cy="{y + 25}" r="7" fill="{GREEN}"/>'
        b += t(x + 36, y + 22, name, 14.5, 650)
        b += t(x + 36, y + 40, rule, 12.5, 400, MUTED)
    b += line([(866, 255), (910, 255)], INK, 2.5)

    b += box(914, 150, 246, 100, GREEN_L, GREEN, 14, 2)
    b += t(934, 186, "Approval", 21, 700)
    b += t(934, 212, "A person with the", 14.5, 400, MUTED)
    b += t(934, 232, "approver role signs.", 14.5, 400, MUTED)
    b += line([(1037, 254), (1037, 292)], GREEN, 2.5)
    b += box(914, 296, 246, 100, "#ffffff", LINE, 14, 1.5)
    b += t(934, 332, "Production pointer", 19, 700)
    b += t(934, 358, "moves to v2, and the", 14.5, 400, MUTED)
    b += t(934, 378, "incident joins the suite.", 14.5, 400, MUTED)
    b += line([(1037, 430), (1037, 400)], RED, 2.2, "7 6")
    b += t(1050, 420, "if a release fails", 13, 600, RED)
    b += box(914, 432, 246, 56, RED_L, RED, 12, 1.5)
    b += t(934, 456, "Rollback", 16.5, 700, RED)
    b += t(934, 476, "one command, back to v1", 13.5, 400, MUTED)
    b += t(40, 530, "Source: Ledgerloop gate file. The flagship demo passed 8 of 8 gates for v2 (stand-in model, label: pipeline-test).", 13.5, 400, GREY)
    return svg("gates", 1200, 556, "A release bundle goes through eight gates and a person's approval before the production pointer moves; rollback is one command.", b)


# ---------------------------------------------------------------------------- figure 5
def whisker_panel(x0, y0, w, title, sub, rows, scale_max=100.0):
    """A dot-and-whisker chart: success rate with its 95% interval. rows = (label, v, lo, hi, color)."""
    label_w = 190
    left, right = x0 + label_w, x0 + w - 70
    out = t(x0, y0, title, 19, 700) + t(x0, y0 + 24, sub, 14, 400, MUTED)
    top = y0 + 56
    n = len(rows)
    row_h = 54
    for tick in (0, 25, 50, 75, 100):
        x = left + (right - left) * tick / scale_max
        out += f'<line x1="{x}" y1="{top - 10}" x2="{x}" y2="{top + n * row_h}" stroke="{GREY_L}" stroke-width="1"/>'
        out += t(x, top + n * row_h + 22, f"{tick}%", 13, 400, GREY, "middle")
    for i, (label, v, lo, hi, color) in enumerate(rows):
        cy = top + i * row_h + row_h / 2 - 6
        sx = lambda p: left + (right - left) * p / scale_max  # noqa: E731
        out += t(x0, cy + 5, label, 15, 500)
        out += f'<line x1="{sx(lo)}" y1="{cy}" x2="{sx(hi)}" y2="{cy}" stroke="{color}" stroke-width="3.5" stroke-linecap="round"/>'
        out += f'<circle cx="{sx(v)}" cy="{cy}" r="8" fill="{color}" stroke="#ffffff" stroke-width="2"/>'
        out += t(right + 12, cy + 5, f"{v:.1f}%", 15, 700, color)
    return out


def results():
    b = heading(
        "Numbers, not adjectives: success with its 95% interval",
        "A dot is the measured rate. A line is the 95% confidence interval. The number of cases limits the width.",
    )
    b += box(40, 112, 560, 372, "#ffffff", LINE, 14, 1.5)
    b += whisker_panel(
        62, 146, 520, "Incident and fix", "Ledgerloop test split, 69 cases, stand-in model",
        [
            ("v1 before the incident", 100.0, 94.7, 100.0, GREEN),
            ("v1 during the incident", 89.9, 80.5, 95.0, RED),
            ("v2 with the fix", 100.0, 94.7, 100.0, GREEN),
            ("FAQ baseline, no LLM", 47.8, 36.5, 59.4, GREY),
        ],
    )
    b += t(62, 466, "Paired change during the incident: −10.1 pts (95% CI −17.4 to −4.3), p = 0.016", 13.5, 400, MUTED)
    b += box(620, 112, 540, 372, "#ffffff", LINE, 14, 1.5)
    b += whisker_panel(
        642, 146, 500, "Your agent against a naive agent", "Ledgerloop dev split, 51 cases, example agents",
        [
            ("naive_refunder.py", 21.6, 12.5, 34.6, RED),
            ("careful_refunder.py", 78.4, 65.4, 87.5, GREEN),
        ],
    )
    b += box(642, 352, 250, 78, RED_L, RED, 12, 1.5)
    b += t(767, 388, "33 of 51", 27, 700, RED, "middle")
    b += t(767, 413, "trials with a critical violation", 13, 400, MUTED, "middle")
    b += box(910, 352, 232, 78, GREEN_L, GREEN, 12, 1.5)
    b += t(1026, 388, "0 of 51", 27, 700, GREEN, "middle")
    b += t(1026, 413, "trials with a critical violation", 13, 400, MUTED, "middle")
    b += t(642, 454, "Paired change: +56.9 pts (95% CI +43.1 to +70.6).", 13.5, 400, MUTED)
    b += t(642, 474, "Better in 29 cases. Worse in 0 cases.", 13.5, 400, MUTED)
    b += t(40, 514, "Left: label pipeline-test (stand-in model). Right: label measured-in-simulation (rule-based example agents). The careful agent does refunds only.", 13.5, 400, GREY)
    return svg("results", 1200, 538, "Success rates with 95% confidence intervals for the incident demo and for two example agents.", b)


# ---------------------------------------------------------------------------- figure 6
def monitor():
    b = heading(
        "The monitor sees the drift without an answer key",
        "Live deployments have no oracle. The monitor uses signals that the platform can see in each ticket.",
    )
    left, right, axis_y = 90, 1110, 250
    scale = (right - left) / 60
    b += f'<line x1="{left}" y1="{axis_y}" x2="{right}" y2="{axis_y}" stroke="{INK}" stroke-width="2"/>'
    for tick in range(0, 61, 10):
        x = left + tick * scale
        b += f'<line x1="{x}" y1="{axis_y}" x2="{x}" y2="{axis_y + 8}" stroke="{INK}" stroke-width="2"/>'
        b += t(x, axis_y + 30, str(tick), 14, 400, MUTED, "middle")
    b += t((left + right) / 2, axis_y + 56, "tickets after the incident starts (13.3 tickets each hour)", 14.5, 600, MUTED, "middle")

    alarms = [
        (1, "stale_context", "after 1 ticket", "about 4 minutes", "severity: ticket", BLUE, 112, "start"),
        (48, "policy_flag", "after 48 tickets", "about 3.6 hours", "severity: page", AMBER, 112, "end"),
        (50, "critical_flag", "after 50 tickets", "about 3.8 hours", "severity: page", RED, 190, "start"),
    ]
    for tk, name, a, c, sev, color, ty, anchor in alarms:
        x = left + tk * scale
        b += f'<line x1="{x}" y1="{axis_y}" x2="{x}" y2="{ty + 74}" stroke="{color}" stroke-width="2" stroke-dasharray="5 4"/>'
        b += f'<circle cx="{x}" cy="{axis_y}" r="9" fill="{color}" stroke="#ffffff" stroke-width="2.5"/>'
        tx = x + 14 if anchor == "start" else x - 14
        b += t(tx, ty, name, 17, 700, color, anchor, mono=True)
        b += t(tx, ty + 24, a, 15.5, 650, INK, anchor)
        b += t(tx, ty + 44, c + ", " + sev, 14, 400, MUTED, anchor)

    b += box(40, 346, 1120, 150, SURF, LINE, 14, 1.5)
    b += t(60, 380, "Signal rate: reference window against incident window", 17, 700)
    rows = [("stale_context", "0.0%", "84.1%"), ("policy_flag", "0.0%", "10.1%"), ("critical_flag", "0.0%", "10.1%")]
    for i, (name, ref, inc) in enumerate(rows):
        x = 60 + i * 370
        b += t(x, 416, name, 15, 650, INK, mono=True)
        b += t(x, 448, ref, 23, 700, GREY)
        b += line([(x + 78, 441), (x + 118, 441)], INK, 2)
        b += t(x + 128, 448, inc, 23, 700, RED)
    b += t(60, 482, "An alert needs the whole 95% interval of the change to be above the tolerance. The monitor saw 7 of 7 failed trials. 0 were silent.", 13.5, 400, MUTED)
    b += t(40, 532, "Source: flagship demo, fictional tenant Ledgerloop, stand-in model. Label: pipeline-test.", 13.5, 400, GREY)
    return svg("monitor", 1200, 556, "Three monitor alarms on a timeline of tickets: the stale context alarm comes after one ticket, the page-level alarms after about fifty tickets.", b)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    figures = {
        "closed-loop": closed_loop(),
        "architecture": architecture(),
        "diagnosis": diagnosis(),
        "gates": gates(),
        "results": results(),
        "monitor": monitor(),
    }
    for name, text in figures.items():
        (OUT / f"{name}.svg").write_text(text, encoding="utf-8")
        print(f"wrote docs/images/{name}.svg")


if __name__ == "__main__":
    main()
