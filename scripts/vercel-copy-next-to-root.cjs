/**
 * Vercel runs the Next.js builder from the repo root and expects `.next` there.
 * Workspace builds emit `frontend/.next` — copy it up after `next build`.
 */
const fs = require("fs");
const path = require("path");

const root = process.cwd();
const src = path.join(root, "frontend", ".next");
const dest = path.join(root, ".next");

if (!fs.existsSync(src)) {
  console.error("Expected Next.js output at frontend/.next (run next build in frontend).");
  process.exit(1);
}
fs.rmSync(dest, { recursive: true, force: true });
fs.cpSync(src, dest, { recursive: true });
console.log("Synced frontend/.next -> .next for Vercel.");
