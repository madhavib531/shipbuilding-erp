import { apiRequest } from "./client";

type Envelope<T> = { status: string; message: string; data: T };
export type AssistantStatus = { enabled: boolean; model: string | null; tools: string[] };
export type AiAnswer = { answer: string; tools_used: { tool: string; input: Record<string, unknown> }[]; model: string };
export type Turn = { role: "user" | "assistant"; content: string };

export const getAssistantStatus = async (signal?: AbortSignal) =>
  (await apiRequest<Envelope<AssistantStatus>>("/api/v1/assistant/status", { signal })).data;

export const askAssistant = async (question: string, history: Turn[]) =>
  (await apiRequest<Envelope<AiAnswer>>("/api/v1/assistant/ask", { method: "POST", body: JSON.stringify({ question, history }) })).data;
