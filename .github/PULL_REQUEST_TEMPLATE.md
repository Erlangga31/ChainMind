## Ringkasan

<!-- Jelaskan tujuan perubahan secara singkat. -->

## Perubahan

- Ringkasan perubahan:

## Validasi

- [ ] `uv run pytest -q`
- [ ] `uv run ruff check src tests scripts infra`
- [ ] `uv run ruff format --check src tests scripts infra`
- [ ] `npm ci` dan `npm run build` dari `dashboard/` (bila UI berubah)
- [ ] `npx --yes aws-cdk synth` dari `infra/` (bila infrastruktur berubah)

## Pemeriksaan

- [ ] Tidak ada secret atau `.env` yang ditambahkan.
- [ ] PO tetap memerlukan persetujuan manusia sebelum dieksekusi.
- [ ] Dokumentasi/API diperbarui bila relevan.
