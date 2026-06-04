# Benchmark App Provider Evaluation

## 1. cypress-realworld-app (PRIMARY)

- **URL**: https://github.com/cypress-io/cypress-realworld-app
- **License**: MIT
- **Language/Framework**: TypeScript, React, Express, Material-UI
- **Install commands**: `yarn install`
- **Test commands**: `yarn test` (unit), `yarn cypress:run` (e2e)
- **Dev server command**: `yarn dev`
- **Default ports**: 3000 (frontend), 3001 (API)
- **Database/setup**: SQLite (built-in, seeds on first run via `yarn db:seed`)
- **Browser testing**: Yes — full Cypress e2e suite, 100+ tests
- **Suitability**: Excellent — real auth (Passport.js), transactions, notifications, full CRUD
- **Integration risks**: Yarn v1 dependency; Cypress version pinning; needs Node 18+
- **Notes**: Venmo-clone with user signup, login, transactions, comments, notifications. Perfect for UI-fix, backend-validation, and test-coverage benchmarks.

## 2. gothinkster/realworld

- **URL**: https://github.com/gothinkster/realworld
- **License**: MIT
- **Language/Framework**: Spec-only (multiple implementations)
- **Install commands**: Varies by implementation
- **Test commands**: Postman/Newman API tests (standardized)
- **Dev server command**: Varies
- **Default ports**: 3000 (typical)
- **Database/setup**: Varies (Postgres, SQLite, MongoDB)
- **Browser testing**: Limited (no official e2e tests, but UI exists)
- **Suitability**: Good for API-contract tasks; less ideal for UI tasks
- **Integration risks**: Must pick a specific implementation; no unified test suite
- **Notes**: "Medium clone" — articles, comments, tags, auth. Good for API-contract and backend-validation categories.

## 3. tastejs/todomvc

- **URL**: https://github.com/tastejs/todomvc
- **License**: MIT
- **Language/Framework**: Vanilla JS, React, Vue, Angular, etc.
- **Install commands**: `npm install` (varies by implementation)
- **Test commands**: Limited built-in tests
- **Dev server command**: Static file serve or framework-specific
- **Default ports**: 8080 (typical)
- **Database/setup**: None (localStorage)
- **Browser testing**: Yes — simple DOM, easy to validate
- **Suitability**: Good for quick UI-fix and accessibility tasks
- **Integration risks**: Many implementations to choose from; no backend
- **Notes**: Classic todo app. Best for ui-fix, accessibility, and frontend-state categories. Fast iteration cycle.

## 4. juice-shop/juice-shop

- **URL**: https://github.com/juice-shop/juice-shop
- **License**: MIT
- **Language/Framework**: Angular, Express, SQLite
- **Install commands**: `npm install`
- **Test commands**: `npm test` (unit), `npm run e2e` (Protractor/Cypress)
- **Dev server command**: `npm start`
- **Default ports**: 3000
- **Database/setup**: SQLite (auto-seeds)
- **Browser testing**: Yes — Angular app with full UI
- **Suitability**: Excellent for security-defensive tasks
- **Integration risks**: Large dependency tree; Angular-specific; intentionally vulnerable (must only do defensive fixes)
- **Notes**: OWASP intentionally-vulnerable app. Use ONLY for defensive input-validation and sanitization benchmarks. Never create exploits.

## 5. snowmountainAi/webdevbench

- **URL**: https://github.com/snowmountainAi/webdevbench
- **License**: Apache-2.0
- **Language/Framework**: Mixed (benchmark harness)
- **Install commands**: `pip install -r requirements.txt`
- **Test commands**: `python run_benchmark.py`
- **Dev server command**: N/A (benchmark runner)
- **Default ports**: N/A
- **Database/setup**: None
- **Browser testing**: Yes (uses Playwright for validation)
- **Suitability**: Good reference for benchmark format; tasks pre-defined
- **Integration risks**: May overlap with our task format; Python-based
- **Notes**: Existing AI coding benchmark. Useful as reference for task format and validation approach. Can adapt tasks into our schema.

---

## Prioritization

1. **cypress-realworld-app** — First fully integrated benchmark (full-stack, tests, browser)
2. **juice-shop** — Security-defensive tasks only
3. **todomvc** — Quick UI/accessibility iterations
4. **realworld** — API-contract validation
5. **webdevbench** — Reference/adaptation source
