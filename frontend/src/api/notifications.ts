import { apiRequest } from "./client";

export type StoredNotification = {
  id: number;
  kind: string;
  title: string;
  body: string | null;
  page: string | null;
  record: string | null;
  created_at: string;
  read_at: string | null;
};

type Envelope<T> = { status: string; message: string; data: T };

export async function listNotifications(signal?: AbortSignal) {
  return (await apiRequest<Envelope<{ notifications: StoredNotification[]; unread: number; email_enabled: boolean }>>("/api/v1/notifications?limit=20", { signal })).data;
}
export const markNotificationRead = (id: number) => apiRequest<Envelope<{ updated: number }>>(`/api/v1/notifications/${id}/read`, { method: "POST" });
export const markAllNotificationsRead = () => apiRequest<Envelope<{ updated: number }>>("/api/v1/notifications/read-all", { method: "POST" });
