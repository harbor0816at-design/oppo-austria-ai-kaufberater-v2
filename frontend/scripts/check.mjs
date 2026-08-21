import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";

const files = [
  "src/app.js",
  "src/admin.js",
  "src/shared.js",
  "scripts/build.mjs",
  "scripts/check.mjs"
];

for (const file of files) {
  if (!existsSync(file)) {
    throw new Error(`Missing required file: ${file}`);
  }
  execFileSync(process.execPath, ["--check", file], { stdio: "inherit" });
}

for (const file of [
  "src/index.html",
  "src/admin.html",
  "src/styles.css",
  "src/assets/hero-brand.svg",
  "src/assets/hero-camera.svg",
  "src/assets/hero-vienna.svg"
]) {
  if (!existsSync(file)) {
    throw new Error(`Missing required file: ${file}`);
  }
}

console.log("Frontend syntax and required-file checks passed.");
