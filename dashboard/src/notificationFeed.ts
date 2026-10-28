import type { DisruptionRun } from "./types";

export type NotificationKind = "draft_ready" | "approval_overdue" | "tracking_deviation";

export interface GroupedNotification {
  key: string;
  kind: NotificationKind;
  run: DisruptionRun;
  count: number;
  unread: boolean;
}

export function notificationStorageKey(tenantId: string, key: string): string {
  return `chainmind.notifications.read.${tenantId}.${key}`;
}

export function markNotificationRead(
  tenantId: string,
  key: string,
  storage: Pick<Storage, "setItem">,
): void {
  storage.setItem(notificationStorageKey(tenantId, key), "true");
}

export function markNotificationsRead(
  tenantId: string,
  notifications: GroupedNotification[],
  storage: Pick<Storage, "setItem">,
): void {
  for (const notification of notifications) {
    markNotificationRead(tenantId, notification.key, storage);
  }
}

export function groupNotifications(
  runs: DisruptionRun[],
  isRead: (key: string) => boolean = () => false,
): GroupedNotification[] {
  const grouped = new Map<string, GroupedNotification>();
  for (const run of runs) {
    const kinds: NotificationKind[] = [];
    if (run.draft_po) kinds.push("draft_ready");
    if (run.approval_overdue_notified) kinds.push("approval_overdue");
    if (run.execution_tracking?.alert) kinds.push("tracking_deviation");
    for (const kind of kinds) {
      const key = `${run.run_id}:${kind}`;
      const count = run.audit_log.filter(
        (entry) =>
          entry.agent === "notifications" &&
          entry.input_summary.includes(`event=${kind}`),
      ).length;
      const current = grouped.get(key);
      if (current) {
        current.count += Math.max(1, count);
      } else {
        grouped.set(key, {
          key,
          kind,
          run,
          count: Math.max(1, count),
          unread: !isRead(key),
        });
      }
    }
  }
  return [...grouped.values()];
}

export function unreadNotificationCount(
  notifications: GroupedNotification[],
): number {
  return notifications.reduce(
    (count, notification) => count + Number(notification.unread),
    0,
  );
}

export function notificationBadgeLabel(count: number): string {
  return count > 99 ? "99+" : String(count);
}
