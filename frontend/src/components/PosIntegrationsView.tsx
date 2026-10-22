import React, { useEffect, useState } from 'react';
import {
  CheckCircle2,
  Copy,
  Layers,
  Plus,
  RefreshCw,
  Server,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { api } from '../services/api';
import { PosIntegration, PosSyncResponse } from '../types';

export const PosIntegrationsView: React.FC = () => {
  const [integrations, setIntegrations] = useState<PosIntegration[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // New Integration Form
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [provider, setProvider] = useState<string>('MOCK_SQUARE');
  const [integrationName, setIntegrationName] = useState<string>('Register Terminal #1');
  const [apiKey, setApiKey] = useState<string>('');
  const [creating, setCreating] = useState<boolean>(false);
  const [newSecretBanner, setNewSecretBanner] = useState<{ name: string; secret: string } | null>(null);

  // Syncing States
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [lastSyncResult, setLastSyncResult] = useState<PosSyncResponse | null>(null);

  const loadIntegrations = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await api.getPosIntegrations();
      setIntegrations(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load POS integrations');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadIntegrations();
  }, []);

  const handleCreateIntegration = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setErrorMsg(null);
    try {
      const created = await api.createPosIntegration({
        provider,
        integration_name: integrationName.trim(),
        api_key: apiKey.trim() || undefined,
      });

      if (created.webhook_signing_secret) {
        setNewSecretBanner({
          name: created.integration_name,
          secret: created.webhook_signing_secret,
        });
      }

      setShowCreateModal(false);
      setApiKey('');
      setIntegrationName('Register Terminal #2');
      loadIntegrations();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to create POS integration');
    } finally {
      setCreating(false);
    }
  };

  const handleTriggerSync = async (integration: PosIntegration) => {
    setSyncingId(integration.id);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await api.syncPosIntegration(integration.id);
      setLastSyncResult(res);
      setSuccessMsg(
        `Successfully synced ${res.synced_items_count} items from ${integration.provider} (${res.adjusted_transactions_count} stock transactions adjusted).`
      );
      loadIntegrations();
    } catch (err: any) {
      setErrorMsg(err.message || 'POS inventory sync failed');
    } finally {
      setSyncingId(null);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    alert('Copied to clipboard!');
  };

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-900)' }}>Point-of-Sale (POS) Integrations</h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
            Provider-independent adapter architecture for Square, Clover, and real-time sales webhook synchronization.
          </p>
        </div>

        <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
          <Plus size={16} /> Connect POS Provider
        </button>
      </div>

      {/* Notifications */}
      {errorMsg && (
        <div style={{ padding: '12px', background: 'var(--danger-bg)', color: 'var(--danger)', borderRadius: '8px', marginBottom: '16px' }}>
          <strong>Error:</strong> {errorMsg}
        </div>
      )}

      {successMsg && (
        <div style={{ padding: '12px', background: 'var(--success-bg)', color: 'var(--success)', borderRadius: '8px', marginBottom: '16px' }}>
          {successMsg}
        </div>
      )}

      {/* New Webhook Secret Single-View Alert */}
      {newSecretBanner && (
        <div style={{ padding: '16px', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '12px', marginBottom: '20px' }}>
          <h4 style={{ fontWeight: 700, color: '#1e40af', fontSize: '0.9375rem', marginBottom: '4px' }}>
            🔐 Save Webhook Signing Secret for "{newSecretBanner.name}"
          </h4>
          <p style={{ fontSize: '0.75rem', color: '#1e3a8a', marginBottom: '10px' }}>
            This secret is used by your external POS provider to generate HMAC-SHA256 signatures. It will never be shown again!
          </p>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <code style={{ background: 'white', padding: '6px 12px', borderRadius: '6px', border: '1px solid #93c5fd', fontSize: '0.8125rem', fontFamily: 'monospace', flex: 1 }}>
              {newSecretBanner.secret}
            </code>
            <button className="btn btn-primary" onClick={() => copyToClipboard(newSecretBanner.secret)}>
              <Copy size={14} /> Copy Secret
            </button>
            <button className="btn btn-secondary" onClick={() => setNewSecretBanner(null)}>
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Integrations List */}
      <div className="card">
        <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '14px' }}>
          Configured POS Adapters ({integrations.length})
        </h3>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '32px', color: 'var(--gray-500)' }}>
            Loading configured POS adapters...
          </div>
        ) : integrations.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '40px' }}>
            <Layers size={36} color="var(--gray-300)" style={{ margin: '0 auto 12px' }} />
            <h4 style={{ fontWeight: 600, color: 'var(--gray-800)', marginBottom: '4px' }}>No POS Integrations Configured</h4>
            <p style={{ fontSize: '0.8125rem', color: 'var(--gray-500)', marginBottom: '16px' }}>
              Connect a Mock POS or Square terminal adapter to automate inventory catalog synchronization.
            </p>
            <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
              Connect Mock POS
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {integrations.map((integ) => (
              <div
                key={integ.id}
                style={{
                  border: '1px solid var(--border)',
                  borderRadius: '10px',
                  padding: '16px',
                  background: integ.is_active ? 'white' : 'var(--gray-50)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <h4 style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--gray-900)' }}>
                        {integ.integration_name}
                      </h4>
                      <span className={`badge ${integ.provider.includes('MOCK') ? 'badge-notice' : 'badge-fresh'}`}>
                        {integ.provider}
                      </span>
                      {integ.provider.includes('MOCK') && (
                        <span style={{ fontSize: '0.6875rem', color: 'var(--warning)', fontWeight: 600 }}>
                          (Simulation Only)
                        </span>
                      )}
                    </div>
                    <p style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '2px' }}>
                      Connected on {new Date(integ.created_at).toLocaleDateString()} • Last Synced:{' '}
                      {integ.last_sync_at ? new Date(integ.last_sync_at).toLocaleString() : 'Never'}
                    </p>
                  </div>

                  <button
                    className="btn btn-primary"
                    disabled={syncingId === integ.id}
                    onClick={() => handleTriggerSync(integ)}
                  >
                    <RefreshCw className={syncingId === integ.id ? 'animate-spin' : ''} size={14} />
                    {syncingId === integ.id ? 'Syncing...' : 'Trigger Inventory Sync'}
                  </button>
                </div>

                {/* Webhook Endpoint Info */}
                <div style={{ background: 'var(--gray-50)', padding: '10px 14px', borderRadius: '8px', fontSize: '0.75rem', border: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontWeight: 600, color: 'var(--gray-700)' }}>Webhook Callback URL:</span>
                    <button
                      onClick={() => copyToClipboard(integ.webhook_url)}
                      style={{ background: 'none', border: 'none', color: 'var(--primary)', cursor: 'pointer', fontSize: '0.75rem', fontWeight: 600 }}
                    >
                      Copy URL
                    </button>
                  </div>
                  <code style={{ display: 'block', marginTop: '4px', wordBreak: 'break-all', color: 'var(--gray-800)' }}>
                    {integ.webhook_url}
                  </code>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create POS Modal */}
      {showCreateModal && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ maxWidth: '500px' }}>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '16px' }}>Connect POS Adapter</h3>

            <form onSubmit={handleCreateIntegration}>
              <div className="form-group">
                <label className="form-label">Provider Adapter</label>
                <select value={provider} onChange={(e) => setProvider(e.target.value)} className="form-select">
                  <option value="MOCK_SQUARE">Mock Square POS (Simulation & Tests)</option>
                  <option value="MOCK_CLOVER">Mock Clover POS (Simulation & Tests)</option>
                  <option value="MOCK_POS">Mock Generic POS (Testing)</option>
                  <option value="SQUARE">Square POS (Production V2 Adapter)</option>
                  <option value="GENERIC_REST">Generic REST POS API</option>
                </select>
                {provider.startsWith('MOCK') && (
                  <span style={{ fontSize: '0.6875rem', color: 'var(--gray-500)', marginTop: '2px', display: 'block' }}>
                    Mock adapters simulate full catalog sync and sales webhooks without external credentials.
                  </span>
                )}
              </div>

              <div className="form-group">
                <label className="form-label">Terminal / Integration Name *</label>
                <input
                  type="text"
                  required
                  value={integrationName}
                  onChange={(e) => setIntegrationName(e.target.value)}
                  placeholder="e.g. Downtown Register #1"
                  className="form-input"
                />
              </div>

              <div className="form-group">
                <label className="form-label">Provider API Key (Optional)</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Hashed on server; never stored in plaintext"
                  className="form-input"
                />
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setShowCreateModal(false)}
                  disabled={creating}
                >
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={creating}>
                  {creating ? 'Registering...' : 'Register Adapter'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
