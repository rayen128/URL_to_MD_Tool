import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = defineConfig([
  ...nextVitals,
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "web/**",
    ".pytest_cache/**",
    "__pycache__/**",
    "tests/__pycache__/**",
    "output/**",
    "logs/**",
  ]),
]);

export default eslintConfig;
