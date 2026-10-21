import { apiRequest } from "./client";

/** Ledger entries per month. Counted, not summed: batches use different units. */
export type MovementMonth = { month: string; stock_in: number; stock_out: number };
export type Movements = { months: MovementMonth[]; stock_in_types: string[]; stock_out_types: string[] };

export type ShipProgram = {
  id: string;
  name: string;
  yard: string;
  build_status: string;
  build_progress: number;
  allocated_batches: number;
  reserved_batches: number;
};

type Envelope<T> = { status: string; message: string; data: T };

export async function getMovements(months: number, signal?: AbortSignal) {
  return (await apiRequest<Envelope<Movements>>(`/api/v1/dashboard/movements?months=${months}`, { signal })).data;
}

export async function getShipPrograms(signal?: AbortSignal) {
  return (await apiRequest<Envelope<{ ships: ShipProgram[] }>>("/api/v1/dashboard/ships", { signal })).data.ships;
}
