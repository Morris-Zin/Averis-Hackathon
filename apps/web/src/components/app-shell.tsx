"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  AlertCircle,
  Bell,
  Boxes,
  CircleHelp,
  FileCheck2,
  Inbox,
  Menu,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import type { QueueView } from "@/lib/contracts";
import { useSession } from "./session-provider";
import { Button, Select, SelectItem } from "./ui";

const queues: { value: QueueView; label: string; icon: typeof Inbox }[] = [
  { value: "all", label: "All cases", icon: Inbox },
  { value: "mismatches", label: "Mismatches", icon: SlidersHorizontal },
  { value: "review", label: "Needs review", icon: CircleHelp },
  { value: "waiting", label: "Waiting", icon: Bell },
  { value: "completed", label: "Completed", icon: FileCheck2 },
];

export function AppShell({
  children,
  activeView = "all",
  onViewChange,
  contentBusy = false,
}: {
  children: ReactNode;
  activeView?: QueueView;
  onViewChange?: (view: QueueView) => void;
  contentBusy?: boolean;
}) {
  const {
    session,
    setActor,
    logout,
    sessionActionPending,
    sessionActionError,
  } = useSession();
  const pathname = usePathname();
  const [mobileNav, setMobileNav] = useState(false);
  const initials =
    session?.actor
      .split(" ")
      .map((part) => part[0])
      .join("")
      .slice(0, 2) ?? "AV";

  return (
    <div className="app-frame">
      <header className="topbar">
        <Button
          className="mobile-menu"
          variant="ghost"
          size="sm"
          aria-label="Toggle navigation"
          aria-controls="project-navigation"
          aria-expanded={mobileNav}
          onClick={() => setMobileNav((value) => !value)}
        >
          {mobileNav ? <X size={20} /> : <Menu size={20} />}
        </Button>
        <Link href="/" className="topbar-brand">
          <span className="topbar-logo">
            <FileCheck2 size={18} />
          </span>
          <span>Averis</span>
        </Link>
        <nav className="topbar-links" aria-label="Global navigation">
          <Link href="/">Your work</Link>
          <Link href="/">Queues</Link>
          <Link href="/?view=mismatches">Mismatches</Link>
        </nav>
        <div className="topbar-actions">
          <div className="reviewer-select">
            <Select
              value={session?.actor ?? ""}
              label="Acting reviewer"
              onValueChange={(actor) => void setActor(actor)}
              disabled={sessionActionPending || contentBusy}
            >
              {(session?.reviewers ?? []).map((reviewer) => (
                <SelectItem key={reviewer} value={reviewer}>
                  {reviewer}
                </SelectItem>
              ))}
            </Select>
          </div>
          <span className="avatar" title={session?.actor}>
            {initials}
          </span>
          <Button
            className="logout-button"
            variant="ghost"
            size="sm"
            disabled={sessionActionPending || contentBusy}
            onClick={() => void logout()}
          >
            Log out
          </Button>
        </div>
      </header>
      {sessionActionError ? (
        <div className="shell-message" role="alert">
          <AlertCircle size={16} />
          {sessionActionError}
        </div>
      ) : null}
      <div className="app-body">
        <aside
          id="project-navigation"
          className={mobileNav ? "sidebar sidebar-open" : "sidebar"}
        >
          <div className="project-identity">
            <span className="project-icon">
              <Boxes size={21} />
            </span>
            <div>
              <strong>Shipping review</strong>
              <span>Document operations</span>
            </div>
          </div>
          <nav aria-label="Project navigation">
            <Link
              className={
                pathname === "/" ? "sidebar-link active" : "sidebar-link"
              }
              href="/"
            >
              <Inbox size={17} />
              <span>Queues</span>
            </Link>
          </nav>
          <div className="sidebar-section">
            <p>Queues</p>
            {queues.map(({ value, label, icon: Icon }) =>
              onViewChange ? (
                <button
                  key={value}
                  type="button"
                  className={
                    activeView === value
                      ? "sidebar-link queue-link active"
                      : "sidebar-link queue-link"
                  }
                  onClick={() => {
                    onViewChange(value);
                    setMobileNav(false);
                  }}
                >
                  <Icon size={16} />
                  <span>{label}</span>
                </button>
              ) : (
                <Link
                  key={value}
                  className="sidebar-link queue-link"
                  href={`/?view=${value}`}
                  onClick={() => setMobileNav(false)}
                >
                  <Icon size={16} />
                  <span>{label}</span>
                </Link>
              ),
            )}
          </div>
          <div className="sidebar-footer">
            <span
              className={!session?.live_enabled ? "live-dot muted" : "live-dot"}
            />
            <div>
              <strong>
                {session?.live_enabled
                  ? "AI processing enabled"
                  : "Controlled demo"}
              </strong>
              <span>
                {session?.live_enabled
                  ? "Mailbox not connected"
                  : "Live AI and mailbox are off"}
              </span>
            </div>
          </div>
        </aside>
        <main className="workspace">{children}</main>
      </div>
    </div>
  );
}

export const queueLabels: Record<QueueView, string> = {
  all: "All cases",
  mismatches: "Mismatches",
  review: "Needs review",
  waiting: "Waiting",
  completed: "Completed",
};
