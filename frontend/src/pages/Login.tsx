import { useCallback, useEffect, useRef, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { OpenhouseLogo } from '../components/icons';
import { api, ApiError } from '../lib/api';
import type { AuthResponse } from '../lib/types';
import { useAuth } from '../store/auth';

const DEV_QUICK_EMAILS = [
  'support@openhouse.in',
  'admin@openhouse.in',
  'cm@openhouse.in',
  'rm1@openhouse.in',
];

/**
 * Login: Google Identity Services button when VITE_GOOGLE_CLIENT_ID is set;
 * dev email quick-login (POST /v1/auth/dev-login) otherwise. 403 surfaces the
 * API's "Account not provisioned" detail.
 */
export default function Login() {
  const { token, login } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState('');
  const gsiRef = useRef<HTMLDivElement | null>(null);

  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;

  const finishLogin = useCallback(
    (res: AuthResponse) => {
      login(res.token, res.user);
      navigate('/', { replace: true });
    },
    [login, navigate],
  );

  const failLogin = useCallback((e: unknown) => {
    setError(e instanceof ApiError ? e.detail : 'Sign-in failed — please try again.');
  }, []);

  /* ---- Google Identity Services ---- */
  useEffect(() => {
    if (!clientId) return;
    let cancelled = false;

    const onCredential = async (response: { credential: string }) => {
      setError(null);
      setBusy(true);
      try {
        const res = await api.post<AuthResponse>('/auth/google', {
          credential: response.credential,
        });
        if (!cancelled) finishLogin(res);
      } catch (e) {
        if (!cancelled) failLogin(e);
      } finally {
        if (!cancelled) setBusy(false);
      }
    };

    const tryInit = (): boolean => {
      const gsi = window.google?.accounts?.id;
      if (!gsi || !gsiRef.current) return false;
      gsi.initialize({ client_id: clientId, callback: onCredential });
      gsi.renderButton(gsiRef.current, {
        theme: 'outline',
        size: 'large',
        width: 300,
        text: 'signin_with',
        shape: 'pill',
      });
      return true;
    };

    if (tryInit()) return;
    const timer = window.setInterval(() => {
      if (tryInit()) window.clearInterval(timer);
    }, 200);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [clientId, finishLogin, failLogin]);

  /* ---- dev login (no Google client id yet) ---- */
  const devLogin = async (devEmail: string) => {
    if (!devEmail.trim()) return;
    setError(null);
    setBusy(true);
    try {
      const res = await api.post<AuthResponse>('/auth/dev-login', { email: devEmail.trim() });
      finishLogin(res);
    } catch (e) {
      failLogin(e);
    } finally {
      setBusy(false);
    }
  };

  if (token) return <Navigate to="/" replace />;

  return (
    <div className="login-wrap">
      <div className="login-card">
        <OpenhouseLogo size={52} />
        <div className="l-title">Openhouse</div>
        <div className="l-sub">Direct Demand</div>

        {clientId ? (
          <div className="login-gsi" ref={gsiRef} />
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void devLogin(email);
            }}
          >
            <div className="note" style={{ marginBottom: 14, textAlign: 'left' }}>
              Dev sign-in — no Google client ID configured. Requires the API to run with
              DEV_LOGIN_ENABLED=true.
            </div>
            <div className="field" style={{ textAlign: 'left' }}>
              <label htmlFor="dev-email">Email</label>
              <input
                id="dev-email"
                type="email"
                placeholder="you@openhouse.in"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <button type="submit" className="btn green" disabled={busy} style={{ width: '100%' }}>
              {busy ? 'Signing in…' : 'Sign in (dev)'}
            </button>
            <div className="login-quick">
              {DEV_QUICK_EMAILS.map((qe) => (
                <button
                  key={qe}
                  type="button"
                  className="btn ghost sm"
                  disabled={busy}
                  onClick={() => void devLogin(qe)}
                >
                  {qe.split('@')[0]}
                </button>
              ))}
            </div>
          </form>
        )}

        {error && <div className="login-err">{error}</div>}
      </div>
    </div>
  );
}
