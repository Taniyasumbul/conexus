import { ReactNode, useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3, BookOpenCheck, Boxes, ChevronDown, FilePlus2, FileStack, FlaskConical, Hand, LayoutDashboard, LogOut, Menu, Moon,
  Network, Palette, Plus, Settings2, Sun, Tags, X,
} from "lucide-react";
import type { Role } from "@lib/api";
import { ThemePref, useTheme } from "@lib/hooks";
import { Avatar } from "./primitives";

export type ShellUser = { name: string; email: string; role: Role };
const RANK: Record<Role, number> = { sales: 0, legal: 1, admin: 2 };

const MAIN = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/contracts", label: "Contracts", icon: FileStack },
  { to: "/inbox", label: "Inbox", icon: Hand, badge: true },
  { to: "/ledger", label: "Ledger", icon: BookOpenCheck },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
];
const RESEARCH: { to: string; label: string; hint: string; icon: typeof Tags; role?: Role }[] = [
  { to: "/evaluation", label: "Evaluation", hint: "Results for every research objective", icon: FlaskConical },
  { to: "/annotate", label: "Annotate clauses", hint: "Label real contracts for ground truth", icon: Tags, role: "legal" },
  { to: "/architecture", label: "Architecture", hint: "How the agents fit together", icon: Network },
  { to: "/ui", label: "Component library", hint: "Nexus UI, every component", icon: Boxes },
];

export function Logo({ size = 32 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="9" fill="var(--accent)" />
      <path d="M9 11.5a6.5 6.5 0 0 1 11-1.8M23 20.5a6.5 6.5 0 0 1-11 1.8" stroke="#fff" strokeWidth="2.6" fill="none" strokeLinecap="round" />
      <circle cx="21.5" cy="10.5" r="2" fill="#fff" /><circle cx="10.5" cy="21.5" r="2" fill="#fff" />
    </svg>
  );
}

function useClickOutside(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) close(); };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") close(); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDown); document.removeEventListener("keydown", onKey); };
  }, [open, close]);
  return ref;
}

const THEME_NEXT: Record<ThemePref, ThemePref> = { system: "dark", light: "dark", dark: "light" };
const THEME_ICON = { system: Moon, light: Moon, dark: Sun };  // shows what clicking switches to

