export default function Header() {
  return (
    <header className="flex h-16 items-center justify-between border-b border-gray-200 px-8">
      <span className="text-sm text-gray-500">
        Shipping Operations
      </span>

      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600 text-sm font-semibold text-white">
        V
      </div>
    </header>
  );
}