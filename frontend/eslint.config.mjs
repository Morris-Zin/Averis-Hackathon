import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const config = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  { rules: { "@typescript-eslint/no-non-null-assertion": "error" } },
  {
    ignores: [
      ".next/**",
      "out/**",
      "src/lib/generated/api.ts",
      "next-env.d.ts",
    ],
  },
];

export default config;
