import { Suspense } from "react";
import { Home } from "@/components/home";
import { Spinner } from "@/components/ui";

export default function Page() {
  return (
    <Suspense
      fallback={
        <main className="initial-loading">
          <Spinner label="Opening Averis" />
        </main>
      }
    >
      <Home />
    </Suspense>
  );
}
