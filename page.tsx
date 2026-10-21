import AddStudentForm from "./AddStudentForm";

export const metadata = { title: "Add Student · Data Redundancy Removal" };

export default function AddPage() {
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold">Add Student</h1>
      <p className="mb-4 text-slate-600">
        The record is validated on the server, compared with existing data, and stored only if it is unique.
      </p>
      <AddStudentForm />
    </div>
  );
}
