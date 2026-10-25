# Naskah video demo ChainMind — 3 menit

**Lingkungan:** `mock`, fixture cuaca, login sandbox `approver` / `demo`. Semua SAP/AWS yang tampak
adalah simulasi/sandbox; jangan tampilkan credential atau membuat klaim transaksi nyata.

| Waktu | Aksi layar yang tepat | Narasi |
| --- | --- | --- |
| 0:00–0:15 | Buka `http://127.0.0.1:5173/?presenter=1`; pilih `approver`, masukkan password `demo`, klik **Sign in**. | “ChainMind merespons gangguan pasokan dengan agen terkoordinasi, sambil menjaga keputusan pembelian tetap pada manusia.” |
| 0:15–0:35 | Tunggu halaman **Flow** memuat run cuaca. Tunjuk stage 0–1 dan diamond **Gangguan Signifikan?**. | “Kapal Microchip X tertunda lima hari. Snapshot SAP mock menunjukkan stok hanya cukup tiga hari; Monitoring menandai gangguan signifikan.” |
| 0:35–1:00 | Klik **Lanjut / Next** sekali; tunjuk stage **Analisis Dampak**. | “Logistics menghitung dua hari risiko stockout dan biaya tanpa tindakan ilustratif sebesar 200 ribu dolar.” |
| 1:00–1:25 | Klik **Lanjut / Next**; tunjuk tabel vendor di stage **Pencarian Solusi**. | “Procurement membandingkan empat penawaran. Ranking mempertimbangkan tenggat, kapasitas, biaya, wilayah, dan risiko.” |
| 1:25–1:50 | Klik **Lanjut / Next**; tunjuk rekomendasi Vendor B dan biaya di stage keputusan. | “Vendor B dipilih karena tiba dalam dua hari; total 135 ribu dolar, 5.000 unit dengan Air Freight.” |
| 1:50–2:15 | Klik **Lanjut / Next**; buka **Gangguan** untuk kartu PO, tunjuk DRAFT dan `PENDING_APPROVAL`. | “Ini baru draf. Tidak ada pembelian yang dijalankan sebelum approver meninjau dan memberi persetujuan eksplisit.” |
| 2:15–2:40 | Klik **Lanjut / Next**; jika ingin menunjukkan batas approval, buka **Tinjau persetujuan**, lalu batalkan dialog tanpa menyetujui. | “Approval disinkronkan ke alur kerja mock. Penonton dapat melihat keputusan dan jejak audit.” |
| 2:40–3:00 | Buka **KPI**, tunjuk label ilustratif; tutup pada Flow atau coverage matrix. | “Tracking, ETA, inventaris, deviasi, dan KPI terlihat pada simulasi. AWS hanya synth/LocalStack dan SAP adalah sandbox—belum diuji pada akun nyata.” |

## Fallback

Jika API gagal, login melalui sandbox OIDC, klik **Load recorded replay**, pastikan badge **REPLAY**
tampak, lalu jalankan aksi layar yang sama. Jika UI/browser gagal, jalankan
`uv run python scripts/run_demo.py` dan gunakan screenshot di `docs/screenshots/`; jelaskan bahwa
rekaman bukan transaksi live.
