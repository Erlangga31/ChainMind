# Model bisnis, KPI, risiko, dan pendanaan (draft)

> Selaras dengan proposal lokal `docs/reference/ChainMind_Proposal.pdf`. Model, target, biaya, dan KPI
> di bawah adalah hipotesis/placeholder proposal, bukan validasi pelanggan atau hasil produksi.

## Target pasar dan pengguna

- **Target pasar awal:** perusahaan manufaktur otomotif dan elektronik yang memakai SAP dan proses
  Just-In-Time (JIT), dengan paparan pada gangguan pasokan material/komponen.
- **Strategic buyer:** Chief Supply Chain Officer (CSCO) atau Direktur Operasional; fokus pada ROI dan
  pencegahan kerugian akibat gangguan rantai pasok.
- **Daily operator:** Procurement Manager dan Logistics Planner yang bekerja di SAP; fokus pada
  efisiensi kerja harian dan kecepatan meninjau rekomendasi.
- **Pemberi persetujuan:** pemilik workflow bisnis yang berwenang menyetujui transaksi sesuai
  hierarki perusahaan.

Segmen tersebut berasal dari hipotesis proposal dan belum divalidasi melalui wawancara atau pilot.

## Model monetisasi yang diusulkan

Proposal mengusulkan **B2B Enterprise SaaS** dengan:

1. Langganan tahunan yang ditawarkan melalui AWS Marketplace dan/atau SAP Store setelah persyaratan
   marketplace, sertifikasi, kontrak, dan dukungan dipenuhi.
2. Tier harga berdasarkan volume transaksi/gangguan yang diproses dan jumlah Amazon Bedrock Agents
   yang diaktifkan per pelanggan.
3. Biaya onboarding satu kali untuk konfigurasi SAP Integration Suite dan SAP Event Mesh pada tenant
   SAP BTP pelanggan.

Tidak ada harga atau listing marketplace yang telah ditetapkan. Nilai kontrak, batas tiap tier, biaya
implementasi, SLA, dan willingness-to-pay perlu divalidasi. Demo/sandbox bukan tier komersial.

API demo menyediakan tier Starter, Professional, dan Enterprise dengan nilai default yang hanya
berfungsi sebagai ilustrasi konfigurasi. Plan tier dan jumlah agen dapat dioverride per tenant;
metering menghitung run `EXECUTED` pada bulan UTC berjalan, overage, biaya dasar, dan onboarding
satu kali per tenant. Tidak ada
Marketplace Metering API, pembayaran, atau invoice komersial yang terhubung; angka harus diganti dan
disetujui sebelum dipakai untuk keputusan bisnis.

## Dampak dan kerangka KPI

Proposal menargetkan empat area berikut. Targetnya bersifat **ilustratif** dan perlu pilot dengan data
SAP pelanggan; beberapa nilai `GET /kpis` dihitung dari run lokal/simulated, bukan operasi produksi.

| Area dampak | Baseline hipotesis pada proposal | Target/arah yang diusulkan | Implementasi saat ini |
| --- | --- | --- | --- |
| Waktu respons gangguan | Berhari-hari untuk analisis manual lintas sistem | Hitungan menit dari event hingga draf solusi siap ditinjau | API menghitung interval stage deteksi ke stage draf dari timestamp pipeline lokal; bukan SLA/latency AWS. |
| Risiko line-stoppage | Reaktif, berisiko terlambat mencegah stockout | Mitigasi proaktif sebelum stok utama habis | Stockout dan biaya inaction dihitung deterministik dari fixture; hasil nyata belum divalidasi. |
| Beban kerja procurement | Waktu habis untuk firefighting | Lebih banyak fokus pada negosiasi strategis dan hubungan vendor | Perbandingan vendor mock; penghematan jam kerja belum diukur. |
| Kualitas keputusan mitigasi | Rentan bias dan tekanan waktu | Keputusan konsisten dari kalkulasi data komprehensif | Perhitungan ekonomi deterministic; rekomendasi dan savings tidak membuktikan kualitas produksi. |

