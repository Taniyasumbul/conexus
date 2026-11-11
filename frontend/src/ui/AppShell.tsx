import { ReactNode, useState } from "react";
import { NavLink } from "react-router-dom";
import {
  BookOpenCheck, Boxes, FilePlus2, FileStack, FlaskConical, Hand, LayoutDashboard, Menu, Monitor, Moon, Network, Sun, Tags,
} from "lucide-react";
import { ThemePref, useTheme } from "@lib/hooks";
import { Segmented } from "./primitives";

const NAV = [
  { section: "Workspace" },
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/contracts", label: "Contracts", icon: FileStack },
  { to: "/new", label: "New contract", icon: FilePlus2 },
  { to: "/inbox", label: "Escalation inbox", icon: Hand, badge: "inbox" },
  { to: "/ledger", label: "Audit ledger", icon: BookOpenCheck },
  { section: "Research" },
  { to: "/annotate", label: "Annotate clauses", icon: Tags },
  { to: "/evaluation", label: "Evaluation", icon: FlaskConical },
  { to: "/architecture", label: "Architecture", icon: Network },
  { to: "/ui", label: "Component library", icon: Boxes },
] as const;

function Logo() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="7" fill="var(--accent)" />
      <path d="M9 11.5a6.5 6.5 0 0 1 11-1.8M23 20.5a6.5 6.5 0 0 1-11 1.8" stroke="#fff" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      <circle cx="21.5" cy="10.5" r="2" fill="#fff" /><circle cx="10.5" cy="21.5" r="2" fill="#fff" />
    </svg>
  );
}

export function AppShell({ children, inboxCount, llm }: { children: ReactNode; inboxCount: number; llm?: string }) {
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useTheme();
  return (
    <div className={`nx-shell ${open ? "nav-open" : ""}`}>
      <div className="nx-topbar">
        <button className="nx-btn nx-btn--ghost nx-btn--sm" style={{ color: "inherit" }} onClick={() => setOpen(!open)} aria-label="Open navigation"><Menu size={18} /></button>
        <b style={{ fontFamily: "var(--font-display)" }}>CoNexus</b>
      </div>
      <nav className="nx-nav" aria-label="Main" onClick={() => setOpen(false)}>
        <div className="nx-nav__brand"><Logo /><div><b>CoNexus</b><small>Contract Negotiation Executive</small></div></div>
        {NAV.map((n, i) =>
          "section" in n ? <div key={i} className="nx-nav__section">{n.section}</div> : (
            <NavLink key={n.to} to={n.to} end={"end" in n} className="nx-nav__link">
              <n.icon size={17} />{n.label}
              {"badge" in n && inboxCount > 0 && <span className="nx-nav__count">{inboxCount}</span>}
            </NavLink>
          ),
        )}
        <div className="nx-nav__foot" onClick={(e) => e.stopPropagation()}>
          <Segmented<ThemePref> label="Theme" value={theme} onChange={setTheme} options={[
            { value: "light", label: <Sun size={14} aria-label="Light" /> },
            { value: "system", label: <Monitor size={14} aria-label="System" /> },
            { value: "dark", label: <Moon size={14} aria-label="Dark" /> },
          ]} />
          <span>Model: <code>{llm ?? "…"}</code></span>
        </div>
      </nav>
      <main className="nx-main">{children}</main>
    </div>
  );
}
