type StatusBadgeProps = {
  status: string;
};

export default function StatusBadge({ status }: StatusBadgeProps) {
  const styles: Record<string, string> = {
    Analysing: "bg-blue-100 text-blue-700",
    Mismatch: "bg-red-100 text-red-700",
    "No mismatch": "bg-green-100 text-green-700",
    "Needs review": "bg-yellow-100 text-yellow-800",
  };

  return (
    <span
      className={`rounded px-2 py-1 text-xs font-medium ${
        styles[status] ?? "bg-gray-100 text-gray-700"
      }`}
    >
      {status}
    </span>
  );
}