# Skrip demo ChainMind untuk juri

Durasi yang disarankan: **5 menit**. Demo berjalan offline dengan adapter mock; gunakan hanya data fixture yang disediakan.

| Waktu | Fokus |
| --- | --- |
| 0:00–0:45 | Gangguan cuaca, coverage stok, dan severity |
| 0:45–1:45 | Linimasa enam tahap, impact panel, dan perbandingan vendor |
| 1:45–2:30 | Chain of Thought trace, source labels, dan draft PO |
| 2:30–3:30 | Viewer/Approver demo, revise/reject atau konfirmasi approve |
| 3:30–4:30 | Eksekusi mock, konfirmasi Ariba, ASN, ETA, dan tracking |
| 4:30–5:00 | KPI ilustratif, batas verifikasi, dan langkah produksi |

## Persiapan sebelum presentasi

1. Jalankan `uv sync --extra dev`.
2. Terminal pertama: `uv run uvicorn chainmind.api.main:app --app-dir src --reload`.
3. Terminal kedua: `cd dashboard`, `npm ci`, lalu `npm run dev`.
4. Buka dashboard di URL Vite dan pastikan label **MOCK MODE** terlihat. Role selector adalah simulasi lokal, bukan login SSO sungguhan.
5. Bila API/UI bermasalah saat presentasi, jalankan `uv run python scripts/run_demo.py` untuk demo CLI alternatif.

## Alur presentasi

1. **Jelaskan gangguan:** kapal Microchip X terlambat 5 hari karena cuaca ekstrem; stok yang tersedia hanya menutup 3 hari produksi.
2. Klik **Trigger demo disruption**. Run yang baru akan muncul di panel kiri.
3. Tunjukkan linimasa enam tahap: Deteksi Gangguan, Analisis Dampak, Pencarian Solusi, Analisis & Keputusan, Human-in-the-Loop, dan Eksekusi Purchase Order. Monitoring mengklasifikasikan severity **High**; Logistics menghitung cakupan 3 hari, potensi stockout 2 hari, dan estimasi kerugian akibat tidak bertindak sebesar **$200.000**.
4. Buka tabel vendor: ada empat alternatif. Bandingkan harga saja dengan waktu kirim, kapasitas, dan risiko residual—Vendor yang termurah tidak otomatis paling ekonomis.
5. Tunjukkan grafik biaya vs waktu kirim, skor risiko, dan biaya aksi vs inaction. Orchestrator memilih **Vendor B**: lead time 2 hari, $135.000 action cost, dan tidak ada residual stockout pada fixture; alternatif layak berikutnya Vendor A memiliki biaya tersesuaikan risiko $139.500.
6. Baca **Chain of Thought summary** sebagai ringkasan keputusan audit: bukti yang digunakan, risiko stockout, perbandingan pemasok, biaya inaction vs action, dan alasan rekomendasi.
7. Tunjukkan draf SAP S/4HANA: **Vendor B**, Microchip X, **5.000 pcs**, **$27/pcs**, total **$135.000**, **Air Freight**, `PENDING_APPROVAL`.
8. Tekankan gerbang human-in-the-loop: tidak ada order yang dijalankan hanya karena agent merekomendasikannya.
9. Ubah role ke **Approver**, masukkan catatan lalu tekan **Revise vendor**, pilih Vendor A, dan konfirmasi pada dialog. Draf berubah, catatan revisi tercatat, tetapi status tetap `PENDING_APPROVAL`.
10. Pilih apakah ingin **Reject** untuk membuktikan tidak ada eksekusi, atau **Review approval** lalu centang konfirmasi eksplisit untuk memperlihatkan jalur persetujuan pada mock SAP. Approval menghasilkan nomor referensi mock dan audit entry manusia.
11. Setelah approval, tunjukkan tahap **Execution & tracking**: Ariba mengonfirmasi 5.000 pcs, ASN menampilkan ETA vendor 2 hari, dan proyeksi terpisah menunjukkan 6.000 pcs/6 hari cakupan saat barang tiba. Jelaskan bahwa angka ini simulasi dan tidak mengubah saldo stok SAP saat ini.
12. Tampilkan KPI biaya inaction, biaya aksi, dan savings ilustratif; endpoint `GET /kpis` hanya mengagregasi run yang selesai tracking dan bukan proyeksi finansial. CloudWatch dashboard hanya tersedia setelah stack AWS dideploy; demo lokal tidak mengklaim akses CloudWatch.
13. Tunjukkan notifikasi console untuk draft dan signed links. Tekankan bahwa membuka approve link tidak mengeksekusi PO; API tetap meminta role approver dan konfirmasi eksplisit. Pengingat overdue berjalan melalui pemeriksaan berkala; jangan menunggu ambang 24 jam saat demo.

## Rationale fixture demo

- Stock: 3.000 pcs; konsumsi harian: 1.000 pcs; coverage = `3.000 / 1.000 = 3 hari`.
- Kapal terlambat 5 hari; perkiraan stockout tanpa tindakan = `5 - 3 = 2 hari`.
- Estimasi kerugian inaction = `2 × $100.000/hari = $200.000`.
- Vendor A: $120.000, pengiriman 3 hari; ada risiko residual pada safety reserve.
- **Vendor B: $135.000, pengiriman 2 hari; total risk-adjusted terendah.**
- Vendor C dan D lebih lambat sehingga estimasi kerugian residual mereka lebih besar pada fixture.
- Draf Vendor B = `5.000 × $27 = $135.000`, `PENDING_APPROVAL`.

Angka adalah hasil dataset demo dan asumsi mock, bukan penawaran SAP Ariba atau rekomendasi pengadaan yang tervalidasi produksi.
