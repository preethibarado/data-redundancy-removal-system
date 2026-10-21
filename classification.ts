// Shared (client-safe) classification types and labels.
export type Classification =
  | "unique"
  | "possible_duplicate"
  | "exact_duplicate"
  | "conflict"
  | "invalid"
  | "error";

export const CLASSIFICATION_LABELS: Record<Classification, string> = {
  unique: "Unique record",
  possible_duplicate: "Possible duplicate (accepted with warning)",
  exact_duplicate: "Exact duplicate",
  conflict: "Conflicting record",
  invalid: "Invalid record",
  error: "Not saved (database error)",
};

export const ACCEPTED: Classification[] = ["unique", "possible_duplicate"];
