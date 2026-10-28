# Checklist rehearsal ChainMind

## Sebelum juri masuk

- [ ] Pastikan laptop tersambung listrik dan browser pada zoom 100% (atau presenter mode).
- [ ] Jalankan `.\scripts\run_all.ps1`; tunggu semua pemeriksaan preflight dan health check lulus.
- [ ] Buka `http://127.0.0.1:5173/`; periksa halaman sambutan dalam bahasa Indonesia dan mode terang.
- [ ] Pilih **Mulai**, lalu **Masuk dengan ChainMind SSO**; halaman sandbox harus menampilkan label
      User/Password dan footer bahwa ini bukan SAP IAS asli.
- [ ] Login `approver` / `demo`; periksa halaman Flow. Untuk auto-run, buka
      `http://127.0.0.1:5173/?presenter=1` sebelum login.
- [ ] Periksa nilai skenario: delay 5 hari, coverage 3 hari, Vendor B, 2 hari, $135.000,
      Air Freight, dan `PENDING_APPROVAL`.
- [ ] Pastikan halaman KPI menyebut nilai ilustratif; jangan presentasikan sebagai hasil produksi.
- [ ] Siapkan screenshot cadangan dari [`screenshots/`](./screenshots/), termasuk
      `welcome-id-light.png`, `login-id-light.png`, `idp-id-light.png`, `flow-id.png`, `flow-en.png`,
      `po-approval-id.png`, dan `po-approval.png`.
- [ ] Cetak atau buka [QNA.md](./QNA.md) dan [VIDEO_SCRIPT.md](./VIDEO_SCRIPT.md).
- [ ] Siapkan terminal launcher agar mudah dihentikan dengan `Ctrl+C`.

## Saat demo

- [ ] Ceritakan gangguan sebelum memicu; tunjukkan impact dan perbandingan vendor.
- [ ] Sebutkan bahwa mock pipeline menghitung nilai secara deterministik dan LLM hanya merangkum.
- [ ] Tunjukkan PO pending, baca terms/qty/harga, dan demonstrasikan approval eksplisit.
- [ ] Setelah approval, tunjukkan execution/tracking dan KPI berlabel ilustratif.
- [ ] Gunakan klaim: “SAP sandbox simulating S/4HANA OData and Ariba; AWS verified with LocalStack
      and cdk synth.”

## Jika komponen gagal

| Gejala | Tindakan langsung | Narasi yang jujur |
| --- | --- | --- |
| Preflight merah | Baca port/dependency yang gagal; hentikan proses konflik atau jalankan `npm ci` di `dashboard`. | Demo belum siap, jangan mengklaim layanan aktif. |
| Sandbox OIDC tidak hidup | Hentikan launcher, periksa port 8100, jalankan lagi; bila tetap gagal, buka screenshot login dan Flow. | Screenshot adalah ilustrasi UI, bukan sesi runtime. |
| API tidak terjangkau | Login dan pilih **Load recorded replay** jika banner muncul; replay read-only. | Replay adalah data mock rekaman; approval dan API tidak berjalan. |
| Dashboard tidak dapat dibuka | Tampilkan screenshot Flow/PO dan jalankan `uv run python scripts/run_demo.py`. | CLI membuktikan pipeline mock saja, bukan dashboard live. |
| Approval gagal | Jangan mengklaim eksekusi; jelaskan status tetap pending, tampilkan alur dan catatan verifikasi. | Transaksi finansial tidak pernah dipaksakan demi demo. |
| Akses internet/cloud gagal | Tetap di mock lokal, gunakan replay atau screenshot. | Tidak ada layanan AWS/SAP live yang diperlukan atau dipakai. |

## Setelah sesi

- [ ] Hentikan service launcher dengan `Ctrl+C`.
- [ ] Catat pertanyaan juri yang belum terjawab dan hindari membuat klaim baru yang belum diuji.
- [ ] Pertahankan batas: sandbox SAP, LocalStack/CDK synth AWS, KPI dan pricing ilustratif.
