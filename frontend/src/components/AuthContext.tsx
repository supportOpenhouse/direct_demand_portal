/* Google OAuth gate — graceful. If VITE_GOOGLE_CLIENT_ID is unset, auth is OFF
   and the app renders open (exactly as before). When set, the app gates behind a
   Google sign-in and attaches the issued JWT to every API call. */
import { createContext, useContext, useEffect, useRef, useState, ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, AuthUser, GOOGLE_CLIENT_ID, getToken, setToken,
         isDevBuild, getDevUser, setDevUser } from "../lib/api";

interface AuthState {
  enabled: boolean;
  user: AuthUser | null;
  loading: boolean;
  logout: () => void;
  /* Local "view as" — null everywhere except a dev build. Setting it makes every
     request identify as that user, so the role gates and the server's row scoping
     both follow. */
  devUser: string | null;
  viewAs: (email: string | null) => void;
}
const AuthCtx = createContext<AuthState>({
  enabled: false, user: null, loading: false, logout: () => {},
  devUser: null, viewAs: () => {},
});
export const useAuth = () => useContext(AuthCtx);

declare global {
  interface Window {
    google?: any;
    __ddCredential?: (resp: { credential: string }) => void;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const enabled = !!GOOGLE_CLIENT_ID;
  const qc = useQueryClient();
  const [token, setTok] = useState<string | null>(getToken());
  const [devUser, setDev] = useState<string | null>(getDevUser());

  /* /me is polled, not fetched once: an admin changing someone's role in Settings
     now has to reach that person's open tab. The backend reads role off the users
     row (not the JWT claim), so this picks the change up without a re-login. */
  const { data, isLoading } = useQuery({
    // keyed on devUser so switching identity can't serve the previous one from cache
    queryKey: ["me", devUser],
    queryFn: api.me,
    // with auth off /me normally never fires; impersonating is the one case where it
    // must, because the server is what resolves the email into a role
    enabled: (enabled && !!token) || (isDevBuild && !!devUser),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    retry: false,
  });
  const user = data ?? null;

  /* A role swap changes which rows the API will hand back, so the cached
     role-scoped lists are wrong the moment it lands. The admin-only chrome
     re-renders off context on its own — this is only about stale data. */
  const prevRole = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (prevRole.current && user?.role && prevRole.current !== user.role) {
      qc.invalidateQueries();
    }
    prevRole.current = user?.role;
  }, [user?.role, qc]);

  /* Everything cached was fetched as the previous identity — role scoping means the
     server will hand back different rows now, so drop all of it rather than show one
     user's leads under another's name. */
  const viewAs = (email: string | null) => {
    setDevUser(email);
    setDev(email);
    qc.clear();
  };

  const logout = () => {
    setToken(null);
    setTok(null);
    qc.clear();
    window.google?.accounts.id.disableAutoSelect?.();
  };

  /* `enabled` is reported true while impersonating so the role gates actually bite —
     they're all written `!enabled || user?.role === "admin"`, which would otherwise
     hand every impersonated RM a full admin view. */
  const value = {
    enabled: enabled || !!devUser, user, loading: isLoading, logout, devUser, viewAs,
  };
  if (!enabled) return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
  if (token && isLoading)
    return (
      <div style={{ height: "100vh", display: "grid", placeItems: "center", color: "var(--muted)" }}>Loading…</div>
    );
  if (!user) return <LoginGate onSignedIn={setTok} />;
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

function LoginGate({ onSignedIn }: { onSignedIn: (token: string) => void }) {
  const [err, setErr] = useState<string | null>(null);
  const qc = useQueryClient();

  useEffect(() => {
    window.__ddCredential = async (resp) => {
      try {
        const { token, user } = await api.authGoogle(resp.credential);
        setToken(token);
        qc.setQueryData<AuthUser>(["me"], user); // seed, so the gate lifts without a second round-trip
        onSignedIn(token);
      } catch (e: any) {
        setErr(e.message || "Sign-in failed");
      }
    };
    const init = () => {
      if (!window.google) return;
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: (r: { credential: string }) => window.__ddCredential?.(r),
      });
      const el = document.getElementById("g-signin");
      if (el) window.google.accounts.id.renderButton(el, { theme: "filled_black", size: "large", shape: "pill" });
    };
    if (window.google) init();
    else {
      const s = document.createElement("script");
      s.src = "https://accounts.google.com/gsi/client";
      s.async = true;
      s.onload = init;
      document.head.appendChild(s);
    }
  }, [onSignedIn, qc]);

  return (
    <div style={{ height: "100vh", display: "grid", placeItems: "center", background: "var(--bg)" }}>
      <div className="card panel-pad" style={{ width: 360, textAlign: "center", padding: 32 }}>
        <div style={{ fontFamily: "'Bricolage Grotesque'", fontWeight: 700, fontSize: 22, marginBottom: 4 }}>Openhouse</div>
        <div style={{ fontSize: 10.5, letterSpacing: ".14em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 22 }}>
          Direct Demand
        </div>
        <p className="sec-sub" style={{ marginBottom: 20 }}>Sign in with your Openhouse Google account.</p>
        <div id="g-signin" style={{ display: "flex", justifyContent: "center" }} />
        {err && <div className="mand-flag show" style={{ marginTop: 16 }}>⚠ {err}</div>}
      </div>
    </div>
  );
}
