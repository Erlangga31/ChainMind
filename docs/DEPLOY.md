# Panduan deployment AWS (scaffold)

**Belum siap untuk deployment produksi.** Infrastruktur di bawah ini belum pernah dideploy atau diuji terhadap akun AWS nyata. Jangan jalankan `make deploy` atau `make destroy` tanpa review biaya dan persetujuan pemilik akun.

## Prasyarat

- Python 3.12, Node.js 22, AWS CDK v2, dan koneksi paket saat CDK menyiapkan asset Lambda.
- Asset Lambda memuat source ChainMind dan wheel Linux x86_64 untuk Python 3.12 dari
  `infra/lambda-requirements.txt`; arsitektur Lambda saat ini x86_64. Synth pertama mengunduh
  dependency tersebut dan menyimpan cache lokal di `infra/.lambda-package/`.
- Akun dan region AWS dengan izin membuat VPC/NAT Gateway, API Gateway, Cognito, Lambda, DynamoDB, S3, KMS, CloudTrail, Bedrock, Step Functions, EventBridge, CloudWatch, dan Secrets Manager.
- Aktifkan akses ke foundation model Bedrock pada region yang sama, setujui permintaan akses model bila diperlukan, lalu atur context `bedrockModelId`. Pastikan role Lambda hanya memperoleh aksi Bedrock yang diperlukan.
- SAP BTP tenant dengan SAP Integration Suite, API Management/destination dan OAuth client; SAP Event Mesh service instance/queue/webhook; SAP Cloud Connector atau private connectivity yang disetujui organisasi; SAP IAS/Cognito issuer dan callback HTTPS. Detail endpoint serta scope harus dikonfirmasi oleh pemilik SAP.
- Akun AWS yang dapat membuat KMS keys, VPC endpoints, NAT Gateway, CloudTrail multi-region, Cognito hosted UI, CloudWatch logs, Bedrock Agents/Guardrail, dan service-linked roles. Estimasikan biaya sebelum membuat resource.

## Checklist sebelum deployment

1. Tinjau perubahan stack dan estimasi biaya VPC dua AZ, NAT Gateway, interface endpoints, Bedrock, CloudTrail, KMS, dan log retention.
2. Bootstrap sekali untuk akun/region target: `cd infra`, lalu `npx --yes aws-cdk bootstrap aws://ACCOUNT/REGION`.
3. Tinjau output `cdk-nag AwsSolutions`; semua suppressions yang ada mempunyai alasan eksplisit. Selesaikan setiap finding baru, jangan menambah blanket suppression.
4. Siapkan viewer/approver di Cognito dan konfigurasi MFA, recovery, domain, serta OAuth callback HTTPS. Demo OIDC lokal tidak sama dengan verifikasi Cognito/IAS produksi.
5. Buat secret `chainmind/event-bridge` dan `chainmind/notification-links` di Secrets Manager. Atur `CHAINMIND_EVENT_BRIDGE_SECRET`, token SAP, dan key notifikasi lewat secret references. Jangan menaruh credential nyata dalam `.env`, CDK context, atau repository.
6. Aktifkan akses model Bedrock pada region target; tinjau agent instructions, action groups, guardrail, kuota, dan biaya token.
7. Konfigurasikan SAP Integration Suite, Event Mesh, Cloud Connector/private connectivity, destination, OAuth scopes, IAS/Cognito, serta Teams/Slack webhook atau SES verified sender.
8. Tinjau IAM least privilege, KMS key policies, CloudTrail, VPC flow logging, WAF, alarms, API throttling, retention, secret rotation, dan disaster recovery. Lambda asset saat ini menargetkan Linux x86_64/Python 3.12; uji pada akun staging sebelum produksi.
9. Tinjau template terakhir: `npx --yes aws-cdk synth`. Hanya setelah persetujuan biaya dan keamanan, deploy dengan `npx --yes aws-cdk deploy`.

## Validasi yang tersedia

`npx --yes aws-cdk synth` hanya memvalidasi template dan menyiapkan asset Lambda lokal; ia tidak membuktikan bahwa AWS menerima atau menjalankan package tersebut. Pytest memeriksa resource dan isi package target. Tidak ada tahap deploy, panggilan AWS runtime, provisioning SAP, atau verifikasi end-to-end AWS dalam workspace ini.

### LocalStack integration checks

The optional Compose profile exercises AWS SDK service contracts against a local emulator. It does
not create AWS resources or use a real AWS account:

```powershell
docker compose --profile integration up -d localstack
$env:AWS_ENDPOINT_URL = "http://localhost:4566"
$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION = "us-east-1"
uv run pytest tests/integration -m integration -q
docker compose --profile integration stop localstack
```

