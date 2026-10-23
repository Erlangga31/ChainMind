# Model bisnis dan kerangka nilai (draft)

> Draft hipotesis hackathon berdasarkan instruksi tertulis. Proposal PDF tidak tersedia, jadi isi ini bukan kutipan atau validasi terhadap dokumen proposal.

## Pengguna sasaran

- Perencana produksi dan material yang memantau risiko kekurangan bahan.
- Tim procurement yang perlu membandingkan pemasok alternatif.
- Pemimpin operasi/manufaktur yang menyetujui keputusan berdampak finansial.
- Tim transformasi SAP/AWS yang mengintegrasikan sinyal gangguan dan ERP.

## Model layanan yang perlu divalidasi

| Tier | Hipotesis nilai | Batas layanan yang perlu ditentukan |
| --- | --- | --- |
| Demo / Sandbox | Skenario fixture, satu material, adapter mock dan laporan ilustratif | Tanpa koneksi SAP, SLA, atau keputusan pengadaan riil |
| Team | Dashboard multi-pengguna, workflow approval, konfigurasi beberapa material dan kanal notifikasi | Harga, jumlah pengguna, lingkungan, dan SLA TBD |
| Enterprise | Integrasi SAP melalui BTP/Integration Suite, kontrol identitas, audit-retensi, dukungan multi-site | Scope implementasi, keamanan, SLA, dan biaya cloud TBD |

Biaya onboarding/implementasi: **[TBD setelah discovery dan estimasi integrasi]**. Biaya berulang: **[TBD; perlu model berdasarkan site, material, volume event, dan penggunaan layanan AWS]**. Nilai ini bukan harga yang ditawarkan.

## Distribusi dan onboarding

Saluran potensial yang perlu divalidasi: AWS Marketplace untuk distribusi cloud dan SAP Store untuk ekosistem SAP. Listing, sertifikasi, dukungan, perjanjian data, hak merek, serta persyaratan vendor marketplace belum dibuat atau disetujui.

Onboarding hipotetis: discovery proses dan data → konektivitas SAP BTP/Cloud Connector → pemetaan material dan vendor → policy approval → uji sandbox → pilot dengan operator → review KPI. Tidak ada akses SAP tenant nyata dalam demo ini.

## Kerangka KPI

KPI yang tersedia di `GET /kpis` bersifat **simulated/illustrative**: tracked runs, executed runs, line stoppages avoided, illustrative action/inaction cost, dan savings ilustratif. KPI ini memakai seed assumptions; tidak mengukur nilai bisnis aktual dan bukan proyeksi finansial.

Validasi pelanggan nantinya perlu data baseline dan definisi yang disepakati, misalnya waktu dari deteksi ke keputusan, material shortage yang benar-benar dicegah, biaya pengadaan aktual, tingkat override, dan false-positive rate. Owner, periode, sumber, serta formula untuk KPI produksi masih TBD.

## Risiko dan mitigasi awal

| Risiko | Dampak | Mitigasi/proof yang tersedia | Sisa pekerjaan |
| --- | --- | --- | --- |
| Keputusan pengadaan tanpa otorisasi | Komitmen finansial tidak sah | Human approval gate; role check; modal konfirmasi; callback workflow | Hubungkan identitas produksi dan uji SoD |
| Data stok/vendor simulasi tidak akurat | Rekomendasi yang salah | Label mock/illustrative; source trace | Validasi mapping SAP dan freshness |
| Gangguan eksternal palsu/duplikat | Alert dan workflow berulang | HMAC bridge, dedupe key, validasi event | Key rotation, replay window, operasi event bus |
| LLM mengubah perhitungan uang | Keputusan biaya tidak dapat dipercaya | Seleksi vendor dan matematika deterministik di Python | Uji guardrails dan model output di AWS |
| Credential atau PII bocor | Akses tidak sah / pelanggaran privasi | Secrets Manager/CDK, structured logs tanpa input bebas | Threat model, cdk-nag, security review, tenant test |
| Ketergantungan konektivitas AWS/SAP | Workflow tertunda | Retry, DLQ, audit store | Resilience, RTO/RPO, SAP BTP private connectivity |
| Perkiraan KPI dibaca sebagai hasil riil | Klaim bisnis menyesatkan | API/dashboard menandai data simulasi | Persetujuan formula dan data produksi |

## Kerangka pendanaan (placeholder)

- Dana prototipe/pilot: **[TBD]** — menutup engineering, keamanan, dan sandbox integrasi.
- Biaya infrastruktur demo/pilot AWS: **[TBD setelah estimasi region, Bedrock, NAT, log, dan retensi]**.
- Biaya SAP BTP / SAP Integration Suite / SAP Cloud Connector: **[TBD sesuai lisensi dan tenant]**.
- Target milestone dan kebutuhan runway: **[TBD]**.

Tidak ada angka pendanaan, harga, kontrak, atau komitmen komersial yang disimpulkan dari mock data.
