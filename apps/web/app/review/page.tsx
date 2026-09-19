import { Suspense } from "react";
import { ReviewWorkspace } from "@/components/review-workspace";
import { Spinner } from "@/components/ui";

export default function ReviewPage() {
  return <Suspense fallback={<main className="initial-loading"><Spinner label="Opening review" /></main>}><ReviewWorkspace /></Suspense>;
}
