/**
 * Settings & Access — no-code integrations (switches, API key & webhook code
 * blocks) and Roles & access (hierarchy explainer, team roster, assignment
 * method). Admin-only (route is guarded by the router).
 */
import { useState } from 'react';
import { Avatar } from '../components/Avatar';
import { Switch } from '../components/Switch';
import { Topbar } from '../components/Topbar';
import { useToast } from '../components/Toast';
import { IconSettings, IconLeads } from '../components/icons';
import { ConnectMetaModal } from '../features/modals/ConnectMetaModal';
import { useAddLeadModal } from '../features/modals/AddLeadModal';
import { ApiError } from '../lib/api';
import { useSettings, useUpdateAssignment, useUpdateIntegration, useUsers } from '../lib/queries';
import type { Role } from '../lib/types';

function errDetail(e: unknown): string {
  if (e instanceof ApiError) return e.detail;
  return e instanceof Error ? e.message : 'Something went wrong';
}

const ROLE_LABELS: Record<Role, string> = { admin: 'Admin', cm: 'Closing Manager', rm: 'RM' };

const HIERARCHY: { role: string; scope: string }[] = [
  { role: 'Admin', scope: 'Everything — all leads, settings, and the only role that edits source-captured data.' },
  { role: 'Closing Manager', scope: 'All leads assigned to the RMs in their team.' },
  { role: 'RM', scope: 'Their own (assigned) leads only.' },
];

const ASSIGNMENT_OPTIONS: { value: string; label: string }[] = [
  { value: 'round_robin', label: 'Round robin' },
  { value: 'fewest_leads', label: 'Fewest leads' },
  { value: 'manual', label: 'Manual' },
];

function CodeBlock({ label, value, copiedTitle }: { label: string; value: string; copiedTitle: string }) {
  const { push } = useToast();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      push({ kind: 'blue', title: copiedTitle });
    } catch {
      push({ kind: 'blue', title: 'Copy failed', sub: 'Clipboard unavailable' });
    }
  };
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--ink-2)', marginBottom: 6 }}>{label}</div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          background: 'var(--panel-2)',
          border: '1px solid var(--line)',
          borderRadius: 9,
          padding: '8px 11px',
        }}
      >
        <code className="mono" style={{ flex: 1, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {value}
        </code>
        <button type="button" className="btn ghost sm" onClick={copy}>
          Copy
        </button>
      </div>
    </div>
  );
}

export default function Settings() {
  const { openAddLead, addLeadModal } = useAddLeadModal();
  const { push } = useToast();
  const settings = useSettings();
  const users = useUsers();
  const updateIntegration = useUpdateIntegration();
  const updateAssignment = useUpdateAssignment();
  const [metaOpen, setMetaOpen] = useState(false);

  const toggleIntegration = (key: string, label: string, enabled: boolean) => {
    updateIntegration.mutate(
      { key, enabled },
      {
        onSuccess: () =>
          push({ kind: 'green', title: `${label} ${enabled ? 'enabled' : 'disabled'}` }),
      },
    );
  };

  const changeAssignment = (method: string) => {
    updateAssignment.mutate(
      { method },
      {
        onSuccess: () =>
          push({
            kind: 'green',
            title: 'Assignment method updated',
            sub: ASSIGNMENT_OPTIONS.find((o) => o.value === method)?.label,
          }),
      },
    );
  };

  return (
    <>
      <Topbar onAddLead={openAddLead} />
      <div className="view">
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))',
            gap: 14,
            alignItems: 'start',
          }}
        >
          {/* ------------------------------------------------ integrations */}
          <div className="card panel-pad">
            <div className="panel-title">
              <IconSettings size={16} />
              No-code integrations
            </div>

            {settings.isLoading && <div className="empty">Loading…</div>}
            {settings.error != null && <div className="note">{errDetail(settings.error)}</div>}

            {settings.data && (
              <>
                {settings.data.integrations.map((ig) => (
                  <div
                    key={ig.key}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '10px 0',
                      borderBottom: '1px solid var(--line-2)',
                    }}
                  >
                    <span style={{ flex: 1, fontWeight: 600, fontSize: 13 }}>{ig.label}</span>
                    {ig.key === 'meta' && (
                      <button type="button" className="btn ghost sm" onClick={() => setMetaOpen(true)}>
                        Connect
                      </button>
                    )}
                    <Switch
                      checked={ig.enabled}
                      disabled={updateIntegration.isPending}
                      onChange={(c) => toggleIntegration(ig.key, ig.label, c)}
                    />
                  </div>
                ))}
                {updateIntegration.error != null && (
                  <div className="note" style={{ marginTop: 10 }}>
                    {errDetail(updateIntegration.error)}
                  </div>
                )}

                <CodeBlock label="API key" value={settings.data.api_key_masked} copiedTitle="API key copied" />
                <CodeBlock label="Webhook" value={settings.data.webhook_url} copiedTitle="Webhook URL copied" />
              </>
            )}
          </div>

          {/* ------------------------------------------------ roles & access */}
          <div className="card panel-pad">
            <div className="panel-title">
              <IconLeads size={16} />
              Roles &amp; access
            </div>

            {HIERARCHY.map((h) => (
              <div
                key={h.role}
                style={{
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 10,
                  background: 'var(--panel-2)',
                  border: '1px solid var(--line-2)',
                  borderRadius: 9,
                  padding: '9px 12px',
                  marginBottom: 8,
                }}
              >
                <span className="chip" style={{ background: 'var(--panel)' }}>
                  {h.role}
                </span>
                <span style={{ fontSize: 12.5, color: 'var(--ink-2)' }}>{h.scope}</span>
              </div>
            ))}

            <div style={{ fontSize: 12, fontWeight: 700, margin: '16px 0 4px' }}>Team roster</div>
            {users.isLoading && <div className="empty">Loading…</div>}
            {users.error != null && <div className="note">{errDetail(users.error)}</div>}
            {users.data?.map((u) => (
              <div
                key={u.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '9px 0',
                  borderBottom: '1px solid var(--line-2)',
                }}
              >
                <Avatar name={u.name} size={28} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{u.name}</span>
                  <br />
                  <span style={{ fontSize: 11.5, color: 'var(--muted)' }}>{u.email}</span>
                </span>
                <span className="chip">{ROLE_LABELS[u.role]}</span>
                <span
                  title={u.active ? 'Active' : 'Inactive'}
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    flex: '0 0 auto',
                    background: u.active ? 'var(--emerald)' : 'var(--muted)',
                  }}
                />
              </div>
            ))}

            <div className="field" style={{ marginTop: 16, marginBottom: 0 }}>
              <label htmlFor="assignment-method">Assignment method</label>
              <select
                id="assignment-method"
                value={settings.data?.assignment_method ?? 'round_robin'}
                disabled={!settings.data || updateAssignment.isPending}
                onChange={(e) => changeAssignment(e.target.value)}
              >
                {ASSIGNMENT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>
            {updateAssignment.error != null && (
              <div className="note" style={{ marginTop: 10 }}>
                {errDetail(updateAssignment.error)}
              </div>
            )}
          </div>
        </div>
      </div>

      <ConnectMetaModal open={metaOpen} onClose={() => setMetaOpen(false)} />
      {addLeadModal}
    </>
  );
}
