import { useCallback, useEffect, useState } from "react";

type Entity = "materials" | "vendors" | "shipments" | "events";
type Request = <T>(path: string, init?: RequestInit) => Promise<T>;

type DataStudioProps = {
  request: Request;
  requestText: (path: string) => Promise<string>;
  language: "id" | "en";
};

const entities: Entity[] = ["materials", "vendors", "shipments", "events"];
const idFields: Record<Entity, string> = {
  materials: "component_id",
  vendors: "vendor_id",
  shipments: "shipment_id",
  events: "event_id",
};

export function DataStudio({ request, requestText, language }: DataStudioProps) {
  const [entity, setEntity] = useState<Entity>("materials");
  const [records, setRecords] = useState<Record<string, unknown>[]>([]);
  const [recordJson, setRecordJson] = useState("{}");
  const [recordId, setRecordId] = useState("");
  const [importContent, setImportContent] = useState("");
  const [format, setFormat] = useState<"json" | "csv">("json");
  const [generatorSeed, setGeneratorSeed] = useState("1");
  const [generatorSize, setGeneratorSize] = useState("3");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const isId = language === "id";
  const t = (id: string, en: string) => isId ? id : en;

  const refresh = useCallback(async () => {
    setRecords(await request<Record<string, unknown>[]>(`/data/${entity}`));
  }, [entity, request]);

  useEffect(() => {
    void refresh().catch((error: unknown) => setMessage(error instanceof Error ? error.message : String(error)));
  }, [refresh]);

  async function saveRecord(method: "POST" | "PUT") {
    setBusy(true);
    setMessage("");
    try {
      const record = JSON.parse(recordJson) as Record<string, unknown>;
      const key = String(record[idFields[entity]] ?? "");
      if (method === "PUT" && !key) throw new Error(t("ID record wajib diisi untuk mengedit.", "Record ID is required to edit."));
      await request(`/data/${entity}${method === "PUT" ? `/${encodeURIComponent(key)}` : ""}`, {
        method,
        body: JSON.stringify(record),
      });
      setRecordId(key);
      setMessage(t("Data tersimpan.", "Record saved."));
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function removeRecord() {
    if (!recordId) return;
    setBusy(true);
    setMessage("");
    try {
      await request(`/data/${entity}/${encodeURIComponent(recordId)}`, { method: "DELETE" });
      setRecordId("");
      setMessage(t("Data dihapus.", "Record deleted."));
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function importRecords() {
    setBusy(true);
    setMessage("");
    try {
      const result = await request<{ imported: number; errors: { row: number; message: string }[] }>(
        `/data/${entity}/import`,
        { method: "POST", body: JSON.stringify({ format, content: importContent }) },
      );
      setMessage([
        t(`${result.imported} baris diimpor.`, `${result.imported} rows imported.`),
        ...result.errors.map((error) => `${t("Baris", "Row")} ${error.row}: ${error.message}`),
      ].join("\n"));
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function download(path: string, filename: string) {
    try {
      const content = await requestText(path);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([content], { type: "application/octet-stream" }));
      link.download = filename;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }

  async function runAction(path: string, body?: object, method = "POST") {
    setBusy(true);
    setMessage("");
    try {
      const result = await request<Record<string, number>>(path, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      setMessage(JSON.stringify(result));
      await refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  async function loadFile(file?: File) {
    if (!file) return;
    setImportContent(await file.text());
    setFormat(file.name.toLowerCase().endsWith(".csv") ? "csv" : "json");
  }

  return (
    <section className="flex min-h-0 flex-col gap-4 overflow-hidden rounded-2xl bg-white p-5 shadow-card" aria-label="Data Studio">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-ink">{t("Data Studio", "Data Studio")}</h2>
          <p className="text-sm text-slate-500">{t("Data tersimpan dibatasi per tenant.", "Stored data is scoped to your tenant.")}</p>
        </div>
        <label className="text-sm">
          {t("Jenis data", "Data type")}
          <select className="ml-2 rounded-lg border border-slate-300 p-2" value={entity} onChange={(event) => setEntity(event.target.value as Entity)}>
            {entities.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
      </header>
      <div className="grid min-h-0 flex-1 gap-4 overflow-hidden xl:grid-cols-2">
        <div className="flex min-h-0 flex-col gap-3 overflow-hidden">
          <div className="flex flex-wrap gap-2">
            <button type="button" className="rounded-lg bg-accent px-3 py-2 text-sm font-semibold text-white" disabled={busy} onClick={() => void saveRecord("POST")}>{t("Tambah", "Create")}</button>
            <button type="button" className="rounded-lg border px-3 py-2 text-sm font-semibold" disabled={busy} onClick={() => void saveRecord("PUT")}>{t("Simpan perubahan", "Save changes")}</button>
            <button type="button" className="rounded-lg border border-rose-300 px-3 py-2 text-sm font-semibold text-rose-700" disabled={busy || !recordId} onClick={() => void removeRecord()}>{t("Hapus terpilih", "Delete selected")}</button>
          </div>
          <label className="min-h-0 flex-1 text-sm font-medium">
            {t("Record JSON (Pydantic tervalidasi API)", "Record JSON (validated by API)")}
            <textarea aria-label={t("Record JSON", "Record JSON")} className="mt-1 h-full min-h-36 w-full resize-none rounded-lg border border-slate-300 p-3 font-mono text-xs" value={recordJson} onChange={(event) => {
              setRecordJson(event.target.value);
              try {
                const parsed = JSON.parse(event.target.value) as Record<string, unknown>;
                setRecordId(String(parsed[idFields[entity]] ?? ""));
              } catch {
                setRecordId("");
              }
            }} />
          </label>
        </div>
        <div className="flex min-h-0 flex-col gap-3 overflow-hidden">
          <div className="flex flex-wrap items-center gap-2">
            <select aria-label={t("Format impor", "Import format")} value={format} onChange={(event) => setFormat(event.target.value as "json" | "csv")} className="rounded-lg border border-slate-300 p-2">
              <option value="json">JSON</option><option value="csv">CSV</option>
            </select>
            <label className="rounded-lg border px-3 py-2 text-sm">
              {t("Pilih file", "Choose file")}
              <input aria-label={t("Pilih file impor", "Choose import file")} className="sr-only" type="file" accept=".json,.csv" onChange={(event) => void loadFile(event.target.files?.[0])} />
            </label>
            <button type="button" className="rounded-lg border px-3 py-2 text-sm" disabled={busy || !importContent} onClick={() => void importRecords()}>{t("Impor", "Import")}</button>
            <button type="button" className="rounded-lg border px-3 py-2 text-sm" onClick={() => void download(`/data/${entity}/template?format=${format}`, `${entity}-template.${format}`)}>{t("Template", "Template")}</button>
            <button type="button" className="rounded-lg border px-3 py-2 text-sm" onClick={() => void download(`/data/${entity}/export?format=${format}`, `${entity}.${format}`)}>{t("Ekspor", "Export")}</button>
          </div>
          <textarea aria-label={t("Konten impor", "Import content")} className="h-24 shrink-0 rounded-lg border border-slate-300 p-3 font-mono text-xs" value={importContent} onChange={(event) => setImportContent(event.target.value)} />
          <div className="flex flex-wrap gap-2">
            <label className="flex items-center gap-1 text-xs">{t("Seed", "Seed")}<input aria-label={t("Seed generator", "Generator seed")} className="w-20 rounded-lg border p-2" type="number" value={generatorSeed} onChange={(event) => setGeneratorSeed(event.target.value)} /></label>
            <label className="flex items-center gap-1 text-xs">{t("Ukuran", "Size")}<select aria-label={t("Ukuran dataset", "Dataset size")} className="rounded-lg border p-2" value={generatorSize} onChange={(event) => setGeneratorSize(event.target.value)}><option value="1">1</option><option value="3">3</option><option value="5">5</option><option value="10">10</option></select></label>
            <button type="button" className="rounded-lg border px-3 py-2 text-sm" disabled={busy || !generatorSeed.trim()} onClick={() => void runAction("/data/actions/generate", { seed: Number(generatorSeed), size: Number(generatorSize) })}>{t("Buat dataset contoh", "Generate sample dataset")}</button>
            <button type="button" className="rounded-lg border px-3 py-2 text-sm" disabled={busy} onClick={() => void runAction("/data/actions/reset-demo")}>{t("Reset ke demo", "Reset to demo")}</button>
            <button type="button" className="rounded-lg border border-rose-300 px-3 py-2 text-sm text-rose-700" disabled={busy} onClick={() => void runAction("/data", undefined, "DELETE")}>{t("Hapus semua", "Clear all data")}</button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto rounded-lg border border-slate-200" tabIndex={0} role="region" aria-label={t("Daftar data tenant", "Tenant data records")}>
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-100"><tr><th className="p-2">{t("ID", "ID")}</th><th className="p-2">{t("Ringkasan", "Summary")}</th><th className="p-2">{t("Asal data", "Data origin")}</th></tr></thead>
              <tbody>{records.map((record, index) => <tr key={`${String(record[idFields[entity]])}-${index}`} className="border-t">
                <td className="max-w-32 truncate p-2">{String(record[idFields[entity]] ?? "")}</td>
                <td className="max-w-52 truncate p-2">{String(record.component_name ?? record.vendor_name ?? record.status ?? record.title ?? "")}</td>
                <td className="p-2">{String(record.data_origin ?? "user")}</td>
              </tr>)}</tbody>
            </table>
          </div>
        </div>
      </div>
      {message && <pre role="status" className="max-h-24 shrink-0 overflow-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-3 text-xs">{message}</pre>}
    </section>
  );
}
