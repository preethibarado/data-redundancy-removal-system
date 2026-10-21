"use client";

import Link from "next/link";
import { useActionState } from "react";
import { Badge } from "@/components/Badge";
import { DEPARTMENTS, STUDENT_ID_EXAMPLE } from "@/lib/validators";
import { addStudentAction, type FormState } from "./actions";

const input =
  "w-full rounded-lg border px-3 py-2 outline-none focus:border-[#0f4c81] focus:ring-2 focus:ring-[#0f4c81]/20";

export default function AddStudentForm() {
  const [state, formAction, pending] = useActionState<FormState | null, FormData>(addStudentAction, null);
  const outcome = state?.outcome;
  const errors = outcome?.classification === "invalid" ? outcome.errors : {};
  // Keep typed values only when the user must fix field errors.
  const values = outcome?.classification === "invalid" ? state!.values : {};
  const formKey = state ? String(state.nonce) : "initial";

  const field = (name: keyof typeof errors) =>
    `${input} ${errors[name] ? "border-red-500 bg-red-50" : "border-slate-300"}`;

  return (
    <div className="space-y-6">
      {outcome && outcome.classification !== "invalid" && <ResultPanel state={state!} />}

      {outcome?.classification === "invalid" && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-red-800">
          <div className="mb-1 flex items-center gap-2">
            <Badge c="invalid" /> <b>REJECTED</b>
          </div>
          {outcome.message}
        </div>
      )}

      <form key={formKey} action={formAction} noValidate className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
        <div>
          <label htmlFor="student_id" className="mb-1 block font-medium">
            Student ID <span className="text-red-600" aria-hidden>*</span>
          </label>
          <input id="student_id" name="student_id" defaultValue={values.student_id} maxLength={20} placeholder={STUDENT_ID_EXAMPLE}
            autoComplete="off" className={field("student_id")} aria-invalid={!!errors.student_id} aria-describedby="sid-help sid-err" />
          <p id="sid-help" className="mt-1 text-xs text-slate-500">2–4 letters followed by 3–8 digits, e.g. {STUDENT_ID_EXAMPLE}. Case does not matter.</p>
          {errors.student_id && <p id="sid-err" className="mt-1 text-sm text-red-600">{errors.student_id}</p>}
        </div>
        <div>
          <label htmlFor="full_name" className="mb-1 block font-medium">
            Full name <span className="text-red-600" aria-hidden>*</span>
          </label>
          <input id="full_name" name="full_name" defaultValue={values.full_name} maxLength={100} autoComplete="name"
            className={field("full_name")} aria-invalid={!!errors.full_name} aria-describedby="name-err" />
          {errors.full_name && <p id="name-err" className="mt-1 text-sm text-red-600">{errors.full_name}</p>}
        </div>
        <div>
          <label htmlFor="email" className="mb-1 block font-medium">
            Email address <span className="text-red-600" aria-hidden>*</span>
          </label>
          <input id="email" name="email" type="email" defaultValue={values.email} maxLength={254} autoComplete="email"
            className={field("email")} aria-invalid={!!errors.email} aria-describedby="email-help email-err" />
          <p id="email-help" className="mt-1 text-xs text-slate-500">Stored in lower case, so Ana@Uni.edu and ana@uni.edu are the same address.</p>
          {errors.email && <p id="email-err" className="mt-1 text-sm text-red-600">{errors.email}</p>}
        </div>
        <div>
          <label htmlFor="department" className="mb-1 block font-medium">
            Department <span className="text-red-600" aria-hidden>*</span>
          </label>
          <select id="department" name="department" defaultValue={values.department ?? ""} className={field("department")}
            aria-invalid={!!errors.department} aria-describedby="dep-err">
            <option value="">Choose a department…</option>
            {DEPARTMENTS.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          {errors.department && <p id="dep-err" className="mt-1 text-sm text-red-600">{errors.department}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="submit" disabled={pending}
            className="rounded-lg bg-[#0f4c81] px-4 py-2 font-medium text-white hover:bg-[#0b3a63] disabled:opacity-60">
            {pending ? "Checking…" : "Validate & Save"}
          </button>
          <Link href="/records" className="rounded-lg border border-slate-300 px-4 py-2 hover:bg-slate-50">View records</Link>
        </div>
        <p className="text-xs text-slate-500">The creation timestamp is added automatically by the server.</p>
      </form>
    </div>
  );
}

function ResultPanel({ state }: { state: FormState }) {
  const o = state.outcome;
  const tone = o.accepted
    ? o.classification === "unique" ? "border-emerald-200 bg-emerald-50 text-emerald-900" : "border-amber-200 bg-amber-50 text-amber-900"
    : "border-red-200 bg-red-50 text-red-900";
  return (
    <section aria-live="polite" className="space-y-4" data-classification={o.classification}>
      <h2 className="text-lg font-semibold">Duplicate Detection Result</h2>
      <div className={`rounded-xl border p-4 ${tone}`}>
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <Badge c={o.classification} /> <b>{o.accepted ? "ACCEPTED" : "REJECTED"}</b>
        </div>
        <p>{o.message}</p>
      </div>
      {o.reasons.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="mb-2 font-semibold">Why this decision was made</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm">{o.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
          <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">Submitted (after normalisation)</h3>
          {o.cleaned && (
            <dl className="grid grid-cols-[7rem_1fr] gap-y-1">
              <dt className="text-slate-500">Student ID</dt><dd><code>{o.cleaned.student_id}</code></dd>
              <dt className="text-slate-500">Full name</dt><dd>{o.cleaned.full_name}</dd>
              <dt className="text-slate-500">Email</dt><dd className="break-all">{o.cleaned.email}</dd>
              <dt className="text-slate-500">Department</dt><dd>{o.cleaned.department}</dd>
              {o.storedAt && (<><dt className="text-slate-500">Stored at</dt><dd>{o.storedAt.slice(0, 19).replace("T", " ")} UTC</dd></>)}
            </dl>
          )}
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4 text-sm">
          <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">Matching stored records</h3>
          {o.matches.length === 0 ? (
            <p className="text-slate-500">No related records were found.</p>
          ) : (
            <div className="space-y-2">
              {o.matches.map((m, i) => (
                <div key={i} className="rounded-lg border border-slate-200 p-2">
                  <div className="flex justify-between gap-2">
                    <code>{m.record.student_id}</code>
                    {m.score !== null && <span className="rounded bg-slate-100 px-1.5 text-xs">{Math.round(m.score * 100)}% similar</span>}
                  </div>
                  <div>{m.record.full_name}</div>
                  <div className="text-xs text-slate-500">{m.record.email} · {m.record.department}</div>
                  <div className="mt-1 text-xs italic">{m.reason}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
