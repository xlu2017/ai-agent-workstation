# Benchmark Applications

Applications used to evaluate the autonomous coding workstation's capabilities.

## Primary

| Repo | Framework | License | Suitability | Status |
|------|-----------|---------|-------------|--------|
| cypress-realworld-app | React/Express/TypeScript | MIT | Excellent — full-stack, Cypress tests, real auth | **Primary** |

## Secondary

| Repo | Framework | License | Suitability | Status |
|------|-----------|---------|-------------|--------|
| gothinkster/realworld | Multi-framework | MIT | Good — standardized API spec, many implementations | Evaluated |
| tastejs/todomvc | Multi-framework | MIT | Good — simple UI, many frameworks, quick iterations | Evaluated |
| juice-shop/juice-shop | Angular/Express | MIT | Good — security focus, intentional vulns (defensive fixes) | Evaluated |
| snowmountainAi/webdevbench | Multi | Apache-2.0 | Good — existing benchmark format, tasks pre-defined | Evaluated |

## Selection Criteria

1. Open-source with permissive license
2. Full-stack (UI + API + DB) preferred
3. Has existing test suite (unit + e2e)
4. Runs locally without external services (or can be mocked)
5. Suitable for seeded-bug injection
6. Browser-testable UI
7. Reasonable install time (<5 min)
