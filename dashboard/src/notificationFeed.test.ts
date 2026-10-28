import { describe, expect, it } from "vitest";
import {
  groupNotifications,
  markNotificationRead,
  markNotificationsRead,
  notificationBadgeLabel,
  notificationStorageKey,
  unreadNotificationCount,
} from "./notificationFeed";
import type { DisruptionRun } from "./types";

function runFixture(): DisruptionRun {
  return {
    run_id: "run-1",
    status: "PENDING_APPROVAL",
    severity: "HIGH",
    significant: true,
    event: {
      title: "Weather delay",
      component_name: "Custom chip",
      delay_days: 4,
      event_type: "weather",
    },
    stages: [],
    vendor_comparison: [],
    material_impacts: [],
    trace_steps: [],
    selected_vendor_id: "vendor-1",
    chain_of_thought: [],
    inventory_snapshot: {
      component_name: "Custom chip",
      current_stock: 50,
      daily_consumption: 10,
      line_stoppage_cost_per_day: 1000,
      purchase_quantity: 200,
    },
    cost_of_inaction: 0,
    audit_log: [
      {
        timestamp: "2026-01-01T00:00:00Z",
        agent: "notifications",
        input_summary: "run_id=run-1; event=draft_ready",
        output_summary: "sent",
        reasoning: "",
      },
      {
        timestamp: "2026-01-01T00:00:00Z",
        agent: "notifications",
        input_summary: "run_id=run-1; event=draft_ready",
        output_summary: "sent",
        reasoning: "",
      },
    ],
    draft_po: {
      po_id: "po-1",
      sap_reference: null,
      vendor_id: "vendor-1",
      vendor_name: "Vendor One",
      component_id: "chip-1",
      component_name: "Custom chip",
      quantity: 200,
      unit_price: 10,
      total_price: 2000,
      currency: "USD",
      terms: "Air",
      status: "PENDING_APPROVAL",
    },
    execution_tracking: null,
    kpis: null,
    error: null,
  };
}

describe("notification feed helpers", () => {
  it("groups repeated notifications by run and event type", () => {
    const notifications = groupNotifications([runFixture(), runFixture()]);

    expect(notifications).toHaveLength(1);
    expect(notifications[0].key).toBe("run-1:draft_ready");
    expect(notifications[0].count).toBe(4);
  });

  it("counts distinct unread notifications and caps the bell label", () => {
    const notifications = groupNotifications(
      Array.from({ length: 101 }, (_, index) => ({
        ...runFixture(),
        run_id: `run-${index}`,
      })),
      (key) => key.startsWith("run-0:"),
    );

    expect(unreadNotificationCount(notifications)).toBe(100);
    expect(notificationBadgeLabel(100)).toBe("99+");
    expect(notificationBadgeLabel(99)).toBe("99");
  });

  it("keeps read state scoped to a tenant", () => {
    expect(notificationStorageKey("tenant-a", "run-1:draft_ready")).not.toBe(
      notificationStorageKey("tenant-b", "run-1:draft_ready"),
    );
    expect(
      groupNotifications([runFixture()], (key) => key === "run-1:draft_ready")[0]
        .unread,
    ).toBe(false);
  });

  it("persists one or all read states using tenant-specific keys", () => {
    const values = new Map<string, string>();
    const storage = {
      setItem: (key: string, value: string) => values.set(key, value),
    };
    const notifications = groupNotifications([
      runFixture(),
      { ...runFixture(), run_id: "run-2" },
    ]);

    markNotificationRead("tenant-a", notifications[0].key, storage);
    markNotificationsRead("tenant-b", notifications, storage);

    expect(values.get("chainmind.notifications.read.tenant-a.run-1:draft_ready")).toBe("true");
    expect(values.get("chainmind.notifications.read.tenant-b.run-1:draft_ready")).toBe("true");
    expect(values.get("chainmind.notifications.read.tenant-b.run-2:draft_ready")).toBe("true");
  });
});
