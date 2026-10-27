# Changelog

Notable user-facing changes are recorded here. This project follows semantic versioning.

## [1.1.0] - 2026-10-24

### Added

- Viewport-fitted dashboard shell with collapsible desktop navigation and mobile tab bar.
- Tenant-scoped Data Studio for materials, vendors, shipments and disruption records, including CRUD, import/export, templates and row-level validation feedback.
- Persistent SQLite mock catalog, DynamoDB adapter, one-time demo bootstrap, clear/reset actions and deterministic sample-data generation.
- Custom-data pipeline coverage and bilingual dashboard screenshots for light/dark themes and desktop/mobile viewports.

### Verification boundaries

- User data is stored in the local mock catalog; AWS and SAP remain simulated and no live weather polling is enabled.
- The deterministic demo preset remains available for presenter mode.

## [1.0.0] - 2026-10-24

### Added

- Offline-first manufacturing disruption workflow with human-approved purchase orders.
- Multi-tenant usage metering, illustrative pricing tiers, and KPI comparisons.
- Local vendor proximity/capacity ranking, BOM impact analysis, and Indonesian/English dashboard.
- SAP OData-style sandbox contracts and LocalStack AWS service integration checks.
- Windows local launcher, demo materials, accessibility/responsive checks, and jury evidence pack.
- CDK monthly cost budget notifications and project/environment cost-allocation tags.

### Verification boundaries

- Mock-mode backend/dashboard behavior is exercised by automated tests.
- AWS SDK integration is exercised against LocalStack; infrastructure is synthesized with CDK.
- SAP behavior is sandbox/contract-tested.
- No production AWS deployment or live SAP tenant integration has been performed.
