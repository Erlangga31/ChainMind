# Tanya jawab juri ChainMind

## Produk dan demo

### 1. Masalah apa yang diselesaikan?

ChainMind membantu tim manufaktur merespons gangguan pasokan dengan menghitung risiko stok,
membandingkan pemasok alternatif, dan menyiapkan draf PO untuk ditinjau.

### 2. Apa contoh yang didemokan?

Kapal Microchip X terlambat lima hari sementara fixture stok mencakup tiga hari. Pipeline mock
membandingkan empat vendor dan merekomendasikan Vendor B.

### 3. Apakah ini sudah terhubung ke SAP sungguhan?

Belum. SAP sandbox simulating S/4HANA OData and Ariba; AWS verified with LocalStack and cdk synth.
Tidak ada transaksi atau tenant SAP nyata yang dipakai.

### 4. Apa arti angka $135.000?

Nilai draf fixture: 5.000 pcs × $27, dengan Vendor B dan Air Freight. Bukan quote SAP Ariba.

### 5. Apakah sistem otomatis membeli?

Tidak. PO berstatus `PENDING_APPROVAL`; hanya approver yang dapat mengonfirmasi keputusan.

### 6. Apa yang terjadi jika approver menolak atau meminta revisi?

Penolakan menghentikan eksekusi. Revisi vendor memperbarui rekomendasi dan tetap menunggu approval.

## Agent, data, dan AI

### 7. Apa tanggung jawab empat agen?

Monitoring mengklasifikasikan event; Logistics menilai persediaan; Procurement membandingkan
pemasok; Orchestrator memilih opsi ekonomi dan menyiapkan draf.

### 8. Apa yang diputuskan LLM dan apa yang dihitung Python?

Python deterministik menghitung coverage, loss, biaya, feasibility dan ranking. LLM hanya
menyusun ringkasan rationale; ia tidak menghitung uang.

### 9. Bagaimana vendor dipilih?

Mock Procurement membandingkan lead time, harga, kapasitas, risiko dan lokasi. Hasil tergantung
data fixture; belum mewakili kapasitas pemasok aktual.

### 10. Bagaimana dampak multi-material ditangani?

Logistics mengevaluasi bahan komponen BOM yang tersedia di fixture, lalu melaporkan komponen
kritis. Integrasi BOM SAP live belum diaktifkan.

### 11. Apa sumber kebenaran untuk stok?

Dalam demo, data inventory berasal dari SAP sandbox fixture. Target produksi adalah S/4HANA
melalui API yang disepakati dengan tim SAP.

### 12. Apa arti Chain of Thought pada layar?

Itu ringkasan keputusan yang aman untuk audit, bukan hidden chain-of-thought internal model.

## Keamanan dan keandalan

### 13. Bagaimana mencegah PO yang salah?

Ada perbandingan deterministik, status draf, role approver, konfirmasi eksplisit, serta audit.
Sebelum produksi masih diperlukan validasi kebijakan, data, dan kontrol pelanggan.

### 14. Apa yang terjadi bila Bedrock tidak tersedia?

Demo default memakai `MockLLMClient` offline. Adapter Bedrock bersifat opsional; availability,
retry, dan fallback produksi memerlukan konfigurasi dan pengujian akun AWS.

### 15. Bagaimana isolasi multi-tenant bekerja?

API mengikat run dan usage ke claim `tenant_id` JWT dan menguji akses lintas tenant. Hardening
identitas, storage, dan deployment tetap harus direview sebelum produksi.

### 16. Apakah replay dapat mengeksekusi approval?

Tidak. Replay menampilkan fixture rekaman read-only, menandai mode `REPLAY`, dan menonaktifkan
trigger/approval.

### 17. Apa yang diaudit?

Audit run mencatat delapan langkah proposal, keputusan manusia dan tracking; pada konfigurasi
AWS target, arsip disimpan ke S3. Demo lokal tidak membuktikan retensi/immutability produksi.

### 18. Apa risiko utama?

Kualitas dan freshness data, kapasitas vendor, perubahan kontrak SAP, akses lintas sistem,
keamanan tenant, serta estimasi finansial yang belum tervalidasi.

## Verifikasi dan model bisnis

### 19. Apa yang benar-benar telah diuji?

Backend 163 passed / 9 skipped, Vitest 18 passed dan Playwright 11 passed pada verifikasi lokal;
CI juga menjalankan suite backend, dashboard, E2E, LocalStack, compose dan CDK. Lihat
[COVERAGE.md](./COVERAGE.md) untuk tanggal dan level verifikasi terperinci.

### 20. Apakah pricing dan KPI sudah tervalidasi?

Belum. Tier, onboarding, manual baseline, dan target KPI bersifat ilustratif sampai pilot dan
analisis komersial dilakukan.

### 21. Apakah data di-hardcode?

Preset demo memang ditanam sebagai seed deterministik dan hanya dipakai untuk tenant kosong atau
mode presenter. Selain preset itu, analisis berjalan dari data tenant yang dibuat atau diimpor di
Data Studio dan dari event yang dikirim pengguna. Nilai vendor dan hasil KPI bukan konstanta UI.
SAP dan AWS tetap berupa sandbox/mock; bukan integrasi produksi.

## Kalimat klaim yang disetujui

> SAP sandbox simulating S/4HANA OData and Ariba; AWS verified with LocalStack and cdk synth.
