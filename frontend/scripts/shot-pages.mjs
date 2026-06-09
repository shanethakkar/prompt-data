import { chromium } from "@playwright/test";
import fs from "node:fs";

const base = "http://localhost:3001";
const out = "shots";
fs.mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });

for (const route of ["evals", "gallery", "methodology", "limitations"]) {
  await page.goto(`${base}/${route}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${out}/${route}.png`, fullPage: true });
  console.log(`${route} captured`);
}
await browser.close();
console.log("done");
