# Audit cakupan proposal ChainMind

Audit ini membandingkan repository dengan teks hasil ekstraksi lokal dari
[`docs/reference/ChainMind_Proposal.pdf`](./reference/ChainMind_Proposal.pdf). PDF diabaikan Git
(`docs/reference/`); file sumber tidak ditambahkan ke commit.

## Arti status dan tingkat verifikasi

- **Implemented**: perilaku atau artefak yang dinyatakan tersedia di repository.
- **Partial**: ada scaffold/mock atau cakupan terbatas; bagian produksi atau integrasi penuh belum tersedia.
- **Not implemented**: belum ada implementasi yang ditemukan.
- **unit-tested**: tes otomatis menjalankan logika atau kontrak kode lokal.
- **sandbox-verified**: tes HTTP terhadap simulator SAP lokal; bukan tenant SAP.
- **LocalStack-verified**: tes integrasi AWS SDK terhadap LocalStack dalam CI; bukan AWS nyata.
- **synth-only**: template CDK disintesis dan diuji; tidak ada deployment AWS.
- **needs real AWS or SAP**: memerlukan akun, lisensi, konfigurasi, atau koneksi tenant sungguhan.

Semua perhitungan ekonomi demo adalah deterministik dan memakai fixture. Chain of Thought adalah
ringkasan penalaran yang aman untuk audit, bukan log internal model. Tidak ada klaim bahwa AWS,
Bedrock, Cognito/IAS, Teams/Slack/SES, SAP, atau SAP BTP telah diverifikasi secara live.

## Cakupan section proposal

