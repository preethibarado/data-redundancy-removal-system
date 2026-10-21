// TypeScript port of validators.py - gentle normalisation + server-side validation.

export const DEPARTMENTS = [
  "Computer Science",
  "Information Technology",
  "Electronics and Communication",
  "Electrical Engineering",
  "Mechanical Engineering",
  "Civil Engineering",
  "Business Administration",
  "Mathematics",
  "Physics",
  "Other",
];

export const STUDENT_ID_PATTERN = /^[A-Z]{2,4}[0-9]{3,8}$/;
export const STUDENT_ID_EXAMPLE = "CS2024001";

export type FieldName = "student_id" | "full_name" | "email" | "department";
export type RawStudent = Partial<Record<FieldName, string | null | undefined>>;

export interface CleanStudent {
  student_id: string;
  full_name: string;
  name_key: string;
  email: string;
  department: string;
}

export interface ValidationResult {
  cleaned: CleanStudent;
  errors: Partial<Record<FieldName, string>>;
  isValid: boolean;
}

const LABELS: Record<FieldName, string> = {
  student_id: "Student ID",
  full_name: "Full name",
  email: "Email address",
  department: "Department",
};
const MAX: Record<FieldName, number> = { student_id: 20, full_name: 100, email: 254, department: 100 };

const EMAIL_RE =
  /^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$/;

export const collapseWhitespace = (v: string) => v.split(/\s+/).filter(Boolean).join(" ");
export const makeNameKey = (v: string) => collapseWhitespace(v).normalize("NFKC").toLowerCase();

const isLetter = (ch: string) => /\p{L}/u.test(ch);

export function validateStudent(raw: RawStudent): ValidationResult {
  const errors: ValidationResult["errors"] = {};
  const studentId = String(raw.student_id ?? "").trim().toUpperCase();
  const fullName = collapseWhitespace(String(raw.full_name ?? ""));
  const email = String(raw.email ?? "").trim().toLowerCase();
  let department = collapseWhitespace(String(raw.department ?? ""));

  const values: Record<FieldName, string> = {
    student_id: studentId,
    full_name: fullName,
    email,
    department,
  };
  for (const key of Object.keys(values) as FieldName[]) {
    if (!values[key]) errors[key] = `${LABELS[key]} is required.`;
    else if (values[key].length > MAX[key]) errors[key] = `${LABELS[key]} must be at most ${MAX[key]} characters.`;
  }

  if (!errors.student_id && !STUDENT_ID_PATTERN.test(studentId)) {
    errors.student_id = `Student ID format is invalid. Use 2-4 letters followed by 3-8 digits, for example ${STUDENT_ID_EXAMPLE}.`;
  }

  if (!errors.full_name) {
    const chars = Array.from(fullName);
    const bad = chars.some((ch) => !(isLetter(ch) || " '-.".includes(ch)));
    const letters = chars.filter(isLetter).length;
    if (bad) {
      errors.full_name =
        "Full name may contain only letters, spaces, apostrophes ('), hyphens (-) and periods (.).";
    } else if (letters < 2) {
      errors.full_name = "Full name must contain at least 2 letters.";
    }
  }

  if (!errors.email) {
    const local = email.includes("@") ? email.split("@")[0] : "";
    if (!EMAIL_RE.test(email) || local.length > 64) {
      errors.email = "Email address is not valid. Use the format name@example.com.";
    }
  }

  if (!errors.department) {
    const canonical = DEPARTMENTS.find((d) => d.toLowerCase() === department.toLowerCase());
    if (!canonical) errors.department = "Please choose a department from the list.";
    else department = canonical;
  }

  return {
    cleaned: { student_id: studentId, full_name: fullName, name_key: makeNameKey(fullName), email, department },
    errors,
    isValid: Object.keys(errors).length === 0,
  };
}
