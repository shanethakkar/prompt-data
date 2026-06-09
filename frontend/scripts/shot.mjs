import { chromium } from "@playwright/test";
import fs from "node:fs";

const url = "http://localhost:3000";
const out = "shots";
fs.mkdirSync(out, { recursive: true });

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });

await page.goto(url, { waitUntil: "networkidle" });
await page.screenshot({ path: `${out}/hero.png` });
console.log("hero captured");

await page.getByLabel("Ask a question").fill("How many orders were delivered?");
await page.keyboard.press("Enter");
await page.waitForSelector("text=Generated SQL", { timeout: 90000 });
await page.waitForTimeout(700);
await page.screenshot({ path: `${out}/answer.png`, fullPage: true });
console.log("answer captured");

await page.goto(url, { waitUntil: "networkidle" });
await page.getByLabel("Ask a question").fill("Who are the top sellers?");
await page.keyboard.press("Enter");
await page.waitForSelector("text=Clarifying first", { timeout: 90000 });
await page.waitForTimeout(500);
await page.screenshot({ path: `${out}/clarify.png`, fullPage: true });
console.log("clarify captured");

await browser.close();
console.log("done");
