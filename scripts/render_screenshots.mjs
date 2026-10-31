// Screenshots of the web UI for the README (light theme, Ledgerloop demo data).
// Build the UI first: `uv run fdeops demo --tenant tenants/ledgerloop --export web/public/demo`
// (also for parcelpoint), then `cd web && pnpm install && pnpm build`.
// Usage: node scripts/render_screenshots.mjs [outDir]
import { spawn } from "node:child_process";
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const out = process.argv[2] ?? join(root, "docs", "images");
let chromium;
try {
  ({ chromium } = createRequire(import.meta.url)("playwright"));
} catch {
  ({ chromium } = createRequire(join(root, "web", "package.json"))("playwright"));
}
mkdirSync(out, { recursive: true });

const port = 4179;
const server = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1", "--directory", join(root, "web", "out")], { stdio: "ignore" });
await new Promise((r) => setTimeout(r, 1000));

const shots = [
  { page: "", name: "ui-overview" },
  { page: "monitor/", name: "ui-monitor" },
];
const browser = await chromium.launch();
try {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "light", deviceScaleFactor: 1.5 });
  await ctx.addInitScript(() => window.localStorage.setItem("fdeops.tenant", "ledgerloop"));
  const page = await ctx.newPage();
  for (const s of shots) {
    await page.goto(`http://127.0.0.1:${port}/${s.page}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(900); // the lamp test and the reveal finish
    await page.screenshot({ path: join(out, `${s.name}.png`) });
    console.log(`wrote ${s.name}.png`);
  }
} finally {
  await browser.close();
  server.kill();
}