KPI dashboard membandingkan baseline manual ilustratif dengan metrik ChainMind dari run lokal jika
tersedia (waktu respons, line-stoppage risk teramati, dan konsistensi vendor terpilih). Beban kerja
procurement serta baseline manual tetap target ilustratif. Pilot perlu mendefinisikan baseline,
formula, sumber data, pemilik, periode, tingkat override, serta false-positive rate bersama pelanggan.

## Risiko dan arah mitigasi

| Risiko proposal | Dampak | Arah mitigasi proposal | Bukti/batas saat ini |
| --- | --- | --- | --- |
| Keputusan agent keliru, misalnya vendor tidak optimal | Kerugian biaya atau keterlambatan tambahan | Human-in-the-loop SAP Business Workflow untuk tindakan finansial dan audit reasoning di CloudWatch | Role-gated approval, konfirmasi, audit mock dan CDK scaffold ada; Workflow/CloudWatch live belum diuji. |
| Resistensi Procurement/Logistics | MVP tidak digunakan konsisten setelah pilot | Libatkan pengguna dalam desain UI/UX dan integrasikan ke kanal kerja serta akun SAP yang familiar | Dashboard dan feed lokal ada; usability pilot/omnichannel nyata belum dilakukan. |
| Kompleksitas integrasi SAP pelanggan/on-premise | Implementasi melampaui perkiraan | Mulai dengan sandbox SAP BTP; gunakan SAP Cloud Connector bila koneksi on-premise diperlukan | Sandbox lokal tersedia; BTP, Integration Suite, dan Cloud Connector adalah prerequisite, belum terhubung. |
| Ketergantungan pada Amazon Bedrock/model | Perubahan harga atau kebijakan penyedia | Model-agnostic LLM adapter dan pemilihan model lain yang tersedia di Bedrock | Mock/Bedrock adapter dan config ada; model alternatif, performa, dan biaya belum diuji. |
| Perubahan schema/API SAP BTP atau Integration Suite | Konektor perlu penyesuaian | Ikuti rilis resmi SAP dan jadwalkan regression test berkala | Stub dan contract sandbox ada; siklus rilis tenant belum diuji. |
| Data vendor/stok simulasi tidak akurat | Rekomendasi tidak sesuai keadaan operasi | Validasi freshness, mapping, dan kebijakan terhadap data pelanggan | Seed fixtures diberi label mock; integrasi data riil belum dilakukan. |
| KPI ilustratif dianggap hasil finansial aktual | Klaim bisnis menyesatkan | Beri label target/ilustratif dan tetapkan metrik pilot bersama pelanggan | UI/API memberi label simulated; realisasi penghematan belum ada. |

Tabel ini adalah risk register awal dari proposal, bukan threat model, assessment keamanan formal, atau
sertifikasi kepatuhan.

## Kebutuhan pendanaan dan sumber daya (placeholder)

Proposal meminta angka aktual dilengkapi sebelum pengajuan; belum ada estimasi biaya yang tervalidasi.

- Biaya komputasi dan API AWS selama MVP (Bedrock, Lambda, EventBridge, Step Functions, API Gateway):
  **[TBD berdasarkan region, traffic, model, retensi, dan durasi]**.
- Biaya/lisensi tenant SAP BTP trial, Integration Suite, sandbox S/4HANA, dan Ariba:
  **[TBD sesuai akses dan lisensi SAP]**.
- Sumber daya manusia menurut struktur tim dan estimasi jam per fase roadmap:
  **[TBD setelah pembagian peran dan estimasi engineering]**.
- Cadangan validasi calon pengguna (wawancara Procurement Manager manufaktur otomotif/elektronik):
  **[TBD berdasarkan jumlah sesi dan kebutuhan perjalanan]**.

Tidak ada angka pendanaan, biaya cloud, harga, kontrak, ataupun komitmen komersial yang disimpulkan
dari data fixture. Sebelum pilot, estimasi harus memakai asumsi tenant/region, volume event, model,
retensi audit, dan kebutuhan konektivitas yang nyata.
