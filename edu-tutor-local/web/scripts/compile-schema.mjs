import { readFileSync, writeFileSync, copyFileSync } from "node:fs";
copyFileSync(
  new URL("../src/avatar-manifest.json", import.meta.url),
  new URL("../public/avatar-manifest.json", import.meta.url),
);
import Ajv2020 from "ajv/dist/2020.js";
import standalone from "ajv/dist/standalone/index.js";
const schema = JSON.parse(
  readFileSync(
    new URL("../src/lesson_plan.schema.json", import.meta.url),
    "utf8",
  ),
);
const ajv = new Ajv2020({
  allErrors: true,
  strict: false,
  code: { source: true, esm: true, lines: true },
});
const validator = ajv.compile(schema);
let output = standalone(ajv, validator);
// AJV emits CommonJS helper references even in ESM mode. Make these static
// imports so Vite can bundle them without runtime evaluation or require().
output = output.replace(
  /const (\w+) = require\("([^"]+)"\)\.default;/g,
  (_, name, path) => `import ${name} from "${path}.js";`,
);
writeFileSync(
  new URL("../src/validate-lesson.js", import.meta.url),
  "// Generated from lesson_plan.schema.json. Do not edit by hand.\n" + output,
);
