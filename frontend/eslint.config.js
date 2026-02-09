import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    linterOptions: {
      reportUnusedDisableDirectives: 'warn',  // Warn on unused disable comments
    },
    rules: {
      // Enforce unused vars are prefixed with underscore
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        caughtErrorsIgnorePattern: '^_',
      }],
      // Warn on any types - use sparingly in tests/mocks
      '@typescript-eslint/no-explicit-any': 'warn',
      // Enforce react hooks rules
      'react-hooks/exhaustive-deps': 'error',
      'react-hooks/set-state-in-effect': 'warn',
      // Warn on case declarations (usually fixable)
      'no-case-declarations': 'warn',
      // Disallow console in production code (except comments)
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      // Disallow debugger in production code
      'no-debugger': 'error',

      // ====== God File Prevention (Phase 67-03) ======
      // Warn on files exceeding 500 lines (skip blank lines and comments)
      'max-lines': ['warn', {
        max: 500,
        skipBlankLines: true,
        skipComments: true
      }],
      // Warn on functions exceeding 50 lines
      'max-lines-per-function': ['warn', {
        max: 50,
        skipBlankLines: true,
        skipComments: true,
        IIFEs: true
      }],
      // Warn on high cyclomatic complexity
      'complexity': ['warn', 15],
    },
  },
])
