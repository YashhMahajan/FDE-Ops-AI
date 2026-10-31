// Render docs/images/*.svg to PNG at 2x with Chromium (light theme, white background).
// Usage: node scripts/render_diagrams.mjs
import { readdirSync, readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dir = join(root, "docs", "images");
// Playwright comes from the global install, or from web/node_modules (pnpm install in web/).
let chromium;
try {
  ({ chromium } = createRequire(import.meta.url)("playwright"));
} catch {
  ({ chromium } = createRequire(join(root, "web", "package.json"))("playwright"));
}
const browser = await chromium.launch();
for (const file of readdirSync(dir).filter((f) => f.endsWith(".svg"))) {
  const svg = readFileSync(join(dir, file), "utf8");
  const [, w, h] = svg.match(/viewBox="0 0 (\d+) (\d+)"/);
  const page = await browser.newPage({ viewport: { width: +w, height: +h }, deviceScaleFactor: 2 });
  await page.setContent(`<html><body style="margin:0;background:#fff">${svg}</body></html>`);
  await page.screenshot({ path: join(dir, file.replace(".svg", ".png")), omitBackground: false });
  await page.close();
  console.log(`wrote docs/images/${file.replace(".svg", ".png")}`);
}
await browser.close();
