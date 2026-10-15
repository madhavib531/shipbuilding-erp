// Prototype identity: there is no authentication yet. This name is shown in the top bar and sent as
// the "actor" on transfer actions, so the audit trail records whoever is using this browser as this user.
export const CURRENT_USER = { name: "Maya Chen", role: "Materials Lead", initials: "MC" } as const;
