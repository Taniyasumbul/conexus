import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

/** Fetch data, optionally re-polling while `poll(data)` returns an interval in ms. */
export function useApi<T>(fn: () => Promise<T>, deps: unknown[] = [], poll?: (data: T | undefined) => number | false) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const pollRef = useRef(poll);
  pollRef.current = poll;

  const reload = useCallback(async () => {
    try {
      const d = await fnRef.current();
      setData(d);
      setError(null);
      return d;
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, String(e)));
      return undefined;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    setLoading(true);
    const tick = async () => {
      const d = await reload();
      const ms = pollRef.current?.(d);
      if (alive && ms) timer = setTimeout(tick, ms);
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, reload, setData };
}

export type ThemePref = "system" | "light" | "dark";

/** Light by default. Dark only when the person switches it on (stored per browser). */
export function readTheme(): "light" | "dark" {
  try { return localStorage.getItem("nx-mode") === "dark" ? "dark" : "light"; } catch { return "light"; }
}
export function useTheme(): [ThemePref, (t: ThemePref) => void] {
  const [pref, setPref] = useState<ThemePref>(readTheme);
  useEffect(() => {
    const mode = pref === "dark" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", mode);
    try { localStorage.setItem("nx-mode", mode); } catch { /* storage blocked */ }
  }, [pref]);
  return [pref, setPref];
}

/** Read a CSS custom property (for charts, which need concrete colours). Re-reads on theme change. */
export function useTokens<K extends string>(names: readonly K[]): Record<K, string> {
  const read = () => {
    const cs = getComputedStyle(document.documentElement);
    return Object.fromEntries(names.map((n) => [n, cs.getPropertyValue(`--${n}`).trim()])) as Record<K, string>;
  };
  const [vals, setVals] = useState(read);
  useEffect(() => {
    const update = () => setVals(read());
    const mo = new MutationObserver(update);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "data-palette"] });
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", update);
    return () => { mo.disconnect(); mq.removeEventListener("change", update); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return vals;
}

export const PALETTES = ["ocean", "violet", "sunset", "emerald", "mono", "midnight"] as const;
export type Palette = (typeof PALETTES)[number];

export function readPalette(): Palette {
  try {
    const p = localStorage.getItem("nx-palette") as Palette | null;
    return p && (PALETTES as readonly string[]).includes(p) ? p : "ocean";
  } catch { return "ocean"; }
}

/** Colour palette, persisted per browser and applied on <html data-palette>. */
export function usePalette(): [Palette, (p: Palette) => void] {
  const [p, setP] = useState<Palette>(readPalette);
  useEffect(() => {
    document.documentElement.setAttribute("data-palette", p);
    try { localStorage.setItem("nx-palette", p); } catch { /* storage blocked */ }
    window.dispatchEvent(new Event("nx:palette"));
  }, [p]);
  return [p, setP];
}
