import { cpSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const dist = "dist";
rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

function copy(from, to) {
  mkdirSync(dirname(to), { recursive: true });
  cpSync(from, to, { recursive: true });
}

copy("src/assets", join(dist, "assets"));
copy("src/styles.css", join(dist, "styles.css"));
copy("src/admin.css", join(dist, "admin.css"));
copy("src/admin-conversations.css", join(dist, "admin-conversations.css"));
copy("src/shared.js", join(dist, "shared.js"));
copy("src/app.js", join(dist, "app.js"));
copy("src/admin.js", join(dist, "admin.js"));
copy("src/admin-conversations.js", join(dist, "admin-conversations.js"));
copy("src/index.html", join(dist, "index.html"));
copy("src/index.html", join(dist, "smartphone-finder", "index.html"));
copy("src/admin.html", join(dist, "admin", "index.html"));

const api = (
  process.env.ASSISTANT_API_BASE_URL
  || "https://oppo-austria-ai-kaufberater.vercel.app"
).replace(/\/$/, "");

writeFileSync(
  join(dist, "config.js"),
  `window.OPPO_CONFIG = ${JSON.stringify({ API_BASE_URL: api })};\n`
);

console.log(`Built static frontend in ${dist}`);
