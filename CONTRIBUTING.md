# Berkontribusi

Terima kasih telah tertarik membantu ChainMind. Kontribusi kecil, dokumentasi, pengujian, dan demonstrasi bug semuanya berguna.

## Persiapan dan pemeriksaan

Gunakan Python 3.12, Node.js 20+, `uv`, dan npm:

```powershell
uv sync --extra dev
uv run pytest -q
uv run ruff check src tests scripts infra
uv run ruff format --check src tests scripts infra
cd dashboard
npm ci
npm run build
```

Untuk pekerjaan CDK, instal dependensi `infra/requirements.txt` pada Python environment aktif dan jalankan `npx --yes aws-cdk synth` dari `infra/`. Pemeriksaan lokal memakai mode mock dan tidak memerlukan secret AWS/SAP.

## Mengajukan perubahan

1. Buat perubahan terfokus dan tes untuk perilaku yang diubah.
2. Jangan commit `.env`, credentials, `node_modules`, `.venv`, atau artefak build.
3. Jalankan pemeriksaan backend dan dashboard yang relevan.
4. Buat pull request dengan ringkasan, cara menguji, dan catatan perubahan API/UI atau perilaku.
5. Pastikan keputusan finansial tetap menunggu persetujuan manusia dan jangan mengklaim konektivitas SAP produksi tanpa pengujian nyata.