| Section | Status | Implementasi dan bukti | Verifikasi / batas |
| --- | --- | --- | --- |
| 3 — alasan AWS dan SAP | Partial | Pembagian peran AWS/SAP diterangkan dalam [arsitektur](./architecture.md) dan [pitch](./PITCH.md); adapter SAP mock menjaga data SAP sebagai sumber input demo. | Unit dan sandbox lokal; interoperabilitas resmi AWS–SAP/RISE belum divalidasi, **needs real AWS or SAP**. |
| 5 — solusi agentic AI empat agen | Implemented (mock) | [Agents](../src/chainmind/agents/), [pipeline](../src/chainmind/workflow/pipeline.py), action groups pada [CDK stack](../infra/chainmind_stack.py). | unit-tested, synth-only; tidak ada Bedrock runtime. |
| 6 — arsitektur AWS/SAP | Partial | CDK memodelkan Lambda, EventBridge, Step Functions, API Gateway, S3, CloudWatch, IAM/KMS, VPC, Cognito, dan Bedrock; SAP adapters/sandbox tersedia. | unit-tested, sandbox-verified, synth-only; SAP BTP production dan AWS deployment **needs real AWS or SAP**. |
| 7 — alur end-to-end 8 langkah | Partial | Pemetaan lengkap per langkah di bawah; local pipeline menguji alur mock dari event hingga tracking. | unit-tested dan sandbox-verified; Step Functions/AWS-to-SAP runtime **needs real AWS or SAP**. |
| 7.1 — diagram end-to-end dan stages 0–6 | Implemented (live mock run) | [FlowDiagram](../dashboard/src/FlowDiagram.tsx) menampilkan event ingest, stage 0–6, dua decision diamonds, cabang tidak signifikan/tolak/revisi, nilai vendor/PO, dan service footer. Stage status berasal dari `/runs/{run_id}`. | unit-tested, Playwright E2E/axe, screenshot ID/EN; service wiring real **needs real AWS or SAP**. |
| 8 — UX dan human-in-the-loop | Partial | [Dashboard](../dashboard/src/App.tsx), feed dengan sumber SAP, fake OIDC roles, signed links, modal konfirmasi, approve/reject/revise. | unit-tested dan Playwright E2E; omnichannel live dan SAP Business Workflow **needs real AWS or SAP**. |
| 9 — keamanan, privasi, kepatuhan | Partial | JWT verification, RBAC, KMS, private endpoints, encrypted/versioned S3, CloudTrail, audit, cdk-nag, API throttling. | Unit-tested dan synth-only; IAM review, VPC flow logs/WAF, account controls, privacy/compliance certification **needs real AWS or SAP**. |
| 10 — competitive position | Partial | Klaim dan pembeda dirangkum sebagai proposisi dalam [pitch](./PITCH.md); tidak ada benchmark produk pesaing. | Documentation-only; validasi pasar dan klaim kompetitif belum dilakukan. |
| 11 — model bisnis dan target pasar | Partial | Target buyer/operator, tier usage demo, onboarding, dan distribusi potensial dalam [BUSINESS.md](./BUSINESS.md) dan [MARKETPLACE.md](./MARKETPLACE.md). | unit-tested metering; pricing defaults illustrative; marketplace listing and willingness-to-pay TBD. |
| 12 — dampak/KPI | Implemented (local comparison) | `GET /kpis`, timestamp response measurement, repeated-scenario decision-consistency metric, and dashboard comparison. | unit-tested; manual baselines/workload targets illustrative; no production/SAP measurement. |
| Tenant metering and isolation | Implemented (local scaffold) | Tenant JWT claim, tenant-scoped run/idempotency/KPI/current-month usage routes, per-tenant plan/agent overrides, role-gated usage page. | unit-tested; tenant provisioning, billing integration, and production isolation review **need real AWS or SAP**. |
| Vendor alternatif lokal | Implemented (seeded simulation) | [Procurement ranking](../src/chainmind/agents/procurement.py), [regional vendor seeds](../src/chainmind/data/seed_vendors.json), plant region on inventory. | unit-tested; regional distance and capacity remain simulated data. |
| Multi-material BOM impact | Implemented (seeded simulation) | [Multi-component logistics](../src/chainmind/agents/logistics.py), [additional inventory fixture](../src/chainmind/data/seed_additional_inventory.json), impact table in dashboard. | unit-tested with two affected materials; no live SAP BOM source. |
| Indonesian/English experience and accessible layout | Implemented | [translations](../dashboard/src/i18n.ts), localized notifications/demo labels, accessibility controls and [Playwright axe/responsive test](../dashboard/e2e/auth-workflow.spec.ts). | unit-tested, Playwright; critical/serious axe violations blocked, 375px and 1280px viewports exercised. |
| Model-agnostic Bedrock configuration | Implemented (configuration surface) | `CHAINMIND_BEDROCK_MODEL_ID`, `BedrockLLMClient`, and deterministic Bedrock Agents fallback metadata. | unit-tested configuration; model permissions/invocation **needs real AWS**. |
| Release and budget readiness | Implemented (scaffold) | [Version/changelog](../CHANGELOG.md), [tag guidance](../CONTRIBUTING.md), [jury evidence](./JURY_PACK.md), CDK budget threshold and project tags. | CDK assertions, synth-only; cost-allocation tag activation, SNS email confirmation, and real account spend monitoring **needs real AWS**. |
| 23 — Figure 1 live flow | Implemented (mock) | [Flow page](../dashboard/src/FlowDiagram.tsx), [component/branch tests](../dashboard/src/FlowDiagram.test.tsx), [E2E](../dashboard/e2e/auth-workflow.spec.ts), [flow screenshots](./screenshots/). | Vitest, Playwright and axe on ID/EN; current data comes from the selected run; no live service validation. |
| 24 — presenter and replay | Implemented (offline demo tooling) | `?presenter=1`, [replay generator](../scripts/generate_replay_fixture.py), [replay fixture](../dashboard/public/replay-run.json), [preflight](../scripts/preflight.py), [3-minute video](./VIDEO_SCRIPT.md). | E2E and generator/preflight unit tests; replay is recorded mock data and read-only. |
| 25 — proposal fidelity and stage 6 outputs | Implemented (locally checkable claims) | [fidelity tests](../tests/test_proposal_fidelity.py), [numbered audit steps](../src/chainmind/core/models.py), [tracking outputs](../src/chainmind/agents/tracking.py), `/kpis`. | Pipeline/API tests and mocked S3 archive assertions; only LocalStack/synth for AWS, sandbox for SAP. |
| 26 — real-account readiness | Implemented (documentation/validation) | [GO_LIVE.md](./GO_LIVE.md), [offline config validator](../scripts/validate_config.py), [AWS verifier](../scripts/verify_aws_account.py), [SAP verifier](../scripts/verify_sap_tenant.py). | Validator unit-tested; live checks are opt-in and were not run. |
| Presenter package | Implemented (reproducible) | [Pitch generator](../scripts/build_slides.py), bilingual [PowerPoint decks](./slides/), [jury Q&A](./QNA.md), and [rehearsal checklist](./REHEARSAL.md). | Unit test verifies both decks, 11 slides and speaker notes; no claim of audience/user validation. |
| 13 — roadmap MVP enam minggu | Partial | Sandbox, API, agents, UI, notifikasi, demo dan testing dijabarkan di [DEMO.md](./DEMO.md). | Implementasi mock lokal terverifikasi; pilot BTP dan runtime layanan nyata belum dikerjakan. |
| 15 — risiko dan mitigasi | Partial | Risiko salah pilih agen, adopsi, kompleksitas SAP, ketergantungan Bedrock, dan perubahan API dicatat di [BUSINESS.md](./BUSINESS.md). | Documentation-only, cdk-nag synth-only; bukan threat model atau security certification formal. |
| 16 — pendanaan/sumber daya | Partial | Kategori biaya AWS/SAP, kapasitas tim, dan user validation placeholders tersedia di [BUSINESS.md](./BUSINESS.md). | Tidak ada harga, budget, atau estimasi aktual; semua masih TBD. |

