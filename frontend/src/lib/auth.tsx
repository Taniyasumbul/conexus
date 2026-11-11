import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, AuthStatus, Role, User } from "./api";

const RANK: Record<Role, number> = { sales: 0, legal: 1, admin: 2 };

interface AuthCtx {
  user: User;
  can: (role: Role) => boolean;
  signOut: () => Promise<void>;
}
const Ctx = createContext<AuthCtx | null>(null);

export function useAuth(): AuthCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useAuth outside AuthProvider");
  return c;
}

/** Loads the session; renders `gate` (sign-in / setup) until someone is signed in. */
export function AuthProvider({ children, gate }: {
  children: ReactNode;
  gate: (status: AuthStatus | null, onSignedIn: (u: User) => void, error: string | null) => ReactNode;
}) {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    api.authStatus().then((s) => { setStatus(s); setError(null); }).catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    refresh();
    const onExpired = () => setStatus((s) => (s ? { ...s, user: null } : s));
    window.addEventListener("nx:unauthorized", onExpired);
    return () => window.removeEventListener("nx:unauthorized", onExpired);
  }, [refresh]);

  if (!status?.user) {
    return <>{gate(status, (u) => setStatus({ setup_required: false, user: u }), error)}</>;
  }
  const user = status.user;
  const value: AuthCtx = {
    user,
    can: (role) => RANK[user.role] >= RANK[role],
    signOut: async () => { await api.logout().catch(() => {}); setStatus({ setup_required: false, user: null }); },
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
