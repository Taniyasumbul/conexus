import { ReactNode, useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  BarChart3, BookOpenCheck, Boxes, ChevronDown, FilePlus2, FileStack, FlaskConical, GraduationCap, Hand, LayoutDashboard, LogOut, Menu,
  Moon, Network, Palette, Plus, Settings2, Sun, Tags, X,
} from "lucide-react";
import type { Role } from "@lib/api";
import { ThemePref, useTheme } from "@lib/hooks";
import { Avatar } from "./primitives";

export type ShellUser = { name: string; email: string; role: Role };
const RANK: Record<Role, number> = { sales: 0, legal: 1, admin: 2 };

type NavItem = { to: string; label: string; icon: typeof Tags; hint?: string; role?: Role; end?: boolean };

/* Everyday work first; research, demo and developer pages live under Learn. */
const REPORTS: NavItem[] = [
  { to: "/analytics", label: "Portfolio", hint: "Volume, value, why deals paused", icon: BarChart3 },
  { to: "/ledger", label: "Audit history", hint: "Every decision, hash-chain verified", icon: BookOpenCheck },
];
const LEARN: NavItem[] = [
  { to: "/evaluation", label: "Evaluation", hint: "Results for every research objective", icon: FlaskConical },
  { to: "/annotate", label: "Annotate clauses", hint: "Label real contracts for ground truth", icon: Tags, role: "legal" },
  { to: "/architecture", label: "Architecture", hint: "How the agents fit together", icon: Network },
  { to: "/ui", label: "Component library", hint: "Nexus UI, every component", icon: Boxes },
  { to: "/themes", label: "Colour themes", hint: "Preview other palettes", icon: Palette },
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

function NavMenu({ label, icon: Icon, items }: { label: string; icon: typeof Tags; items: NavItem[] }) {
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const [left, setLeft] = useState(0);
  const ref = useClickOutside(open, () => setOpen(false));
  useEffect(() => setOpen(false), [loc.pathname]);
  const active = items.some((r) => loc.pathname.startsWith(r.to));
  return (
    <div className="nx-menu" ref={ref}>
      <button type="button" className={`nx-toplink ${active ? "active" : ""}`} aria-expanded={open} aria-haspopup="menu"
        onClick={(e) => { setLeft(e.currentTarget.getBoundingClientRect().left); setOpen(!open); }}>
        <Icon size={16} />{label}<ChevronDown size={14} />
      </button>
      {open && (
        <div className="nx-menu__panel nx-menu__panel--left" role="menu" style={{ position: "fixed", top: 58, left }}>
          {items.map((r) => (
            <NavLink key={r.to} to={r.to} className="nx-menu__item" role="menuitem">
              <r.icon size={18} /><span>{r.label}<small>{r.hint}</small></span>
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

export function AppShell({ children, inboxCount, llm, user, onSignOut, bell }: {
  children: ReactNode; inboxCount: number; llm?: string; user: ShellUser; onSignOut: () => void; bell?: ReactNode;
}) {
  const nav = useNavigate();
  const loc = useLocation();
  const [theme, setTheme] = useTheme();
  const [userMenu, setUserMenu] = useState(false);
  const [sheet, setSheet] = useState(false);
  const userRef = useClickOutside(userMenu, () => setUserMenu(false));
  useEffect(() => { setUserMenu(false); setSheet(false); }, [loc.pathname]);

  const allowed = (r: NavItem) => !r.role || RANK[user.role] >= RANK[r.role];
  // Legal and Admin act on the queue; Sales only watches what is waiting on Legal
  const reviewLabel = RANK[user.role] >= RANK.legal ? "Review queue" : "Waiting on Legal";
  const work: NavItem[] = [
    { to: "/", label: "Home", icon: LayoutDashboard, end: true },
    { to: "/contracts", label: "Contracts", icon: FileStack },
    { to: "/review", label: reviewLabel, icon: Hand },
  ];
  const learn = LEARN.filter(allowed);
  const ThemeIcon = THEME_ICON[theme];
  const count = inboxCount > 0 && <span className="nx-toplink__count" aria-label={`${inboxCount} waiting`}>{inboxCount}</span>;

  return (
    <div className="nx-shell">
      <a href="#main" className="nx-skip">Skip to content</a>
      <header className="nx-topbar">
        <div className="nx-topbar__inner">
          <NavLink to="/" className="nx-brand" aria-label="CoNexus home"><Logo /><b>CoNexus</b></NavLink>

          <nav className="nx-topnav" aria-label="Main">
            {work.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end} className="nx-toplink">
                <n.icon size={16} />{n.label}{n.to === "/review" && count}
              </NavLink>
            ))}
            <NavMenu label="Reports" icon={BarChart3} items={REPORTS} />
            <NavMenu label="Learn" icon={GraduationCap} items={learn} />
          </nav>

          <div className="nx-topbar__end">
            <button type="button" className="nx-btn nx-btn--primary nx-btn--sm" onClick={() => nav("/new")} aria-label="Create contract" title="Create contract">
              <Plus size={16} /><span className="nx-hide-sm">Create contract</span>
            </button>
            {bell}
            <button type="button" className="nx-iconbtn" onClick={() => setTheme(THEME_NEXT[theme])}
              aria-label={`Switch to ${THEME_NEXT[theme]} mode`} title={`Switch to ${THEME_NEXT[theme]} mode`}>
              <ThemeIcon size={16} />
            </button>
            <div className="nx-menu" ref={userRef}>
              <button type="button" className="nx-userbtn" aria-expanded={userMenu} aria-haspopup="menu" onClick={() => setUserMenu(!userMenu)} aria-label="Account">
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
                  <NavLink to="/settings" className="nx-menu__item" role="menuitem"><Settings2 size={16} />
                    {user.role === "admin" ? "Policy, team & settings" : "Settings"}
                  </NavLink>
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
          <button type="button" className="nx-btn nx-btn--primary" onClick={() => nav("/new")}><FilePlus2 size={16} />Create contract</button>
          {[...work, ...REPORTS].map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className="nx-menu__item"><n.icon size={18} />{n.label}
              {n.to === "/review" && inboxCount > 0 && <span className="nx-toplink__count" style={{ marginLeft: "auto" }}>{inboxCount}</span>}
            </NavLink>
          ))}
          <NavLink to="/settings" className="nx-menu__item"><Settings2 size={18} />Settings</NavLink>
          <details>
            <summary>Learn</summary>
            {learn.map((n) => <NavLink key={n.to} to={n.to} className="nx-menu__item"><n.icon size={18} />{n.label}</NavLink>)}
          </details>
        </nav>
      )}

      {user.email === "demo@conexus.local" && (
        <div className="nx-demobar" role="status">
          <span>Demo workspace: every customer and deal here is sample data.</span>
          <button type="button" onClick={onSignOut}>Leave demo</button>
        </div>
      )}
      <main className="nx-main" id="main"><div className="nx-page" key={loc.pathname}>{children}</div></main>
    </div>
  );
}
