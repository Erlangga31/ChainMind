# Catatan packaging marketplace (belum diajukan)

> ChainMind belum terdaftar atau diajukan ke AWS Marketplace maupun SAP Store. Ini adalah daftar
> prasyarat packaging, bukan klaim persetujuan, sertifikasi, atau kesiapan komersial.

## AWS Marketplace

- Pertimbangkan model **SaaS contract listing** setelah security review, dukungan operasional,
  subscription lifecycle, pricing approval, dan legal review selesai.
- Nilai usage demo dihitung lokal dari run `EXECUTED` dan jumlah agent aktif. Implementasi produksi
  perlu tenant onboarding/entitlement yang terverifikasi dan integrasi AWS Marketplace Metering API
  (misalnya `BatchMeterUsage`) dengan retries, idempotency, dan rekonsiliasi; itu belum ada.
- Jangan mengirim metering dari fixture atau simulator sebagai billable usage.
- Ganti nilai plan ilustratif dengan harga, unit, batas, kebijakan overage, dan onboarding yang telah
  disetujui. Invoice dashboard saat ini hanya estimasi demonstrasi.

## SAP Store

- Evaluasi listing setelah arsitektur tenant, SAP Integration Suite package, authentication,
  connectivity, support lifecycle, compatibility matrix, dan persyaratan SAP Store tervalidasi.
- Kontrak `/ariba/*` adalah ChainMind custom adapter API melalui Integration Suite, bukan kontrak
  universal SAP Ariba. Implementasi harus melalui sertifikasi dan uji tenant SAP yang berwenang.
- Belum ada listing, sertifikasi, atau submission.

## Gerbang rilis sebelum submission

1. Validasi tenant isolation, IAM, data residency, audit retention, incident response, dan privacy.
2. Ganti semua angka ilustratif dengan commercial terms yang disetujui.
3. Jalankan uji integrasi pada akun AWS/SAP staging yang disetujui dan dokumentasikan bukti.
4. Lengkapi support/SLA, metering reconciliation, upgrade policy, onboarding, dan proses offboarding.
