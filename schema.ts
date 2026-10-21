import { index, pgTable, serial, timestamp, uniqueIndex, varchar } from "drizzle-orm/pg-core";

// Mirrors CodeAlpha_DataRedundancyRemoval/models.py (the Flask implementation).
export const students = pgTable(
  "students",
  {
    id: serial("id").primaryKey(),
    studentId: varchar("student_id", { length: 20 }).notNull(),
    fullName: varchar("full_name", { length: 100 }).notNull(),
    nameKey: varchar("name_key", { length: 100 }).notNull(),
    email: varchar("email", { length: 254 }).notNull(),
    department: varchar("department", { length: 100 }).notNull(),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [
    uniqueIndex("uq_students_student_id").on(t.studentId),
    uniqueIndex("uq_students_email").on(t.email),
    index("ix_students_name_key").on(t.nameKey),
    index("ix_students_created_at").on(t.createdAt),
  ],
);

export const submissionLogs = pgTable(
  "submission_logs",
  {
    id: serial("id").primaryKey(),
    outcome: varchar("outcome", { length: 30 }).notNull(),
    reasonCode: varchar("reason_code", { length: 60 }),
    createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index("ix_submission_logs_outcome").on(t.outcome)],
);

export type Student = typeof students.$inferSelect;
