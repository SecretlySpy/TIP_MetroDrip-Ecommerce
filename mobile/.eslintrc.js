// The `lint` script in package.json referenced eslint long before eslint was a
// dependency, so `npm run lint` failed on a clean checkout and nothing noticed
// — the mobile app had no CI at all. Both halves are fixed together.
module.exports = {
  root: true,
  extends: ["expo"],
  ignorePatterns: ["node_modules/", ".expo/", "dist/"],
  rules: {
    // The API client mirrors the DRF serializers in apps/mobile_api by hand.
    // An unused import there usually means a response field was dropped on the
    // server and the type was left behind, so it should be visible, not fatal.
    "@typescript-eslint/no-unused-vars": [
      "warn",
      { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
    ],
  },
};
