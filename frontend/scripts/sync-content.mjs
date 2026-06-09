// Copies the committed eval artifacts into frontend/content/ so the static pages can import
// them and the Vercel build (root = frontend/) is self-contained. Runs on predev/prebuild.
// The copies in content/ are committed; this only refreshes them when eval/out is present.
import fs from "node:fs";
import path from "node:path";

const src = path.resolve("..", "eval", "out");
const dest = path.resolve("content");
fs.mkdirSync(dest, { recursive: true });

const files = ["eval_results.json", "trap_results.json", "gallery.json"];
for (const f of files) {
  const from = path.join(src, f);
  if (fs.existsSync(from)) {
    fs.copyFileSync(from, path.join(dest, f));
    console.log(`synced ${f}`);
  } else {
    console.warn(`! ${from} not found; using committed content/${f}`);
  }
}
