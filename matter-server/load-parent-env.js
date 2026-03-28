/**
 * Preload with: node --import ./load-parent-env.js server.js
 * Loads repo-root `.env` (same file as the Python app) before `server.js` runs.
 */
import { config } from "dotenv";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const envPath = join(dirname(fileURLToPath(import.meta.url)), "..", ".env");
const result = config({ path: envPath });
if (result.parsed && Object.keys(result.parsed).length > 0) {
  console.log(`Loaded environment from ${envPath}`);
} else {
  console.warn(
    `No variables loaded from ${envPath} (file missing or empty). Using process.env and defaults.`,
  );
}
