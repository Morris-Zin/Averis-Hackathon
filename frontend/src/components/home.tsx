"use client";

import { InboxView } from "./inbox";
import { useSession } from "./session-provider";
import { Spinner } from "./ui";
import { Welcome } from "./welcome";

export function Home() {
  const { status } = useSession();
  if (status === "loading")
    return (
      <main className="initial-loading">
        <Spinner label="Opening Averis" />
      </main>
    );
  if (status !== "ready") return <Welcome />;
  return <InboxView />;
}
