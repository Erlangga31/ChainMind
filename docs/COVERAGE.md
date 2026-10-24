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
| 7.1 — diagram end-to-end dan stages 0–6 | Implemented (demo mapping) | Stage 0–6 dijabarkan di tabel alur berikutnya; enam label dashboard dan CLI berada di [components](../dashboard/src/components.tsx) dan [run_demo.py](../scripts/run_demo.py). | unit-tested, Playwright E2E; service wiring real **needs real AWS or SAP**. |
| 8 — UX dan human-in-the-loop | Partial | [Dashboard](../dashboard/src/App.tsx), feed dengan sumber SAP, fake OIDC roles, signed links, modal konfirmasi, approve/reject/revise. | unit-tested dan Playwright E2E; omnichannel live dan SAP Business Workflow **needs real AWS or SAP**. |
| 9 — keamanan, privasi, kepatuhan | Partial | JWT verification, RBAC, KMS, private endpoints, encrypted/versioned S3, CloudTrail, audit, cdk-nag, API throttling. | Unit-tested dan synth-only; IAM review, VPC flow logs/WAF, account controls, privacy/compliance certification **needs real AWS or SAP**. |
| 10 — competitive position | Partial | Klaim dan pembeda dirangkum sebagai proposisi dalam [pitch](./PITCH.md); tidak ada benchmark produk pesaing. | Documentation-only; validasi pasar dan klaim kompetitif belum dilakukan. |
| 11 — model bisnis dan target pasar | Partial | Target buyer/operator, langganan SaaS bertier, onboarding, dan distribusi potensial dalam [BUSINESS.md](./BUSINESS.md). | Documentation-only; harga, marketplace listing, dan willingness-to-pay TBD. |
| 12 — dampak/KPI | Partial | `GET /kpis`, model KPI dan tampilan dashboard. Proposal mengusulkan respons menit, mitigasi proaktif, beban kerja procurement lebih ringan, serta keputusan konsisten. | unit-tested; angka dan savings dashboard adalah ilustratif, target proposal perlu pilot, **needs real SAP**. |
| 13 — roadmap MVP enam minggu | Partial | Sandbox, API, agents, UI, notifikasi, demo dan testing dijabarkan di [DEMO.md](./DEMO.md). | Implementasi mock lokal terverifikasi; pilot BTP dan runtime layanan nyata belum dikerjakan. |
| 15 — risiko dan mitigasi | Partial | Risiko salah pilih agen, adopsi, kompleksitas SAP, ketergantungan Bedrock, dan perubahan API dicatat di [BUSINESS.md](./BUSINESS.md). | Documentation-only, cdk-nag synth-only; bukan threat model atau security certification formal. |
| 16 — pendanaan/sumber daya | Partial | Kategori biaya AWS/SAP, kapasitas tim, dan user validation placeholders tersedia di [BUSINESS.md](./BUSINESS.md). | Tidak ada harga, budget, atau estimasi aktual; semua masih TBD. |

## Lampiran B — layanan AWS dan SAP

| Layanan proposal | Status | Lokasi/bukti | Tingkat verifikasi |
| --- | --- | --- | --- |
| Amazon Bedrock Agents | Partial | [Bedrock clients/agents](../src/chainmind/integrations/llm/), empat Agents, Action Groups dan Guardrail di [CDK](../infra/chainmind_stack.py). Mode default `mock`. | unit-tested, synth-only; real model access **needs real AWS**. |
| AWS Lambda | Implemented (package scaffold) | [Lambda handlers](../src/chainmind/handlers/), [package builder](../infra/lambda_package.py), asset Python 3.12 Linux x86_64. | unit-tested asset content, synth-only; belum dideploy. |
| Amazon EventBridge | Partial | Event bus/rules pada [CDK](../infra/chainmind_stack.py), Event Mesh bridge handler. | unit-tested, synth-only; delivery runtime **needs real AWS**. |
| AWS Step Functions | Partial | State machine, callback approval, Retry/Catch, DLQ dan tracing pada [CDK](../infra/chainmind_stack.py). | unit-tested, synth-only; AWS task-token runtime **needs real AWS**. |
| Amazon API Gateway | Partial | REST API, Cognito authorizer, throttling, signed notification routes pada [CDK](../infra/chainmind_stack.py). | synth-only; deployed API **needs real AWS**. |
| Amazon S3 | Partial | Encrypted/versioned audit-artifact bucket, block public access di [CDK](../infra/chainmind_stack.py). | synth-only; object writes/runtime **needs real AWS**. |
| Amazon CloudWatch | Partial | Log groups, alarms, dashboard, API access logs pada [CDK](../infra/chainmind_stack.py). | synth-only; production telemetry **needs real AWS**. |
| AWS IAM dan AWS KMS | Partial | CMK, Lambda roles, grants, encrypted DynamoDB/S3/SQS/Secrets dan VPC policies pada [CDK](../infra/chainmind_stack.py). | CDK assertions, synth-only; account-level IAM validation **needs real AWS**. |
| SAP S/4HANA | Partial (mock) | [S/4HANA client](../src/chainmind/integrations/sap/mock_s4hana.py), OData local routes pada [sandbox](../sandbox/sap_sandbox/main.py). | sandbox-verified; tenant/API mapping **needs real SAP**. |
| SAP Ariba Network | Partial (mock) | [Ariba client](../src/chainmind/integrations/sap/mock_ariba.py), vendor offers/PO/ASN sandbox. | sandbox-verified; live supplier network **needs real SAP**. |
| SAP Business Technology Platform (BTP) | Not implemented (prerequisite) | [Deployment prerequisites](./DEPLOY.md). | **needs real SAP** tenant and account. |
| SAP Integration Suite | Not implemented (prerequisite) | [Real SAP client stubs](../src/chainmind/integrations/sap/real_stubs.py), [DEPLOY.md](./DEPLOY.md). | **needs real SAP** connectivity, destinations, credentials and API policies. |
| SAP Event Mesh | Partial (simulator) | [Event Mesh sandbox routes](../sandbox/sap_sandbox/main.py), HMAC bridge to API. | sandbox-verified locally; BTP broker **needs real SAP**. |
| SAP Business Workflow | Partial (simulator) | [Approval task sandbox](../sandbox/sap_sandbox/main.py), callback integration, explicit human approval. | sandbox-verified; enterprise workflow hierarchy **needs real SAP**. |
| SAP Cloud Connector | Not implemented (prerequisite) | Architecture and [deployment requirements](./DEPLOY.md). | **needs real SAP** setup and network approval. |
| SAP BTP Identity Authentication Service (IAS) | Partial (fake OIDC) | [OIDC sandbox](../sandbox/sap_sandbox/oidc.py), PKCE/JWKS/RS256; backend JWT roles. | unit-tested and sandbox-verified; federation with IAS **needs real SAP**. |

