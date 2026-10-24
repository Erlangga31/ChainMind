# Changelog

Notable user-facing changes are recorded here. This project follows semantic versioning.

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
