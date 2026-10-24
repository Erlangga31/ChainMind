# ChainMind — outline pitch hackathon

## Slide 1 — Masalah manufaktur

- JIT dan rantai pasok global membuat keterlambatan komponen kecil berisiko menghambat produksi.
- Contoh demo: kapal Microchip X terlambat lima hari, sementara fixture stok hanya mencakup tiga hari.
- Analisis gangguan, stok, logistik, dan vendor sering tersebar lintas sistem.

## Slide 2 — Mengapa AWS dan SAP

- SAP S/4HANA dan SAP Ariba diposisikan sebagai sistem sumber data/stok dan pemasok.
- AWS memetakan event, compute, orkestrasi, penyimpanan audit, identitas, dan agentic AI.
- Integrasi SAP BTP, Event Mesh, Integration Suite, dan IAS adalah target arsitektur; koneksi yang berjalan pada demo ini adalah sandbox, bukan tenant produksi.

## Slide 3 — Arsitektur dan alur

- Event disruption → Monitoring → Logistics → Procurement → Orchestrator → human approval → mock execution/tracking.
- Deterministic Python menghitung coverage, loss, harga, dan pilihan ekonomi; LLM hanya merangkum alasan.
- AWS CDK disintesis lokal; tidak ada AWS resource yang dideploy atau diverifikasi runtime.

## Slide 4 — Live demo

- Login fake OIDC sebagai approver; injeksikan skenario cuaca.
- Perlihatkan stok 3 hari, keterlambatan 5 hari, Vendor B 2 hari / $135,000 / Air Freight.
- PO tetap `PENDING_APPROVAL` sampai pengguna mengonfirmasi; lanjutkan ke status tracking mock.

## Slide 5 — Model bisnis (hipotesis)

- B2B enterprise SaaS / add-on untuk manufaktur otomotif dan elektronik.
- Potensi annual subscription bertier menurut volume gangguan dan agent yang digunakan.
- Onboarding SAP BTP sebagai kemungkinan biaya implementasi satu kali; harga, channel marketplace, dan willingness-to-pay belum tervalidasi.

## Slide 6 — KPI (target ilustratif)

- Waktu respons: berhari-hari manual menjadi target hitungan menit.
- Mitigasi line stoppage: target proses proaktif sebelum buffer utama habis.
- Beban procurement dan konsistensi keputusan: hipotesis untuk pilot.
- Angka dashboard demo berasal dari fixture/simulasi dan bukan hasil pengukuran aktual.

## Slide 7 — Roadmap

- MVP hackathon: offline mock, fake OIDC, dashboard, API, CDK synthesis, dan browser tests.
- Berikutnya: pilot SAP BTP sandbox, verifikasi tenant APIs, identity federation, notification channels, cost and security review.
- Deployment production hanya setelah akses, governance, privacy, dan sign-off pelanggan.

## Slide 8 — Risiko dan batasan

- Data vendor/stok sandbox tidak memprediksi situasi produksi; integrasi SAP dan freshness perlu validasi.
- Keputusan finansial memerlukan persetujuan manusia; tidak ada auto-approval.
- AWS/CDK belum dideploy; Bedrock, Cognito/IAS, Teams/Slack/SES, dan SAP services belum diuji dengan akun nyata.
- Estimasi biaya, model bisnis, marketplace listing, dan KPI produksi masih TBD.
