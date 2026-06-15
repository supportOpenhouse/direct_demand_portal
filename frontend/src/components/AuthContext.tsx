/* Google OAuth gate — graceful. If VITE_GOOGLE_CLIENT_ID is unset, auth is OFF
   and the app renders open (exactly as before). When set, the app gates behind a
   Google sign-in and attaches the issued JWT to every API call. */
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, AuthUser, GOOGLE_CLIENT_ID, getToken, setToken } from "../lib/api";

interface AuthState {
  enabled: boolean;
  user: AuthUser | null;
  loading: boolean;
  logout: () => void;
}
const AuthCtx = createContext<AuthState>({ enabled: false, user: null, loading: false, logout: () => {} });
export const useAuth = () => useContext(AuthCtx);

declare global {
  interface Window {
    google?: any;
    __ddCredential?: (resp: { credential: string }) => void;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const enabled = !!GOOGLE_CLIENT_ID;
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(enabled);

  // restore an existing session
  useEffect(() => {
    if (!enabled) return;
    if (!getToken()) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, [enabled]);

  const logout = () => {
    setToken(null);
    setUser(null);
    window.google?.accounts.id.disableAutoSelect?.();
  };

  if (!enabled) return <AuthCtx.Provider value={{ enabled, user, loading, logout }}>{children}</AuthCtx.Provider>;
  if (loading)
    return (
      <div style={{ height: "100vh", display: "grid", placeItems: "center", color: "var(--muted)" }}>Loading…</div>
    );
  if (!user) return <LoginGate onSignedIn={setUser} />;
  return <AuthCtx.Provider value={{ enabled, user, loading, logout }}>{children}</AuthCtx.Provider>;
}

function LoginGate({ onSignedIn }: { onSignedIn: (u: AuthUser) => void }) {
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    window.__ddCredential = async (resp) => {
      try {
        const { token, user } = await api.authGoogle(resp.credential);
        setToken(token);
        onSignedIn(user);
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
  }, [onSignedIn]);

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