CI runs the same marked suite in the **LocalStack integration** job. The tests cover EventBridge
publication/rule configuration, DynamoDB idempotency and run storage, S3 trace/audit archival,
Step Functions task-token approval via SQS, an SQS dead-letter queue contract, Secrets Manager reads,
SES message acceptance, and a full mock-SAP/mock-LLM disruption pipeline persisted in DynamoDB. These
checks do not prove AWS IAM policy behavior, service quotas, delivery to external email, or equivalence
with AWS production. The EventBridge test calls the Lambda-shaped handler locally; it does not prove
an actual Lambda container invocation. LocalStack results remain distinct from real-AWS verification.

### Kontrak SAP dan smoke test opt-in

Kontrak JSON Schema di `contracts/sap/` membedakan nama field standar SAP dari ekstensi khusus
ChainMind. S/4HANA sandbox menyajikan envelope OData V2, metadata EDMX, material stock, purchase
order, dan supplier. Endpoint `/ariba/*` adalah adapter khusus ChainMind melalui Integration Suite,
bukan klaim bahwa semua tenant Ariba menyediakan API OData universal. Periksa kontrak dan mapping
tenant bersama pemilik SAP sebelum membuat destination produksi.

Smoke test live bersifat opt-in dan tidak dijalankan oleh demo atau suite default. Jangan jalankan
perintah ini sebelum pemilik tenant memberikan URL dan kredensial khusus untuk lingkungan uji:

```powershell
$env:SAP_LIVE_BASE_URL = "https://<integration-suite-host>"
$env:SAP_LIVE_TOKEN_URL = "https://<oauth-token-endpoint>"
$env:SAP_LIVE_CLIENT_ID = "<client-id>"
$env:SAP_LIVE_CLIENT_SECRET = "<secret-from-approved-secret-store>"
uv run python scripts/verify_sap_tenant.py
uv run pytest tests/integration/test_live_sap.py -m live_sap -q
```

Script mengambil token client-credentials, memeriksa `$metadata` untuk tiga service OData S/4HANA
serta adapter Ariba, dan melakukan satu GET per service. Path dapat diubah melalui environment
`SAP_LIVE_MATERIAL_METADATA_PATH`, `SAP_LIVE_PURCHASE_ORDER_METADATA_PATH`,
`SAP_LIVE_BUSINESS_PARTNER_METADATA_PATH`, `SAP_LIVE_ARIBA_METADATA_PATH`,
`SAP_LIVE_MATERIAL_READ_PATH`, `SAP_LIVE_PURCHASE_ORDER_READ_PATH`,
`SAP_LIVE_BUSINESS_PARTNER_READ_PATH`, dan `SAP_LIVE_ARIBA_READ_PATH`. Pastikan service hanya
mengizinkan operasi baca untuk smoke test. Output tidak menampilkan token atau secret. Hapus
environment variables setelah selesai; jangan simpan kredensial di `.env` atau Git.

The SAP sandbox/schema tests are `sandbox-verified`; the live smoke test requires a real SAP BTP
Integration Suite tenant and remains **needs real SAP** until explicitly run by its owner.

### AWS account verifier (read-only preflight)

Set AWS credentials through the approved AWS credential provider chain, then configure resource IDs
only if those resources exist in the target account:

```powershell
$env:AWS_REGION = "us-east-1"
$env:CHAINMIND_BEDROCK_MODEL_ID = "<foundation-model-id>"
$env:CHAINMIND_BEDROCK_AGENT_ID = "<agent-id>"
$env:CHAINMIND_BEDROCK_AGENT_ALIAS_ID = "<agent-alias-id>"
$env:CHAINMIND_EVENT_BUS_NAME = "chainmind"
$env:CHAINMIND_STATE_MACHINE_ARN = "<state-machine-arn>"
uv run python scripts/verify_aws_account.py
```

The verifier reads STS identity, the regional Bedrock model catalog, configured Bedrock agent/alias,
EventBridge bus, and Step Functions state machine. A model being listed does **not** prove invocation
access; it never calls `InvokeAgent` or `InvokeModel`. EventBridge `PutEvents` has no AWS dry-run API,
so the verifier explicitly reports that check as skipped and sends no event. Use a separately approved
staging runbook for paid or mutating runtime checks. This script has not been run against a real account.

## Perintah berisiko

- `npx --yes aws-cdk deploy` membuat atau mengubah resource berbayar dan membutuhkan kredensial AWS.
- `npx --yes aws-cdk destroy` menghapus stack; resource dengan retain policy tetap tersimpan dan mungkin tetap menimbulkan biaya.

Keduanya sengaja tidak dijalankan dalam proses pengembangan ini.
