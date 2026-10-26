// MapLibre 6 loads its web worker from a URL next to maplibre-gl.mjs, which a bundled chunk does
// not have. Copy the (self-contained) worker into public/ and point setWorkerUrl at it
// (components/vessel-map.tsx). Runs before `dev` and `build`.
import { copyFileSync, mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const dist = join(dirname(require.resolve("maplibre-gl/package.json")), "dist");
const out = join(import.meta.dirname, "..", "public", "vendor");
mkdirSync(out, { recursive: true });
copyFileSync(join(dist, "maplibre-gl-worker.mjs"), join(out, "maplibre-gl-worker.mjs"));
