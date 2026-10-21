"use server";

import { revalidatePath } from "next/cache";
import { submitStudent, type SubmissionOutcome } from "@/lib/submit";

export interface FormState {
  outcome: SubmissionOutcome;
  values: Record<string, string>;
  nonce: number;
}

export async function addStudentAction(_prev: FormState | null, formData: FormData): Promise<FormState> {
  const values = {
    student_id: String(formData.get("student_id") ?? ""),
    full_name: String(formData.get("full_name") ?? ""),
    email: String(formData.get("email") ?? ""),
    department: String(formData.get("department") ?? ""),
  };
  const outcome = await submitStudent(values);
  revalidatePath("/");
  revalidatePath("/records");
  return { outcome, values, nonce: Date.now() };
}
