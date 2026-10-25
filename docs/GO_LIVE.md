# Checklist menuju pilot akun nyata

Jangan jalankan langkah deployment sampai pemilik akun menyetujui region, biaya, IAM, data, dan
rollback. Semua perintah `verify_*` bersifat opt-in dan harus dijalankan oleh operator pada akun
yang berwenang. `scripts/validate_config.py` tidak membuat koneksi.

## 1. Bekukan konfigurasi dan bukti lokal

1. Pastikan mode lokal tetap `CHAINMIND_MODE=mock`; jalankan `uv run python scripts/preflight.py`,
   `uv run python scripts/validate_config.py --mode mock`, tes, dan CDK synth.
2. Simpan salinan nilai deployment yang disetujui di secret store organisasi. Jangan menaruh nilai
   rahasia dalam Git, tiket, screenshot, atau output terminal.
3. Tentukan tenant/region, pemilik incident response, retention audit, biaya bulanan maksimum, dan
   kriteria rollback sebelum pilot.

## 2. AWS sandbox dan kesiapan

1. Pilih akun AWS non-produksi dan region; aktifkan akses model Amazon Bedrock yang didukung serta
   konfirmasi kuota/biaya sebelum runtime.
2. Tinjau IAM, KMS, VPC/endpoints, logging, alarms, budget, bucket/table names, dan perubahan CDK.
3. Jalankan `cdk bootstrap <account>/<region>` hanya setelah persetujuan pemilik akun; lalu deploy
   stack sesuai change window. Dokumentasi ini tidak melakukan deploy.
4. Simpan SAP OAuth credentials dan notification signing secret di AWS Secrets Manager; verifikasi
   resource/permissions tanpa mencetak nilai.
5. Atur environment (`CHAINMIND_MODE=aws`, region, bus/table/bucket, Bedrock model/agent IDs,
   secret IDs, notification channels) lalu validasi:
   `uv run python scripts/validate_config.py --mode aws`.
6. Jalankan `uv run python scripts/verify_aws_account.py` dari environment yang punya akses.
   Script memeriksa identitas, katalog model, EventBridge bus dan state machine secara read-only;
   `PutEvents` dry-run tidak mengirim event, dan model invocation tidak dilakukan.
7. Jalankan smoke run berbiaya rendah dengan persetujuan eksplisit. Pastikan log, S3 archive,
   alarms, DLQ, dan jalur approval terpantau sebelum memperluas penggunaan.

## 3. SAP BTP dan konektivitas

1. Sediakan SAP BTP trial/non-production tenant dan konfirmasi hak lisensi/API dengan SAP.
2. Konfigurasikan SAP Integration Suite, API policies/destinations, Event Mesh topic/credentials,
   Cloud Connector bila sistem on-premises, serta IAS app/claims/roles.
3. Buat service user dengan akses minimum; rahasiakan OAuth client secret. Sediakan mapping OData
   dan idempotency policy yang disetujui tim SAP.
4. Validasi tanpa koneksi menggunakan `uv run python scripts/validate_config.py --mode real` setelah
   endpoint dan secret reference diset.
5. Operator SAP menjalankan `uv run python scripts/verify_sap_tenant.py` hanya dengan izin tenant.
   Periksa OAuth, `$metadata`, dan read-only sample requests; jangan membuat/mengeksekusi PO pada
   tahap smoke test.
6. Setujui sandbox transaction test terpisah: draft-only dahulu, approval oleh user SAP yang tepat,
   lalu satu PO dummy yang dapat dibatalkan.

## 4. Notifikasi, approval, dan go/no-go

1. Verifikasi Teams/Slack webhook yang didedikasikan untuk pilot; validasi recipient, redaction, dan
   signed action-link expiry. Untuk SES, verifikasi domain/sender identity dan sandbox quota.
2. Jalankan end-to-end bersama approver SAP; cek role viewer/approver, revise/reject, duplicate
   event, notification delivery, audit trail, ETA deviation, dan rollback.
3. Go-live hanya setelah security, privacy, SAP owner, AWS owner, finance, dan demo/billing owner
   memberi persetujuan tertulis. Tetapkan volume, durasi, kontak on-call, dan stop criteria.

## Rollback dan penghentian

1. Hentikan ingestion/aturan EventBridge terlebih dahulu; pertahankan approval/manual SAP process.
2. Nonaktifkan Lambda/Step Functions sesuai runbook akun; jangan menghapus audit/log/DynamoDB/S3
   sebelum retention/legal hold diperiksa.
3. Cabut/rotasi secret dan OAuth client, webhook, serta token yang mungkin terdampak.
4. Rekonsiliasi setiap draft/PO di SAP secara manual dengan pemilik SAP; jangan menganggap rollback
   infrastruktur membatalkan transaksi SAP.
5. Setelah izin retention, backup, dan billing disetujui, operator dapat menjalankan `cdk destroy`
   pada stack non-produksi. Periksa biaya, snapshot/log, dan resource residual sesudahnya.

**Batas klaim:** sampai semua langkah live dijalankan dan disetujui, ChainMind hanya terverifikasi
melalui unit/sandbox/LocalStack/CDK synth. Checklist ini bukan bukti verifikasi nyata.