## Section 7 — delapan langkah integrasi

| # | Proposal flow | Implementasi | Status / verifikasi |
| --- | --- | --- | --- |
| 1 | SAP Event Mesh atau sinyal eksternal cuaca/logistik masuk | Simulated Event Mesh publish/webhook dan event ingestion API | sandbox-verified; external data provider/BTP **needs real SAP**. |
| 2 | EventBridge → Lambda → Monitoring Bedrock Agent | CDK bus/rules, Lambda handler dan Bedrock Agent scaffold; local pipeline terpicu API | unit-tested, synth-only; cloud trigger **needs real AWS**. |
| 3 | Monitoring Action Group membaca S/4HANA OData via Integration Suite | Mock S/4HANA client, OData sandbox, Action Group; Integration Suite tercatat prerequisite | unit-tested, sandbox-verified; **needs real SAP**. |
| 4 | Procurement memanggil Ariba Network API untuk alternatif vendor | Ariba mock memberi lead time, harga, kapasitas, risiko; minimal dua vendor dibandingkan | unit-tested, sandbox-verified; **needs real SAP**. |
| 5 | Step Functions orkestrasi, observability, retry API | CDK state machine dengan approval callback, retry/catch, X-Ray, DLQ | unit-tested, synth-only; **needs real AWS**. |
| 6 | Lambda menulis draf PO ke S/4HANA dan memulai Business Workflow | Mock draft `PENDING_APPROVAL`, SAP workflow simulator dan role-gated decision API | unit-tested, sandbox-verified; **needs real SAP**. |
| 7 | API Gateway menyajikan notifikasi Teams/Slack/email | Adaptive Card/Block Kit melalui fake HTTP server, SES Stubber, signed link route dan UI feed | unit-tested, synth-only; kanal nyata **needs real AWS or SAP**. |
| 8 | Approval memperbarui SAP; audit disimpan di CloudWatch Logs/S3 | Human confirmation, mock SAP execution, audit trail; CDK CloudWatch/S3 archive | unit-tested, sandbox-verified, synth-only; **needs real AWS or SAP**. |

## End-to-end figure — Stage 0 sampai Stage 6

| Stage | Nama | Implementasi | Verifikasi |
| --- | --- | --- | --- |
| 0 | External event capture | Event Mesh simulator, scenario injection, API ingress/dedupe | unit-tested, sandbox-verified |
| 1 | Deteksi Gangguan | Monitoring severity dan persist run/event | unit-tested |
| 2 | Analisis Dampak | Coverage, stockout, loss deterministik | unit-tested |
| 3 | Pencarian Solusi | Vendor comparison dan feasibility economics | unit-tested, sandbox-verified |
| 4 | Analisis & Keputusan | Orchestrator memilih rekomendasi; model hanya menulis rationale | unit-tested, synth-only |
| 5 | Human-in-the-Loop | Viewer/approver authorization, explicit confirmation, revise/reject | unit-tested, sandbox-verified, Playwright |
| 6 | Eksekusi Purchase Order | Mock SAP PO execution, confirmation, tracking dan KPI | unit-tested, sandbox-verified; SAP live belum diverifikasi |

## Validasi dan batas deployment

CI pada SHA fase 16 `e9ad348` hijau. Validasi lokal saat audit ini: backend **113 passed**, dashboard
**8 passed**, Playwright **6 passed**, Ruff lint/format lulus, dashboard production build dan E2E
typecheck lulus, serta CDK synth + AwsSolutions checks lulus. `npm audit` tidak menemukan kerentanan;
`pip-audit` terhadap locked runtime requirements juga tidak menemukan kerentanan yang diketahui;
secret-pattern scan atas source/docs menemukan **0 hit**. Docker Compose config tidak dapat divalidasi
lokal karena Docker CLI/Engine tidak tersedia pada Windows; job CI yang menyediakan Docker menjadi
validator.

CDK synth menargetkan Python 3.12 Linux x86_64 dan memaketkan dependencies. Synthesis tidak membuktikan
asset dijalankan Lambda. Suppressions cdk-nag yang ada memiliki alasan tertulis; review akun target,
WAF, VPC flow logs, secret rotation, Bedrock permissions, retention, biaya, dan network paths tetap
menjadi deployment gate. Tidak ada AWS/SAP live deployment atau certification.
