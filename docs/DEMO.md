# Skrip demo ChainMind untuk juri

Durasi yang disarankan: **5 menit**. Demo berjalan offline dengan adapter mock; gunakan hanya data fixture yang disediakan.

| Waktu | Fokus |
| --- | --- |
| 0:00–0:45 | Gangguan cuaca, coverage stok, dan severity |
| 0:45–1:45 | Linimasa enam tahap, impact panel, dan perbandingan vendor |
| 1:45–2:30 | Chain of Thought trace, source labels, dan draft PO |
| 2:30–3:30 | Feed notifikasi, role viewer/approver, dan konfirmasi approval |
| 3:30–4:30 | Eksekusi mock, konfirmasi Ariba, ASN, ETA, dan tracking |
| 4:30–5:00 | KPI ilustratif, batas verifikasi, dan langkah produksi |

## Persiapan sebelum presentasi

1. Jalankan `uv sync --extra dev` dan `cd dashboard; npm ci`.
2. Dari root, jalankan `.\scripts\run_all.ps1` (Windows) atau `uv run python scripts/run_all.py`.
3. Tunggu pesan siap, lalu buka `http://127.0.0.1:5173`. API, sandbox SAP/OIDC, dan Vite berjalan lokal dalam mock mode; tidak membutuhkan AWS/SAP atau akses internet saat demo.
4. Masuk sebagai `approver` dengan password `demo`. Bahasa awal dashboard Indonesia; kontrol `EN`
   mengganti dashboard ke Inggris. Ini fake OIDC sandbox, bukan login ke SAP IAS/Cognito produksi.
5. Untuk menghentikan semua proses gunakan `Ctrl+C` di terminal launcher.

## Alur presentasi

1. **Narasi masalah:** kapal pengangkut Microchip X tertunda **5 hari** karena cuaca ekstrem; stok SAP S/4HANA hanya mencakup **3 hari** produksi.
2. Login dengan `approver` / `demo`. Dalam bahasa Indonesia, panel skenario menampilkan **Cuaca ekstrem**; tekan **Picu gangguan demo**.
3. Baca feed notifikasi berbahasa Indonesia yang menyebut Microchip X terlambat 5 hari, stok cukup 3 hari, dan rekomendasi Vendor B $135.000. Tombol **Setujui** tetap meminta review dan konfirmasi eksplisit.
4. Tunjukkan enam tahap dan panel dampak: severity **High**, coverage **3 hari**, stockout tanpa tindakan **2 hari**, biaya inaction ilustratif **$200.000**.
5. Pada tabel vendor dan grafik, bandingkan empat pilihan. **Vendor B** tiba dalam **2 hari**; Vendor A $120.000/3 hari, Vendor C $110.000/4 hari, Vendor D $100.000/5 hari. Harga terendah tidak selalu memiliki biaya total terendah.
6. Tunjukkan **Chain of Thought summary** dan sumber SAP S/4HANA, SAP Ariba, serta Amazon Bedrock mock; hitungan ekonomi tetap deterministik di Python.
7. Pastikan PO berstatus **PENDING_APPROVAL**: Vendor B, **5.000 pcs**, **$27/pcs**, total **$135.000**, terms **Air Freight**.
8. Klik **Setujui** di feed (atau **Tinjau persetujuan** di kartu PO). Dialog muncul; tandai checkbox konfirmasi lalu tekan **Konfirmasi keputusan**. Tidak ada tindakan finansial yang terjadi sebelum konfirmasi.
9. Verifikasi **Eksekusi & pelacakan**: eksekusi SAP mock, konfirmasi pemasok, ASN/ETA **2 hari**, dan proyeksi stok. Tegaskan ini simulasi lokal, bukan transaksi SAP nyata.
10. Klik tab **KPI**. Label halaman menyebut angka sebagai *ilustratif/simulasi*; KPI bukan hasil produksi atau forecast.
11. Penutup: dashboard, IdP, SAP S/4HANA, Ariba, Event Mesh, dan PO adapter adalah sandbox/mock. Tidak ada AWS deployment atau akun SAP yang digunakan.

## Fallback jika jaringan terganggu

Launcher memakai localhost dan adapter mock; ia tidak memerlukan layanan cloud. Bila dashboard atau browser gagal, jalankan `uv run python scripts/run_demo.py` (Indonesia) atau `uv run python scripts/run_demo.py --language en` dari root untuk enam tahap, perbandingan vendor, Chain of Thought, draf PO, audit, dan status approval yang sama. Screenshot lokal di bawah `docs/screenshots/` dapat dipakai untuk menjelaskan tampilan, bukan sebagai bukti transaksi produksi.

## Rationale fixture demo

- Stock: 3.000 pcs; konsumsi harian: 1.000 pcs; coverage = `3.000 / 1.000 = 3 hari`.
- Kapal terlambat 5 hari; perkiraan stockout tanpa tindakan = `5 - 3 = 2 hari`.
- Estimasi kerugian inaction = `2 × $100.000/hari = $200.000`.
- Vendor A: $120.000, pengiriman 3 hari; ada risiko residual pada safety reserve.
- **Vendor B: $135.000, pengiriman 2 hari; total risk-adjusted terendah.**
- Vendor C dan D lebih lambat sehingga estimasi kerugian residual mereka lebih besar pada fixture.
- Draf Vendor B = `5.000 × $27 = $135.000`, `PENDING_APPROVAL`.

Angka adalah hasil dataset demo dan asumsi mock, bukan penawaran SAP Ariba atau rekomendasi pengadaan yang tervalidasi produksi.
