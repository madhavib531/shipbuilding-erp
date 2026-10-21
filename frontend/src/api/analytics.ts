import { apiRequest } from "./client";

/** Rule-based figures computed from stored records (no AI model). Ratios are null when there is nothing to divide by. */
export type AnalyticsOverview = {
  generated_at: string;
  categories: { category: string; batches: number; with_available: number; with_reserved: number; stock_but_none_available: number }[];
  aging: { label: string; batches: number }[];
  suppliers: {
    supplier_id: string; supplier: string; orders: number; orders_delivered: number; first_delivery_on_time: number;
    on_time_rate: number | null; deliveries: number; received_quantity: number; rejected_quantity: number; rejection_rate: number | null;
  }[];
  transfers: { window_days: number; received: number; with_shortage: number; average_lead_time_hours: number | null; in_transit: number; in_transit_overdue: number };
  inspections: { window_days: number; holds_opened: number; quantity_held: number; quantity_released: number; quantity_rejected: number; rejection_rate: number | null; open: number };
  attention: { key: string; title: string; rule: string; page: string; count: number; examples: string[] }[];
};

type Envelope<T> = { status: string; message: string; data: T };

export async function getAnalyticsOverview(signal?: AbortSignal) {
  return (await apiRequest<Envelope<AnalyticsOverview>>("/api/v1/analytics/overview", { signal })).data;
}
