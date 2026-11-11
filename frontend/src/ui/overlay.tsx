import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { CheckCircle2, Info, OctagonAlert } from "lucide-react";

/* ---------------------------------------------------------------- dialog */
export function Dialog({ open, onClose, title, children, footer }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} className="nx-dialog" onClose={onClose} onCancel={onClose}>
      <div className="nx-dialog__head"><h3>{title}</h3></div>
      <div className="nx-dialog__body">{children}</div>
      {footer && <div className="nx-dialog__foot">{footer}</div>}
    </dialog>
  );
}

/* ---------------------------------------------------------------- toasts */
type Toast = { id: number; tone: "info" | "good" | "critical"; text: string };
const ToastCtx = createContext<(text: string, tone?: Toast["tone"]) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, tone, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  const icon = { info: <Info size={18} />, good: <CheckCircle2 size={18} />, critical: <OctagonAlert size={18} /> };
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="nx-toasts" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className="nx-toast" data-tone={t.tone}>{icon[t.tone]}<span>{t.text}</span></div>)}
      </div>
    </ToastCtx.Provider>
  );
}
export const useToast = () => useContext(ToastCtx);
