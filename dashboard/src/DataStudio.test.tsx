import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DataStudio } from "./DataStudio";

function renderStudio() {
  const calls: { path: string; init?: RequestInit }[] = [];
  const request = async <T,>(path: string, init?: RequestInit): Promise<T> => {
    calls.push({ path, init });
    if (path === "/data/materials/import") {
      return { imported: 1, errors: [{ row: 2, message: "daily_consumption must be positive" }] } as T;
    }
    return [] as T;
  };
  const requestText = vi.fn(async () => "[]");
  render(<DataStudio request={request} requestText={requestText} language="en" />);
  return { calls, requestText };
}

describe("tenant Data Studio", () => {
  it("creates a user-supplied material through the validated API", async () => {
    const { calls } = renderStudio();
    const record = {
      component_id: "CUSTOM-1",
      component_name: "Custom microchip",
      plant: "Plant 7",
      unit: "pcs",
      current_stock: 900,
      daily_consumption: 150,
      safety_stock: 100,
      line_stoppage_cost_per_day: 25000,
      bom_relations: [],
    };

    fireEvent.change(screen.getByRole("textbox", { name: "Record JSON" }), {
      target: { value: JSON.stringify(record) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(calls).toContainEqual({ path: "/data/materials", init: {
        method: "POST",
        body: JSON.stringify(record),
      } });
    });
    expect(await screen.findByRole("status")).toHaveTextContent("Record saved.");
  });

  it("reports row-level validation errors when importing records", async () => {
    const { calls } = renderStudio();

    fireEvent.change(screen.getByRole("textbox", { name: "Import content" }), {
      target: { value: '[{"component_id":"CUSTOM-1"}]' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Import" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Row 2: daily_consumption must be positive",
    );
    expect(calls).toContainEqual({ path: "/data/materials/import", init: {
      method: "POST",
      body: JSON.stringify({
        format: "json",
        content: '[{"component_id":"CUSTOM-1"}]',
      }),
    } });
  });

  it("updates and deletes a selected record by its tenant-scoped key", async () => {
    const { calls } = renderStudio();
    const record = { component_id: "CUSTOM-2", component_name: "Updated part" };
    fireEvent.change(screen.getByRole("textbox", { name: "Record JSON" }), {
      target: { value: JSON.stringify(record) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(calls).toContainEqual({ path: "/data/materials/CUSTOM-2", init: {
        method: "PUT",
        body: JSON.stringify(record),
      } });
    });
    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));

    await waitFor(() => {
      expect(calls).toContainEqual({
        path: "/data/materials/CUSTOM-2",
        init: { method: "DELETE" },
      });
    });
  });
});