export function AppShell({ children, inboxCount, llm, user, onSignOut, bell }: {
  children: ReactNode; inboxCount: number; llm?: string; user: ShellUser; onSignOut: () => void; bell?: ReactNode;
}) {
  const nav = useNavigate();
  const loc = useLocation();
  const [theme, setTheme] = useTheme();
  const [research, setResearch] = useState(false);
  const [researchLeft, setResearchLeft] = useState(0);
  const [userMenu, setUserMenu] = useState(false);
  const [sheet, setSheet] = useState(false);
  const researchRef = useClickOutside(research, () => setResearch(false));
  const userRef = useClickOutside(userMenu, () => setUserMenu(false));
  useEffect(() => { setResearch(false); setUserMenu(false); setSheet(false); }, [loc.pathname]);

  const researchItems = RESEARCH.filter((r) => !r.role || RANK[user.role] >= RANK[r.role]);
  const researchActive = researchItems.some((r) => loc.pathname.startsWith(r.to));
  const ThemeIcon = THEME_ICON[theme];

  return (
    <div className="nx-shell">
      <header className="nx-topbar">
        <div className="nx-topbar__inner">
          <NavLink to="/" className="nx-brand" aria-label="CoNexus home"><Logo /><b>CoNexus</b></NavLink>

          <nav className="nx-topnav" aria-label="Main">
            {MAIN.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className="nx-toplink">
                <n.icon size={16} />{n.label}
                {n.badge && inboxCount > 0 && <span className="nx-toplink__count">{inboxCount}</span>}
              </NavLink>
            ))}
            <div className="nx-menu" ref={researchRef}>
              <button type="button" className={`nx-toplink ${researchActive ? "active" : ""}`} aria-expanded={research}
                onClick={(e) => { setResearchLeft(e.currentTarget.getBoundingClientRect().left); setResearch(!research); }}>
                <FlaskConical size={16} />Research<ChevronDown size={14} />
              </button>
              {research && (
                <div className="nx-menu__panel nx-menu__panel--left" role="menu" style={{ position: "fixed", top: 58, left: researchLeft }}>
                  {researchItems.map((r) => (
                    <NavLink key={r.to} to={r.to} className="nx-menu__item" role="menuitem">
                      <r.icon size={18} /><span>{r.label}<small>{r.hint}</small></span>
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
            <NavLink to="/settings" className="nx-toplink"><Settings2 size={16} />Settings</NavLink>
          </nav>

          <div className="nx-topbar__end">
            <button type="button" className="nx-btn nx-btn--primary nx-btn--sm nx-hide-sm" onClick={() => nav("/new")}><Plus size={16} />New contract</button>
            {bell}
            <button type="button" className="nx-iconbtn" onClick={() => setTheme(THEME_NEXT[theme])}
              aria-label={`Switch to ${THEME_NEXT[theme]} mode`} title={`Switch to ${THEME_NEXT[theme]} mode`}>
              <ThemeIcon size={16} />
            </button>
            <div className="nx-menu" ref={userRef}>
              <button type="button" className="nx-userbtn" aria-expanded={userMenu} onClick={() => setUserMenu(!userMenu)} aria-label="Account">
                <Avatar name={user.name} /><span className="nx-hide-sm">{user.name.split(" ")[0]}</span><ChevronDown size={14} className="nx-hide-sm" />
              </button>
              {userMenu && (
                <div className="nx-menu__panel" role="menu">
                  <div className="nx-menu__head">
                    <Avatar name={user.name} size="lg" />
                    <div style={{ minWidth: 0 }}>
                      <b>{user.name}</b>
                      <div className="nx-muted" style={{ fontSize: "var(--text-xs)", overflowWrap: "anywhere" }}>{user.email}</div>
                      <span className="nx-badge nx-badge--info" style={{ marginTop: 6, textTransform: "capitalize" }}>{user.role}</span>
                    </div>
                  </div>
                  <NavLink to="/settings" className="nx-menu__item" role="menuitem"><Settings2 size={16} />Settings</NavLink>
                  <NavLink to="/themes" className="nx-menu__item" role="menuitem"><Palette size={16} />Colour theme</NavLink>
                  <div className="nx-menu__item" style={{ cursor: "default", color: "var(--fg-3)", fontSize: "var(--text-xs)" }}>Language model: {llm ?? "…"}</div>
                  <button type="button" className="nx-menu__item" role="menuitem" onClick={onSignOut}><LogOut size={16} />Sign out</button>
                </div>
              )}
            </div>
            <button type="button" className="nx-iconbtn nx-mobilemenu" onClick={() => setSheet(!sheet)} aria-label="Menu" aria-expanded={sheet}>
              {sheet ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>
        </div>
      </header>

      {sheet && (
        <nav className="nx-sheet" aria-label="Mobile">
          <button type="button" className="nx-btn nx-btn--primary" onClick={() => nav("/new")}><FilePlus2 size={16} />New contract</button>
          {[...MAIN, ...researchItems, { to: "/settings", label: "Settings", icon: Settings2 }].map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className="nx-menu__item"><n.icon size={18} />{n.label}
              {n.to === "/inbox" && inboxCount > 0 && <span className="nx-toplink__count" style={{ marginLeft: "auto" }}>{inboxCount}</span>}
            </NavLink>
          ))}
        </nav>
      )}

      {user.email === "demo@conexus.local" && (
        <div className="nx-demobar" role="status">
          <span>You're exploring a demo with sample deals. Approve escalations, start negotiations, try anything.</span>
          <button type="button" onClick={onSignOut}>Leave demo</button>
        </div>
      )}
      <main className="nx-main"><div className="nx-page" key={loc.pathname}>{children}</div></main>
    </div>
  );
}
