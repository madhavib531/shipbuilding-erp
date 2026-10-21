import { apiRequest } from "./client";

export type Health = { status: string; message: string; version: string; database: string };

export async function getHealth(signal?: AbortSignal) {
  return apiRequest<Health>("/health", { signal });
}