## Lampiran B — layanan AWS dan SAP

| Layanan proposal | Status | Lokasi/bukti | Tingkat verifikasi |
| --- | --- | --- | --- |
| Amazon Bedrock Agents | Partial | [Bedrock clients/agents](../src/chainmind/integrations/llm/), empat Agents, Action Groups dan Guardrail di [CDK](../infra/chainmind_stack.py). Mode default `mock`. | unit-tested, synth-only; real model access **needs real AWS**. |
| AWS Lambda | Implemented (package scaffold) | [Lambda handlers](../src/chainmind/handlers/), [package builder](../infra/lambda_package.py), asset Python 3.12 Linux x86_64. | unit-tested asset content, synth-only; belum dideploy. |
| Amazon EventBridge | Partial | Event bus/rules pada [CDK](../infra/chainmind_stack.py), Event Mesh bridge handler, [LocalStack test](../tests/integration/test_localstack_services.py). | LocalStack-verified event API and handler logic in CI; Lambda event-source invocation synth-only; production delivery **needs real AWS**. |
| AWS Step Functions | Partial | State machine, callback approval, Retry/Catch, DLQ dan tracing pada [CDK](../infra/chainmind_stack.py); task-token test di [LocalStack suite](../tests/integration/test_localstack_services.py). | LocalStack-verified callback API in CI; production callback **needs real AWS**. |
| Amazon API Gateway | Partial | REST API, Cognito authorizer, throttling, signed notification routes pada [CDK](../infra/chainmind_stack.py). | synth-only; deployed API **needs real AWS**. |
| Amazon S3 | Partial | Encrypted/versioned audit-artifact bucket, block public access di [CDK](../infra/chainmind_stack.py); run audit/trace archive integration test. | LocalStack-verified archive API in CI; production writes **needs real AWS**. |
| Amazon CloudWatch | Partial | Log groups, alarms, dashboard, API access logs pada [CDK](../infra/chainmind_stack.py). | synth-only; production telemetry **needs real AWS**. |
| Amazon DynamoDB | Partial | Idempotency/event ledger dan run store; LocalStack integration tests. | LocalStack-verified API behavior in CI; account controls **needs real AWS**. |
| Amazon SQS | Partial | Workflow DLQ in CDK and LocalStack queue integration test. | LocalStack-verified queue API in CI; production redrive policy **needs real AWS**. |
| AWS Secrets Manager | Partial | Secret reads in handlers/factory and LocalStack read test. | LocalStack-verified secret read in CI; secret rotation **needs real AWS**. |
| Amazon SES | Partial | Email adapter and LocalStack send test (no external email delivery). | LocalStack-verified SES API in CI; identity verification/delivery **needs real AWS**. |
| AWS IAM dan AWS KMS | Partial | CMK, Lambda roles, grants, encrypted DynamoDB/S3/SQS/Secrets dan VPC policies pada [CDK](../infra/chainmind_stack.py). | CDK assertions, synth-only; account-level IAM validation **needs real AWS**. |
| SAP S/4HANA | Partial (mock) | [S/4HANA client](../src/chainmind/integrations/sap/real_clients.py), OData V2 sandbox/EDMX pada [sandbox](../sandbox/sap_sandbox/main.py), JSON Schemas di [`contracts/sap/`](../contracts/sap/), opt-in [tenant verifier](../scripts/verify_sap_tenant.py). | contract tests and sandbox-verified; live tenant smoke **needs real SAP**. |
| SAP Ariba Network | Partial (mock/custom adapter) | [Ariba client](../src/chainmind/integrations/sap/real_clients.py), ChainMind Integration Suite adapter contract/EDMX and vendor offers/PO/confirmation/ASN sandbox. | contract tests and sandbox-verified; live supplier network **needs real SAP**. |
| SAP Business Technology Platform (BTP) | Not implemented (prerequisite) | [Deployment prerequisites](./DEPLOY.md). | **needs real SAP** tenant and account. |
| SAP Integration Suite | Not implemented (prerequisite) | [Real SAP client stubs](../src/chainmind/integrations/sap/real_stubs.py), [DEPLOY.md](./DEPLOY.md). | **needs real SAP** connectivity, destinations, credentials and API policies. |
| SAP Event Mesh | Partial (simulator) | [Event Mesh sandbox routes](../sandbox/sap_sandbox/main.py), HMAC bridge to API. | sandbox-verified locally; BTP broker **needs real SAP**. |
| SAP Business Workflow | Partial (simulator) | [Approval task sandbox](../sandbox/sap_sandbox/main.py), callback integration, explicit human approval. | sandbox-verified; enterprise workflow hierarchy **needs real SAP**. |
| SAP Cloud Connector | Not implemented (prerequisite) | Architecture and [deployment requirements](./DEPLOY.md). | **needs real SAP** setup and network approval. |
| SAP BTP Identity Authentication Service (IAS) | Partial (fake OIDC) | [OIDC sandbox](../sandbox/sap_sandbox/oidc.py), PKCE/JWKS/RS256; backend JWT roles. | unit-tested and sandbox-verified; federation with IAS **needs real SAP**. |

