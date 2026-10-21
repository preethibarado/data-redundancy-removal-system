// TypeScript port of services.py: validate -> detect -> insert, with UNIQUE-constraint safety net.
import { db } from "@/db";
import { students, submissionLogs } from "@/db/schema";
import {
  ACCEPTED,
  detectDuplicates,
  type Classification,
  type MatchInfo,
} from "./duplicateDetector";
import { validateStudent, type CleanStudent, type FieldName, type RawStudent } from "./validators";

export interface SubmissionOutcome {
  classification: Classification;
  accepted: boolean;
  message: string;
  reasons: string[];
  matches: MatchInfo[];
  errors: Partial<Record<FieldName, string>>;
  cleaned: CleanStudent | null;
  storedAt: string | null;
}

async function recordAttempt(outcome: Classification, reasonCode: string) {
  try {
    await db.insert(submissionLogs).values({ outcome, reasonCode: reasonCode.slice(0, 60) });
  } catch {
    console.warn("Could not write submission statistics row");
  }
}

function isUniqueViolation(err: unknown): boolean {
  let e: unknown = err;
  for (let i = 0; i < 4 && e; i++) {
    if (typeof e === "object" && e !== null && (e as { code?: string }).code === "23505") return true;
    e = (e as { cause?: unknown }).cause;
  }
  return false;
}

export async function submitStudent(raw: RawStudent): Promise<SubmissionOutcome> {
  const validation = validateStudent(raw);
  if (!validation.isValid) {
    await recordAttempt("invalid", "invalid:" + Object.keys(validation.errors).sort().join(","));
    return {
      classification: "invalid",
      accepted: false,
      message: "The record was rejected because some fields are invalid.",
      reasons: Object.values(validation.errors).filter((v): v is string => !!v),
      matches: [],
      errors: validation.errors,
      cleaned: validation.cleaned,
      storedAt: null,
    };
  }
  const c = validation.cleaned;
  const base = { errors: {}, cleaned: c, matches: [] as MatchInfo[], reasons: [] as string[], storedAt: null };

  let detection;
  try {
    detection = await detectDuplicates(c);
  } catch (err) {
    console.error("Database error during duplicate check", err);
    await recordAttempt("error", "db_error_check");
    return { ...base, classification: "error", accepted: false, message: "The record was NOT saved because the database could not be reached. Please try again in a moment." };
  }

  if (!ACCEPTED.includes(detection.classification)) {
    await recordAttempt(detection.classification, detection.reasonCode);
    return {
      ...base,
      classification: detection.classification,
      accepted: false,
      message: "The record was rejected and nothing was added to the database.",
      reasons: detection.reasons,
      matches: detection.matches,
    };
  }

  try {
    const [row] = await db
      .insert(students)
      .values({ studentId: c.student_id, fullName: c.full_name, nameKey: c.name_key, email: c.email, department: c.department })
      .returning();
    await recordAttempt(detection.classification, detection.reasonCode);
    return {
      ...base,
      classification: detection.classification,
      accepted: true,
      message:
        detection.classification === "unique"
          ? "The record is unique and verified - it was saved to the database."
          : "The record was saved, but it looks similar to an existing student. Please review the warning below.",
      reasons: detection.reasons,
      matches: detection.matches,
      storedAt: row.createdAt.toISOString(),
    };
  } catch (err) {
    if (isUniqueViolation(err)) {
      // A concurrent submission stored the same identifiers first.
      let classification: Classification = "exact_duplicate";
      let reasons = [
        "The database UNIQUE constraint blocked this insert: a record with the same student ID or email was saved at the same moment by another submission.",
      ];
      let matches: MatchInfo[] = [];
      try {
        const retry = await detectDuplicates(c);
        if (!ACCEPTED.includes(retry.classification)) {
          classification = retry.classification;
          reasons = [...reasons, ...retry.reasons];
          matches = retry.matches;
        }
      } catch {
        /* keep generic explanation */
      }
      await recordAttempt(classification, "integrity_constraint");
      return { ...base, classification, accepted: false, message: "The record was rejected and nothing was added to the database.", reasons, matches };
    }
    console.error("Database error while inserting a record", err);
    await recordAttempt("error", "db_error_insert");
    return { ...base, classification: "error", accepted: false, message: "The record was NOT saved because of a database error. Please try again." };
  }
}
