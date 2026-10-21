import { CLASSIFICATION_LABELS, type Classification } from "@/lib/classification";

export const BADGE_STYLES: Record<Classification, string> = {
  unique: "bg-emerald-600 text-white",
  possible_duplicate: "bg-amber-400 text-slate-900",
  exact_duplicate: "bg-red-600 text-white",
  conflict: "bg-fuchsia-700 text-white",
  invalid: "bg-slate-500 text-white",
  error: "bg-slate-800 text-white",
};

export const BAR_STYLES: Record<Classification, string> = {
  unique: "bg-emerald-600",
  possible_duplicate: "bg-amber-400",
  exact_duplicate: "bg-red-600",
  conflict: "bg-fuchsia-700",
  invalid: "bg-slate-500",
  error: "bg-slate-800",
};

export function Badge({ c }: { c: Classification }) {
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${BADGE_STYLES[c]}`}>
      {CLASSIFICATION_LABELS[c]}
    </span>
  );
}