## Section 7 — delapan langkah integrasi

| # | Proposal flow | Implementasi | Status / verifikasi |
| --- | --- | --- | --- |
| 1 | SAP Event Mesh atau sinyal eksternal cuaca/logistik masuk | Simulated Event Mesh publish/webhook, `event_ingestion` audit record (`proposal_step=1`) dan API | unit-tested, sandbox-verified; external data provider/BTP **needs real SAP**. |
| 2 | EventBridge → Lambda → Monitoring Bedrock Agent | CDK bus/rules, Lambda handler dan Bedrock Agent scaffold; local pipeline terpicu API | unit-tested, synth-only; cloud trigger **needs real AWS**. |
| 3 | Monitoring Action Group membaca S/4HANA OData via Integration Suite | Mock S/4HANA client, OData sandbox, Action Group; Integration Suite tercatat prerequisite | unit-tested, sandbox-verified; **needs real SAP**. |
| 4 | Procurement memanggil Ariba Network API untuk alternatif vendor | Ariba mock memberi lead time, harga, kapasitas, risiko; minimal dua vendor dibandingkan | unit-tested, sandbox-verified; **needs real SAP**. |
| 5 | Step Functions orkestrasi, observability, retry API | CDK state machine dengan approval callback, retry/catch, X-Ray, DLQ | unit-tested, synth-only; **needs real AWS**. |
| 6 | Lambda menulis draf PO ke S/4HANA dan memulai Business Workflow | Mock draft `PENDING_APPROVAL`, SAP workflow simulator dan role-gated decision API | unit-tested, sandbox-verified; **needs real SAP**. |
| 7 | API Gateway menyajikan notifikasi Teams/Slack/email | Adaptive Card/Block Kit melalui fake HTTP server, SES Stubber, signed link route dan UI feed | unit-tested, synth-only; kanal nyata **needs real AWS or SAP**. |
| 8 | Approval memperbarui SAP; audit disimpan di CloudWatch Logs/S3 | Human approval and execution audits use `proposal_step=8`; S3 archive stores trace/audit. | unit-tested, mocked S3 archive, LocalStack in CI and synth-only; **needs real AWS or SAP**. |

## End-to-end figure — Stage 0 sampai Stage 6

| Stage | Nama | Implementasi | Verifikasi |
| --- | --- | --- | --- |
| 0 | External event capture | Event Mesh simulator, scenario injection, API ingress/dedupe | unit-tested, sandbox-verified |
| 1 | Deteksi Gangguan | Monitoring severity dan persist run/event | unit-tested |
| 2 | Analisis Dampak | Coverage, stockout, loss deterministik | unit-tested |
| 3 | Pencarian Solusi | Vendor comparison dan feasibility economics | unit-tested, sandbox-verified |
| 4 | Analisis & Keputusan | Orchestrator memilih rekomendasi; model hanya menulis rationale | unit-tested, synth-only |
| 5 | Human-in-the-Loop | Viewer/approver authorization, explicit confirmation, revise/reject | unit-tested, sandbox-verified, Playwright |
| 6 | Eksekusi Purchase Order / Monitoring & Tracking | Mock SAP PO execution, supplier confirmation, shipment monitoring, ETA update, inventory projection, deviation alert, KPI outcome. | unit-tested, sandbox-verified; SAP live belum diverifikasi |

## Validasi dan batas deployment

Validasi lokal pada presenter-package update: backend pytest **155 passed, 9 skipped** (opt-in
LocalStack/live SAP suite tidak dijalankan lokal); dashboard Vitest **15 passed**; Playwright
**10 passed**, termasuk flow ID/EN, axe, presenter, offline replay dan viewport 375px / 1280px;
browser-test typecheck dan production build lulus; Ruff lint/format lulus. `npx --yes aws-cdk synth`
lulus dengan virtualenv Python di PATH. CI status per SHA dicatat di GitHub Actions; semua enam job
untuk commit `b185ba6` sukses, sebelum perubahan slide ini.

CDK synth menargetkan Python 3.12 Linux x86_64 dan memaketkan dependencies. Synthesis tidak
membuktikan asset dijalankan Lambda. Suppressions cdk-nag yang ada memiliki alasan tertulis; review
akun target, WAF, VPC flow logs, secret rotation, Bedrock permissions, retention, biaya, dan network
paths tetap menjadi deployment gate. Tidak ada AWS/SAP live deployment atau certification.
