import { apiRequest } from "./client";

export type Role = "Admin" | "Storekeeper" | "Procurement" | "Inspector" | "Viewer";
export const ROLES: Role[] = ["Admin", "Storekeeper", "Procurement", "Inspector", "Viewer"];
export type Permission = "inventory" | "transfers" | "receiving" | "procurement" | "inspect" | "hold" | "users";

export const ROLE_SUMMARY: Record<Role, string> = {
  Admin: "Everything, including user accounts",
  Storekeeper: "Inventory, transfers, receiving goods, holding stock for inspection",
  Procurement: "Suppliers and purchase orders",
  Inspector: "Inspection holds and decisions",
  Viewer: "Read-only",
};

export type UserAccount = {
  id: number;
  username: string;
  display_name: string;
  email: string | null;
  role: Role;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
};
export type Me = UserAccount & { permissions: Permission[] };

type Envelope<T> = { status: string; message: string; data: T };

export async function login(username: string, password: string) {
  return (await apiRequest<Envelope<{ token: string; expires_at: string; user: Me }>>("/api/v1/auth/login", {
    method: "POST", body: JSON.stringify({ username, password }),
  })).data;
}

export const logout = () => apiRequest<Envelope<null>>("/api/v1/auth/logout", { method: "POST" });
export const getMe = async (signal?: AbortSignal) => (await apiRequest<Envelope<Me>>("/api/v1/auth/me", { signal })).data;
export const changePassword = (current_password: string, new_password: string) =>
  apiRequest<Envelope<null>>("/api/v1/auth/password", { method: "POST", body: JSON.stringify({ current_password, new_password }) });

export const listUsers = async () => (await apiRequest<Envelope<UserAccount[]>>("/api/v1/users")).data;
export const createUser = async (body: { username: string; display_name: string; role: Role; password: string; email?: string }) =>
  (await apiRequest<Envelope<UserAccount>>("/api/v1/users", { method: "POST", body: JSON.stringify(body) })).data;
export const updateUser = async (id: number, body: Partial<Pick<UserAccount, "display_name" | "email" | "role" | "is_active">>) =>
  (await apiRequest<Envelope<UserAccount>>(`/api/v1/users/${id}`, { method: "PATCH", body: JSON.stringify(body) })).data;
export const resetPassword = (id: number, new_password: string) =>
  apiRequest<Envelope<null>>(`/api/v1/users/${id}/password`, { method: "POST", body: JSON.stringify({ new_password }) });
