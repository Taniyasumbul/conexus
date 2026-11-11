import {
  ButtonHTMLAttributes, CSSProperties, Fragment, InputHTMLAttributes, ReactNode, SelectHTMLAttributes,
  TextareaHTMLAttributes, useEffect, useId, useRef, useState,
} from "react";
import { AlertTriangle, CheckCircle2, Info, OctagonAlert, Inbox } from "lucide-react";

export type Tone = "neutral" | "info" | "good" | "warning" | "serious" | "critical";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

/* ---------------------------------------------------------------- layout */
type LayoutProps = { children: ReactNode; gap?: number; className?: string; style?: CSSProperties };
export function Stack({ children, gap, className, style }: LayoutProps) {
  return <div className={cx("nx-stack", className)} style={{ ...(gap !== undefined && { ["--gap" as string]: `${gap}px` }), ...style }}>{children}</div>;
}
export function Row({ children, gap, className, style, justify }: LayoutProps & { justify?: "between" | "end" }) {
  return <div className={cx("nx-row", justify && `nx-row--${justify}`, className)} style={{ ...(gap !== undefined && { ["--gap" as string]: `${gap}px` }), ...style }}>{children}</div>;
}
export function Grid({ children, min = 220, gap, className }: LayoutProps & { min?: number }) {
  return <div className={cx("nx-grid", className)} style={{ ["--min" as string]: `${min}px`, ...(gap !== undefined && { ["--gap" as string]: `${gap}px` }) }}>{children}</div>;
}

