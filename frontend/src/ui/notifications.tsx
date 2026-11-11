/* Nexus UI - notification bell with dropdown. Data is passed in; the app fetches it. */
import { useEffect, useRef, useState } from "react";
import { Bell, CheckCheck, FileSignature, Hand, ThumbsUp, XCircle } from "lucide-react";
import { ago } from "@lib/api";

export type NotificationItem = { id: number; kind: string; title: string; body: string; link: string | null; created_at: number; read: boolean };

const KIND = {
  escalation: { icon: Hand, tone: "critical" },
  signed: { icon: FileSignature, tone: "good" },
  approved: { icon: ThumbsUp, tone: "info" },
  closed: { icon: XCircle, tone: "neutral" },
} as const;

export function NotificationBell({ items, unread, onOpenItem, onReadAll }: {
  items: NotificationItem[]; unread: number; onOpenItem: (n: NotificationItem) => void; onReadAll: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", esc); };
  }, [open]);

  return (
    <div className="nx-menu" ref={ref}>
      <button type="button" className="nx-iconbtn nx-bell" aria-expanded={open} onClick={() => setOpen(!open)}
        aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}>
        <Bell size={16} />
        {unread > 0 && <span className="nx-bell__count" key={unread}>{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && (
        <div className="nx-menu__panel nx-notes" role="dialog" aria-label="Notifications">
          <div className="nx-notes__head">
            <b>Notifications</b>
            {unread > 0 && <button type="button" onClick={onReadAll}><CheckCheck size={14} />Mark all read</button>}
          </div>
          {items.length === 0 ? <p className="nx-notes__empty">You're all caught up.</p> : (
            <ul>
              {items.map((n) => {
                const k = KIND[n.kind as keyof typeof KIND] ?? KIND.closed;
                return (
                  <li key={n.id}>
                    <button type="button" data-read={n.read} onClick={() => { setOpen(false); onOpenItem(n); }}>
                      <span className="nx-notes__icon" data-tone={k.tone}><k.icon size={15} /></span>
                      <span className="nx-notes__text"><b>{n.title}</b><small>{n.body}</small></span>
                      <span className="nx-notes__time">{ago(n.created_at)}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
