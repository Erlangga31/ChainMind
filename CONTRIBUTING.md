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

## Rekomendasi perlindungan branch

- Lindungi `main`; wajibkan pull request dan minimal satu reviewer independen.
- Wajibkan CI backend, dashboard, Playwright, CDK synth, serta LocalStack integration sebelum merge.
- Aktifkan resolve-conversation requirement dan larang force-push serta penghapusan branch protected.
- Wajibkan status checks terbaru untuk head SHA; jangan mengizinkan merge saat check belum selesai.
- Gunakan secret scanning dan Dependabot alerts/security updates; tinjau dependency update sebelum merge.
- Batasi bypass aturan ke maintainers yang ditunjuk dan dokumentasikan setiap emergency override.

Dependabot mencakup `uv`/`uv.lock`, `infra` pip requirements, dashboard npm, dan GitHub Actions
melalui [`.github/dependabot.yml`](./.github/dependabot.yml). Workflow lokal tidak dapat
membuktikan bahwa alerts atau branch protection sudah diaktifkan pada pengaturan GitHub.
Sesuaikan nama checks dengan workflow repository setelah perubahan CI.

## Rilis

Setelah pull request release digabung ke `main`, CI hijau, dan pemilik rilis menyetujui tag:

```powershell
git checkout main
git pull --ff-only
git tag -a v1.0.0 -m "Release ChainMind 1.0.0"
git push origin v1.0.0
```

Jangan membuat tag dari branch fitur atau sebelum artefak rilis dan status CI ditinjau.
