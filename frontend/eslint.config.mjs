// For more info, see https://github.com/storybookjs/eslint-plugin-storybook#configuration-flat-config-format
import storybook from "eslint-plugin-storybook";

import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    ".next-mock/**",
    "out-mock/**",
    "storybook-static/**",
    "public/mockServiceWorker.js",
    "test-results/**",
    "playwright-report/**",
  ]),
  ...storybook.configs["flat/recommended"],
  // Reducer hydration and external async evaluation events intentionally update state in effects.
  { rules: { "react-hooks/set-state-in-effect": "off" } },
]);

export default eslintConfig;
