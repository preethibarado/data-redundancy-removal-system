// TypeScript port of duplicate_detector.py.
import { eq, or, sql } from "drizzle-orm";
import { db } from "@/db";
import { students, type Student } from "@/db/schema";
import { makeNameKey, type CleanStudent } from "./validators";

import type { Classification } from "./classification";
export { ACCEPTED, CLASSIFICATION_LABELS, type Classification } from "./classification";

export const RULES = {
  enablePossibleDuplicateCheck: process.env.ENABLE_POSSIBLE_DUPLICATE_CHECK !== "false",
  nameSimilarityThreshold: Number(process.env.NAME_SIMILARITY_THRESHOLD ?? 0.85),
  maxCandidates: 500,
  maxMatchesShown: 5,
};

export interface MatchRecord {
  student_id: string;
  full_name: string;
  email: string;
  department: string;
}
export interface MatchInfo {
  record: MatchRecord;
  matchedOn: string;
  reason: string;
  score: number | null;
}
export interface DetectionResult {
  classification: Classification;
  reasons: string[];
  matches: MatchInfo[];
  reasonCode: string;
}

const toRecord = (s: Student): MatchRecord => ({
  student_id: s.studentId,
  full_name: s.fullName,
  email: s.email,
  department: s.department,
});

// --- Ratcliff/Obershelp similarity (same algorithm as Python difflib.SequenceMatcher.ratio)
function matchingChars(a: string, b: string): number {
  if (!a.length || !b.length) return 0;
  let best = 0;
  let bi = 0;
  let bj = 0;
  let prev = new Array<number>(b.length + 1).fill(0);
  for (let i = 1; i <= a.length; i++) {
    const cur = new Array<number>(b.length + 1).fill(0);
    for (let j = 1; j <= b.length; j++) {
      if (a[i - 1] === b[j - 1]) {
        cur[j] = prev[j - 1] + 1;
        if (cur[j] > best) {
          best = cur[j];
          bi = i - best;
          bj = j - best;
        }
      }
    }
    prev = cur;
  }
  if (!best) return 0;
  return (
    best +
    matchingChars(a.slice(0, bi), b.slice(0, bj)) +
    matchingChars(a.slice(bi + best), b.slice(bj + best))
  );
}
const ratio = (a: string, b: string) => (a.length + b.length ? (2 * matchingChars(a, b)) / (a.length + b.length) : 0);

export function nameSimilarity(a: string, b: string): number {
  const ka = makeNameKey(a);
  const kb = makeNameKey(b);
  if (!ka || !kb) return 0;
  const sortWords = (s: string) => s.split(" ").sort().join(" ");
  return Math.round(Math.max(ratio(ka, kb), ratio(sortWords(ka), sortWords(kb))) * 1000) / 1000;
}

function differences(existing: Student, c: CleanStudent): string[] {
  const d: string[] = [];
  if (existing.email !== c.email) d.push("email address");
  if (existing.nameKey !== c.name_key) d.push("full name");
  if (existing.department !== c.department) d.push("department");
  return d;
}

export async function detectDuplicates(c: CleanStudent): Promise<DetectionResult> {
  const [byId] = await db.select().from(students).where(eq(students.studentId, c.student_id)).limit(1);
  const [byEmail] = await db.select().from(students).where(eq(students.email, c.email)).limit(1);

  if (byId || byEmail) {
    if (byId && byEmail && byId.id === byEmail.id) {
      const diffs = differences(byId, c);
      if (diffs.length === 0) {
        return {
          classification: "exact_duplicate",
          reasons: [
            `Student ID ${byId.studentId} with email ${byId.email} is already stored with identical details. Saving it again would only create a redundant copy, so it was rejected.`,
          ],
          matches: [{ record: toRecord(byId), matchedOn: "student_id+email", reason: "Same student ID, email, name and department", score: null }],
          reasonCode: "exact_duplicate",
        };
      }
      return {
        classification: "conflict",
        reasons: [
          `Student ID ${byId.studentId} and this email are already registered, but the stored ${diffs.join(", ")} is different. The same identifiers cannot describe two different sets of details, so it was rejected. If the stored data is wrong, correct the existing record instead.`,
        ],
        matches: [{ record: toRecord(byId), matchedOn: "student_id+email", reason: `Same identifiers, different ${diffs.join(", ")}`, score: null }],
        reasonCode: "conflict_identifiers",
      };
    }
    const reasons: string[] = [];
    const matches: MatchInfo[] = [];
    if (byId) {
      const diffs = differences(byId, c);
      reasons.push(
        `Student ID ${byId.studentId} already belongs to a stored record whose ${diffs.join(", ")} is different. A student ID must identify exactly one student.`,
      );
      matches.push({ record: toRecord(byId), matchedOn: "student_id", reason: `Same student ID, different ${diffs.join(", ")}`, score: null });
    }
    if (byEmail) {
      reasons.push(
        `Email ${byEmail.email} is already registered to student ID ${byEmail.studentId}. An email address can belong to only one student.`,
      );
      matches.push({ record: toRecord(byEmail), matchedOn: "email", reason: `Same email, different student ID (${byEmail.studentId})`, score: null });
    }
    reasons.push("The record was rejected to keep the database consistent.");
    return {
      classification: "conflict",
      reasons,
      matches,
      reasonCode: byId && byEmail ? "conflict_both" : byId ? "conflict_student_id" : "conflict_email",
    };
  }

  if (RULES.enablePossibleDuplicateCheck) {
    const tokens = c.name_key.split(" ").filter((t) => t.length >= 2).slice(0, 5);
    if (tokens.length) {
      const escape = (t: string) => t.replace(/[\\%_]/g, (m) => "\\" + m);
      const candidates = await db
        .select()
        .from(students)
        .where(or(...tokens.map((t) => sql`${students.nameKey} like ${"%" + escape(t) + "%"}`)))
        .limit(RULES.maxCandidates);
      const matches: MatchInfo[] = [];
      for (const cand of candidates) {
        const score = nameSimilarity(c.full_name, cand.fullName);
        if (score < RULES.nameSimilarityThreshold) continue;
        matches.push({
          record: toRecord(cand),
          matchedOn: "name",
          score,
          reason:
            score === 1
              ? `Same name as stored student ${cand.studentId} (${cand.fullName}), but with a different student ID and email.`
              : `Name is ${Math.round(score * 100)}% similar to stored student ${cand.studentId} (${cand.fullName}).`,
        });
      }
      matches.sort((x, y) => (y.score ?? 0) - (x.score ?? 0));
      if (matches.length) {
        const shown = matches.slice(0, RULES.maxMatchesShown);
        return {
          classification: "possible_duplicate",
          reasons: [
            ...shown.map((m) => m.reason),
            "The student ID and email are new, so this record was ACCEPTED. Different students can share a name - please just double-check it is not the same person.",
          ],
          matches: shown,
          reasonCode: "similar_name",
        };
      }
    }
  }

  return {
    classification: "unique",
    reasons: [
      "No stored record uses this student ID or email address, and no similar name was found. The record is unique and verified.",
    ],
    matches: [],
    reasonCode: "unique",
  };
}
