# Audit cakupan ChainMind

## Batas audit

`docs/reference/ChainMind_Proposal.pdf` tidak ada di workspace dan folder referensi diabaikan Git. Karena itu audit ini **tidak mengklaim telah membaca atau membandingkan PDF**. Ini adalah status berbasis requirements tertulis di prompt dan berkas source saat ini. Angka section/figure tidak dapat diverifikasi terhadap proposal asli sampai PDF diberikan secara lokal.

Verification labels:

- **unit-tested**: tes otomatis lokal terhadap core, API, atau adapter mock.
- **sandbox-verified**: kontrak HTTP diuji terhadap simulator SAP lokal, bukan tenant SAP.
- **synth-only**: CDK menghasilkan template; tidak dideploy.
- **needs real AWS or SAP**: memerlukan akun AWS/tenant SAP, akses, kredensial, atau runtime yang belum tersedia.

## Requirement coverage (prompt-derived)

| Area / section dari prompt | Status | Bukti | Tingkat verifikasi dan gap |
| --- | --- | --- | --- |
| 3 — konsep dan skenario | Partially | `src/chainmind/agents/`, `src/chainmind/data/`, `tests/test_demo_pipeline.py` | unit-tested; nilai ekonomi masih fixture dan KPI simulasi |
| 5 — empat agent dan Action Groups | Partially | `src/chainmind/agents/`, `src/chainmind/handlers/action_groups.py`, `infra/chainmind_stack.py` | unit-tested + synth-only; belum ada Bedrock runtime |
| 6 — workflow dan approval callback | Partially | `src/chainmind/workflow/`, `src/chainmind/handlers/approval.py`, `tests/test_workflow.py` | unit-tested + synth-only; belum ada callback AWS nyata |
| 7 — integrasi SAP/Ariba | Partially | `sandbox/sap_sandbox/`, `src/chainmind/integrations/sap/`, `tests/test_sap_sandbox.py` | sandbox-verified; real tenant, authorization, dan API mapping perlu verifikasi |
| 8 — notifikasi dan approval links | Partially | `src/chainmind/notifications/`, `tests/test_notifications.py` | unit-tested; kanal eksternal SES/Teams/Slack belum diverifikasi live |
| 9 — security, audit, observability | Partially | `infra/chainmind_stack.py`, `src/chainmind/integrations/aws/event_store.py`, `tests/test_infra_stack.py` | synth-only + unit-tested; belum ada cdk-nag, deploy, threat model, atau audit tenant |
| 10 — UI/demo control tower | Partially | `dashboard/src/`, `docs/DEMO.md` | unit-tested + build; role picker masih mock, bukan OIDC login |
| 11 — model bisnis/komersialisasi | Partially | `docs/BUSINESS.md` | dokumentasi hipotesis saja; harga/marketplace belum tervalidasi |
| 12 — kerangka KPI | Partially | `src/chainmind/core/models.py`, `GET /kpis`, `dashboard/src/components.tsx` | unit-tested; semua angka ilustratif, tidak ada metrik produksi |
| 13 — isi proposal yang belum tersedia | Not implemented | Tidak dapat dipastikan tanpa PDF | needs source PDF dan klarifikasi section yang dimaksud |
| 15 — risiko | Partially | `docs/BUSINESS.md`, kontrol approval dan HMAC | dokumentasi prompt-derived; belum threat-model/security review formal |

## Six-stage figure (prompt-derived)

| Stage | Implementasi | Verifikasi |
| --- | --- | --- |
| Deteksi Gangguan | Ingest normalisasi, mock feeds, deduplikasi dan monitoring | unit-tested; external provider live perlu verifikasi |
| Analisis Dampak | Coverage, stockout, inaction cost deterministik | unit-tested |
| Pencarian Solusi | Perbandingan vendor, kapasitas, waktu, risiko, biaya | unit-tested; SAP Ariba live perlu verifikasi |
| Analisis & Keputusan | Pilihan deterministik + ringkasan trace | unit-tested; Bedrock Agents synth-only |
| Human-in-the-Loop | Role checks, revisi, reject/approve, task-token scaffold | unit-tested + synth-only; Cognito login dashboard belum dihubungkan |
| Eksekusi Purchase Order | Mock eksekusi setelah approval, konfirmasi/ASN/tracking/KPI | unit-tested; SAP nyata needs real SAP |

## AWS deployment readiness

CDK synth lokal berhasil dengan dummy account/region. Stack memodelkan KMS, VPC/endpoints, Cognito authorizer, API throttling/access logs, CloudTrail, event storage, S3 audit archive, alarms, dan dashboard. Status keseluruhan tetap **synth-only**: tidak ada deploy atau AWS runtime verification.

Sebelum deployment perlu menyelesaikan Lambda runtime dependency packaging, menghubungkan dashboard ke OAuth/Cognito PKCE, menjalankan cdk-nag dan meninjau suppressions, menguji permissions/koneksi Bedrock, mengatur Secrets Manager, meninjau biaya NAT/endpoints, dan memvalidasi SAP BTP/Cloud Connector di tenant nyata. Lihat `docs/DEPLOY.md`.