/* ---------------------------------------------------------------- button */
type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger" | "success";
  size?: "sm" | "md" | "lg";
  icon?: ReactNode;
  loading?: boolean;
  block?: boolean;
};
export function Button({ variant = "secondary", size = "md", icon, loading, block, children, className, disabled, ...rest }: ButtonProps) {
  return (
    <button
      className={cx("nx-btn", `nx-btn--${variant}`, size !== "md" && `nx-btn--${size}`, block && "nx-btn--block", className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
}

/* ---------------------------------------------------------------- badge */
export function Badge({ tone = "neutral", icon, dot, outline, children, title }: {
  tone?: Tone; icon?: ReactNode; dot?: boolean; outline?: boolean; children: ReactNode; title?: string;
}) {
  return (
    <span title={title} className={cx("nx-badge", tone !== "neutral" && `nx-badge--${tone}`, dot && "nx-badge--dot", outline && "nx-badge--outline")}>
      {icon}{children}
    </span>
  );
}

/* ---------------------------------------------------------------- card */
export function Card({ title, subtitle, actions, children, flush, flat, tone, className }: {
  title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode;
  flush?: boolean; flat?: boolean; tone?: "critical"; className?: string;
}) {
  return (
    <section className={cx("nx-card", flat && "nx-card--flat", tone && `nx-card--tone-${tone}`, className)}>
      {(title || actions) && (
        <header className="nx-card__head">
          <div>
            {title && <div className="nx-card__title">{title}</div>}
            {subtitle && <div className="nx-card__sub">{subtitle}</div>}
          </div>
          {actions && <Row gap={8}>{actions}</Row>}
        </header>
      )}
      <div className={cx("nx-card__body", flush && "nx-card__body--flush")}>{children}</div>
    </section>
  );
}

/* ---------------------------------------------------------------- stat */
export type Tint = "violet" | "amber" | "rose" | "mint" | "sky";
export function Stat({ label, value, hint, tone, icon, tint = "violet" }: {
  label: string; value: ReactNode; hint?: ReactNode; tone?: "good" | "critical"; icon?: ReactNode; tint?: Tint;
}) {
  return (
    <div className={cx("nx-card nx-stat", tone && `nx-stat--${tone}`)}>
      {icon && <span className="nx-stat__icon" data-tint={tint} aria-hidden>{icon}</span>}
      <span className="nx-stat__label">{label}</span>
      <span className="nx-stat__value">{value}</span>
      {hint && <span className="nx-stat__hint">{hint}</span>}
    </div>
  );
}

/* ---------------------------------------------------------------- page header */
export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: ReactNode; title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="nx-page-header">
      <div className="nx-stack" style={{ ["--gap" as string]: "4px" }}>
        {eyebrow && <span className="nx-eyebrow">{eyebrow}</span>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <Row gap={8}>{actions}</Row>}
    </header>
  );
}

/* ---------------------------------------------------------------- forms */
export function Field({ label, hint, error, children, htmlFor }: { label: string; hint?: ReactNode; error?: string; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="nx-field">
      <label className="nx-field__label" htmlFor={htmlFor}>{label}</label>
      {children}
      {error ? <span className="nx-field__error">{error}</span> : hint && <span className="nx-field__hint">{hint}</span>}
    </div>
  );
}
export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx("nx-input", props.className)} />;
}
export function Select({ options, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { options: { value: string; label: string }[] }) {
  return (
    <select {...props} className={cx("nx-select", props.className)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={cx("nx-textarea", props.className)} />;
}
export function Range({ value, onChange, min, max, step, id, format }: {
  value: number; onChange: (v: number) => void; min: number; max: number; step: number; id?: string; format?: (v: number) => string;
}) {
  return (
    <Row gap={12}>
      <input id={id} type="range" className="nx-range" style={{ flex: 1 }} value={value} min={min} max={max} step={step}
        onChange={(e) => onChange(Number(e.target.value))} />
      <span className="nx-mono nx-num" style={{ minWidth: "4.5em", textAlign: "right" }}>{format ? format(value) : value}</span>
    </Row>
  );
}
export function Segmented<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[]; label: string;
}) {
  return (
    <div className="nx-segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}
export function ChoiceGroup<T extends string>({ value, onChange, options, label }: {
  value: T; onChange: (v: T) => void; options: { value: T; title: ReactNode; detail?: ReactNode }[]; label: string;
}) {
  return (
    <div className="nx-choice-grid" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" className="nx-choice" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          <strong>{o.title}</strong>
          {o.detail && <small>{o.detail}</small>}
        </button>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- tabs */
export function Tabs<T extends string>({ value, onChange, tabs }: {
  value: T; onChange: (v: T) => void; tabs: { value: T; label: ReactNode; count?: number; icon?: ReactNode }[];
}) {
  const id = useId();
  return (
    <div className="nx-tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.value} id={`${id}-${t.value}`} role="tab" type="button" className="nx-tab" aria-selected={t.value === value} onClick={() => onChange(t.value)}>
          {t.icon}{t.label}{t.count !== undefined && <span className="nx-tab__count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- table */
export type Column<T> = { key: string; header: ReactNode; render: (row: T) => ReactNode; num?: boolean; width?: string };
export function Table<T>({ columns, rows, rowKey, onRowClick, empty }: {
  columns: Column<T>[]; rows: T[]; rowKey: (r: T) => string; onRowClick?: (r: T) => void; empty?: ReactNode;
}) {
  if (!rows.length) return <>{empty ?? <EmptyState title="Nothing here yet" />}</>;
  return (
    <div className="nx-table-wrap">
      <table className="nx-table">
        <thead>
          <tr>{columns.map((c) => <th key={c.key} className={c.num ? "num" : undefined} style={{ width: c.width }}>{c.header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={rowKey(r)} className={onRowClick ? "clickable" : undefined} onClick={onRowClick && (() => onRowClick(r))}
              tabIndex={onRowClick ? 0 : undefined} onKeyDown={onRowClick && ((e) => e.key === "Enter" && onRowClick(r))}>
              {columns.map((c) => <td key={c.key} className={c.num ? "num" : undefined}>{c.render(r)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------------------------------------------------------------- feedback */
const ALERT_ICON = { info: Info, good: CheckCircle2, warning: AlertTriangle, critical: OctagonAlert };
export function Alert({ tone = "info", title, children, actions }: {
  tone?: "info" | "good" | "warning" | "critical"; title?: ReactNode; children?: ReactNode; actions?: ReactNode;
}) {
  const Icon = ALERT_ICON[tone];
  return (
    <div className={`nx-alert nx-alert--${tone}`} role={tone === "critical" ? "alert" : "status"}>
      <Icon size={18} />
      <div className="nx-stack" style={{ ["--gap" as string]: "6px", flex: 1 }}>
        {title && <div className="nx-alert__title">{title}</div>}
        {children && <div className="nx-secondary">{children}</div>}
        {actions && <Row gap={8}>{actions}</Row>}
      </div>
    </div>
  );
}
export function Spinner({ label }: { label?: string }) {
  return <span className="nx-spinner" role="status" aria-label={label ?? "Loading"} />;
}
export function Skeleton({ height = 16, width = "100%" }: { height?: number; width?: number | string }) {
  return <div className="nx-skeleton" style={{ height, width }} aria-hidden />;
}
export function EmptyState({ title, children, icon, action }: { title: string; children?: ReactNode; icon?: ReactNode; action?: ReactNode }) {
  return (
    <div className="nx-empty">
      {icon ?? <Inbox size={28} />}
      <h3>{title}</h3>
      {children && <p style={{ maxWidth: "52ch" }}>{children}</p>}
      {action}
    </div>
  );
}
export function KeyValue({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <dl className="nx-kv">
      {items.map(([k, v], i) => (<Fragment key={i}><dt>{k}</dt><dd>{v}</dd></Fragment>))}
    </dl>
  );
}
export function Divider() {
  return <hr className="nx-divider" />;
}
export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="nx-legend">
      {items.map((i) => <span key={i.label}><i className={i.dashed ? "dashed" : undefined} style={{ background: i.color }} />{i.label}</span>)}
    </div>
  );
}

/* ---------------------------------------------------------------- switch / avatar / save bar */
export function Switch({ checked, onChange, label, id, disabled }: { checked: boolean; onChange: (v: boolean) => void; label?: ReactNode; id?: string; disabled?: boolean }) {
  return (
    <label className="nx-switch" htmlFor={id}>
      <input id={id} type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="nx-switch__track" aria-hidden />
      {label && <span>{label}</span>}
    </label>
  );
}
export function Avatar({ name, size = "md" }: { name: string; size?: "md" | "lg" }) {
  const initials = name.split(/[\s@._-]+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
  return <span className={cx("nx-avatar", size === "lg" && "nx-avatar--lg")} aria-hidden>{initials || "?"}</span>;
}
export function SaveBar({ children, actions }: { children: ReactNode; actions: ReactNode }) {
  return <div className="nx-savebar" role="region" aria-label="Unsaved changes"><span>{children}</span><Row gap={8}>{actions}</Row></div>;
}

/* ---------------------------------------------------------------- company mark */
const TINTS: Tint[] = ["violet", "amber", "rose", "mint", "sky"];
export function Company({ name, sub }: { name: string; sub?: ReactNode }) {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
  const tint = TINTS[[...name].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7) % TINTS.length];
  return (
    <div className="nx-company">
      <span className="nx-company__logo" style={{ background: `var(--tint-${tint})`, color: `var(--tint-${tint}-fg)` }} aria-hidden>{initials}</span>
      <div style={{ minWidth: 0 }}>
        <div className="nx-company__name">{name}</div>
        {sub && <div className="nx-company__sub">{sub}</div>}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- count-up number */
const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
/** Rolls a number up from 0 on mount, and from its previous value whenever it changes. */
export function CountUp({ value, format = (n) => Math.round(n).toLocaleString(), duration = 800 }: {
  value: number; format?: (n: number) => string; duration?: number;
}) {
  const [shown, setShown] = useState(reducedMotion() ? value : 0);
  const from = useRef(reducedMotion() ? value : 0);
  useEffect(() => {
    if (reducedMotion()) { setShown(value); from.current = value; return; }
    const start = performance.now(), a = from.current, b = value;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / duration);
      const v = a + (b - a) * (1 - Math.pow(1 - k, 3));
      setShown(v);
      if (k < 1) raf = requestAnimationFrame(tick); else from.current = b;
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); from.current = b; };
  }, [value, duration]);
  return <span className="nx-num">{format(shown)}</span>;
}
