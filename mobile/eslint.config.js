const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/**'],
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'warn',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // Keep the React 19 diagnostic visible while allowing effects whose
      // sole purpose is to initiate an asynchronous native/API read.
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
]);
