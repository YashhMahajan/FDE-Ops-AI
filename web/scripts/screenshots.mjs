// Visual check in CI: screenshots of each page, for both tenants, in light, dark and mobile.
// Usage: node scripts/screenshots.mjs http://127.0.0.1:4173 ./screenshots
import { mkdirSync } from "node:fs";
import { chromium } from "playwright";

const [base = "http://127.0.0.1:4173", out = "screenshots"] = process.argv.slice(2);
mkdirSync(out, { recursive: true });

const pages = ["", "releases/", "monitor/", "runs/", "traces/", "diagnosis/", "roadmap/", "impact/"];
const variants = [
  { name: "ledgerloop-light", tenant: "ledgerloop", scheme: "light", viewport: { width: 1440, height: 1000 } },
  { name: "parcelpoint-dark", tenant: "parcelpoint", scheme: "dark", viewport: { width: 1440, height: 1000 } },
  { name: "ledgerloop-mobile", tenant: "ledgerloop", scheme: "light", viewport: { width: 390, height: 844 } },
];

const browser = await chromium.launch();
const errors = [];
for (const v of variants) {
  const ctx = await browser.newContext({ viewport: v.viewport, colorScheme: v.scheme, deviceScaleFactor: 1 });
  await ctx.addInitScript((t) => window.localStorage.setItem("fdeops.tenant", t), v.tenant);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(`${v.name}: ${e.message}`));
  page.on("console", (m) => m.type() === "error" && errors.push(`${v.name}: ${m.text()}`));
  for (const p of pages) {
    await page.goto(`${base}/${p}`, { waitUntil: "networkidle" });
    await page.waitForTimeout(700); // let the lamp test and the reveal finish
    const slug = p.replace(/\/$/, "") || "overview";
    await page.screenshot({ path: `${out}/${v.name}-${slug}.png`, fullPage: true });
    if (p === "traces/") {
      const row = page.locator("tr.row-button").first();
      if (await row.count()) {
        await row.click();
        await page.waitForTimeout(500);
        await page.screenshot({ path: `${out}/${v.name}-traces-drawer.png` });
        await page.keyboard.press("Escape");
      }
    }
  }
  await ctx.close();
}
await browser.close();
if (errors.length) {
  console.error(errors.join("\n"));
  process.exit(1);
}
console.log(`screenshots written to ${out}`);
