import { History } from "lucide-react";
import type { CaseView } from "@/lib/contracts";

export function ActivityPanel({ history }: { history: CaseView["history"] }) {
  return (
    <section className="activity-section">
      <div className="section-heading">
        <div>
          <h2>Activity</h2>
          <p>
            Classification, corrections, assignments, and workflow changes are
            retained.
          </p>
        </div>
      </div>
      <ol>
        {history.map((entry, index) => (
          <li key={`${entry.at}-${index}`}>
            <span className="activity-icon">
              <History size={15} />
            </span>
            <div>
              <p>
                <strong>{entry.actor}</strong> · {entry.action}
              </p>
              <span>{entry.detail}</span>
              <small>{new Date(entry.at).toLocaleString()}</small>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
