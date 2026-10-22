import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  HeartHandshake,
  HelpCircle,
  Info,
  RefreshCw,
  Save,
  Server,
  ShieldAlert,
  Trash2,
  XCircle,
} from 'lucide-react';
import { api } from '../services/api';
import {
  ExpiryAlertHistory,
  ExpiryAlertItemSummary,
  ExpiryEvaluationResponse,
  TenantAlertConfig,
} from '../types';

export const ExpiryAlertsView: React.FC = () => {
  const [loading, setLoading] = useState<boolean>(true);
  const [evaluating, setEvaluating] = useState<boolean>(false);
  const [savingConfig, setSavingConfig] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [evaluation, setEvaluation] = useState<ExpiryEvaluationResponse | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>('ALL_AT_RISK');
  const [config, setConfig] = useState<TenantAlertConfig | null>(null);

  // Form states for config
  const [critHours, setCritHours] = useState<number>(24);
  const [warnDays, setWarnDays] = useState<number>(3);
  const [noticeDays, setNoticeDays] = useState<number>(7);
  const [autoDonate, setAutoDonate] = useState<boolean>(true);

  // Acknowledgment modal
  const [selectedAlertItem, setSelectedAlertItem] = useState<ExpiryAlertItemSummary | null>(null);
  const [ackAction, setAckAction] = useState<string>('MARKED_FOR_DONATION');

  const loadData = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const [evalRes, cfgRes] = await Promise.all([
        api.getExpiringInventory(statusFilter),
        api.getAlertConfig(),
      ]);
      setEvaluation(evalRes);
      setConfig(cfgRes);
      setCritHours(cfgRes.critical_threshold_hours);
      setWarnDays(cfgRes.warning_threshold_days);
      setNoticeDays(cfgRes.notice_threshold_days);
      setAutoDonate(cfgRes.auto_flag_for_donation);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load expiry data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [statusFilter]);

  const handleTriggerEvaluation = async () => {
    setEvaluating(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const res = await api.evaluateExpiry(false);
      setEvaluation(res);
      setSuccessMsg(
        `Evaluation complete! Evaluated ${res.summary.total_evaluated} lots (${res.summary.critical_count} critical, ${res.summary.expired_count} expired).`
      );
    } catch (err: any) {
      setErrorMsg(err.message || 'Evaluation run failed');
    } finally {
      setEvaluating(false);
    }
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingConfig(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const updated = await api.updateAlertConfig({
        critical_threshold_hours: critHours,
        warning_threshold_days: warnDays,
        notice_threshold_days: noticeDays,
        auto_flag_for_donation: autoDonate,
      });
      setConfig(updated);
      setSuccessMsg('Alert threshold configuration updated successfully!');
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to update alert configuration');
    } finally {
      setSavingConfig(false);
    }
  };

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-900)' }}>Expiry Tracking & Waste Horizons</h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
            Regulatory-compliant food classification (USDA FoodKeeper / FDA Food Code 2022) with automated donation guardrails.
          </p>
        </div>

        <button className="btn btn-primary" onClick={handleTriggerEvaluation} disabled={evaluating}>
          <RefreshCw className={evaluating ? 'animate-spin' : ''} size={16} />
          {evaluating ? 'Evaluating Items...' : 'Run Expiry Evaluation'}
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

      {/* Summary Cards */}
      {evaluation && (
        <div className="grid-cols-4" style={{ marginBottom: '20px' }}>
          <div className="card">
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gray-500)', textTransform: 'uppercase' }}>
              Critical Risk (≤24h)
            </span>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--danger)', marginTop: '4px' }}>
              {evaluation.summary.critical_count} lots
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Immediate dispatch required</div>
          </div>

          <div className="card">
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gray-500)', textTransform: 'uppercase' }}>
              Warning (≤3 days)
            </span>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--warning)', marginTop: '4px' }}>
              {evaluation.summary.warning_count} lots
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Apply 25-50% markdown</div>
          </div>

          <div className="card">
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gray-500)', textTransform: 'uppercase' }}>
              Notice (≤7 days)
            </span>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--primary)', marginTop: '4px' }}>
              {evaluation.summary.notice_count} lots
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Rotate FIFO stock</div>
          </div>

          <div className="card">
            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gray-500)', textTransform: 'uppercase' }}>
              Expired (Past Date)
            </span>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#475569', marginTop: '4px' }}>
              {evaluation.summary.expired_count} lots
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--danger)', fontWeight: 600 }}>Strictly Ineligible for Donation</div>
          </div>
        </div>
      )}

      {/* Main Content Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '20px' }}>
        {/* At-Risk Items Table */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>At-Risk Inventory Lots</h3>
            <div style={{ display: 'flex', gap: '6px' }}>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="form-select"
                style={{ fontSize: '0.8125rem', padding: '4px 8px' }}
              >
                <option value="ALL_AT_RISK">All At-Risk Items</option>
                <option value="CRITICAL">Critical Only (≤24h)</option>
                <option value="WARNING">Warning Only (≤3d)</option>
                <option value="NOTICE">Notice Only (≤7d)</option>
                <option value="EXPIRED">Expired Lots Only</option>
              </select>
            </div>
          </div>

          <div className="table-container" style={{ maxHeight: '450px', overflowY: 'auto' }}>
            <table>
              <thead>
                <tr>
                  <th>Product & Category</th>
                  <th>Quantity</th>
                  <th>Expiry & Time Left</th>
                  <th>Horizon Level</th>
                  <th>Donation Safety</th>
                  <th>Recommended Action</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: '32px', color: 'var(--gray-500)' }}>
                      Loading expiry evaluations...
                    </td>
                  </tr>
                ) : !evaluation || evaluation.items.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: '32px', color: 'var(--gray-500)' }}>
                      No inventory lots match this risk threshold. All stock is currently fresh!
                    </td>
                  </tr>
                ) : (
                  evaluation.items.map((item) => (
                    <tr key={item.item_id}>
                      <td>
                        <div style={{ fontWeight: 600, color: 'var(--gray-900)' }}>{item.name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>{item.category_name}</div>
                      </td>
                      <td>
                        <strong>{item.current_quantity}</strong> {item.unit}
                      </td>
                      <td>
                        <div style={{ fontSize: '0.8125rem', fontWeight: 600 }}>{item.expiry_date}</div>
                        <div style={{ fontSize: '0.75rem', color: item.days_remaining <= 1 ? 'var(--danger)' : 'var(--gray-500)' }}>
                          {item.days_remaining <= 0 ? '0.0 days (Expired)' : `${item.days_remaining.toFixed(1)} days remaining`}
                        </div>
                      </td>
                      <td>
                        <span
                          className={`badge ${
                            item.alert_level === 'CRITICAL'
                              ? 'badge-critical'
                              : item.alert_level === 'WARNING'
                              ? 'badge-warning'
                              : item.alert_level === 'NOTICE'
                              ? 'badge-notice'
                              : item.alert_level === 'EXPIRED'
                              ? 'badge-expired'
                              : 'badge-fresh'
                          }`}
                        >
                          {item.alert_level}
                        </span>
                      </td>
                      <td>
                        {item.donation_eligible ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--success)', fontSize: '0.75rem', fontWeight: 600 }}>
                            <CheckCircle2 size={14} /> Eligible for Rescue
                          </div>
                        ) : (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--danger)', fontSize: '0.75rem', fontWeight: 600 }}>
                            <XCircle size={14} /> Ineligible (Past Date)
                          </div>
                        )}
                      </td>
                      <td style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gray-700)' }}>
                        {item.recommended_action}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Sidebar: Config & Diagnostics */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Tenant Alert Threshold Configuration */}
          <div className="card">
            <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '12px' }}>
              Alert Threshold Horizons
            </h3>
            <form onSubmit={handleSaveConfig}>
              <div className="form-group">
                <label className="form-label">Critical Horizon (Hours)</label>
                <input
                  type="number"
                  required
                  min="1"
                  max="168"
                  value={critHours}
                  onChange={(e) => setCritHours(parseInt(e.target.value) || 24)}
                  className="form-input"
                />
                <span style={{ fontSize: '0.6875rem', color: 'var(--gray-500)' }}>Default: 24h (1 day)</span>
              </div>

              <div className="form-group">
                <label className="form-label">Warning Horizon (Days)</label>
                <input
                  type="number"
                  required
                  min="1"
                  max="30"
                  value={warnDays}
                  onChange={(e) => setWarnDays(parseInt(e.target.value) || 3)}
                  className="form-input"
                />
                <span style={{ fontSize: '0.6875rem', color: 'var(--gray-500)' }}>Default: 3 days</span>
              </div>

              <div className="form-group">
                <label className="form-label">Notice Horizon (Days)</label>
                <input
                  type="number"
                  required
                  min="2"
                  max="90"
                  value={noticeDays}
                  onChange={(e) => setNoticeDays(parseInt(e.target.value) || 7)}
                  className="form-input"
                />
                <span style={{ fontSize: '0.6875rem', color: 'var(--gray-500)' }}>Default: 7 days</span>
              </div>

              <div className="form-group">
                <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                  <input
                    type="checkbox"
                    checked={autoDonate}
                    onChange={(e) => setAutoDonate(e.target.checked)}
                  />
                  <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>Auto-Flag Qualifying Stock for Donation</span>
                </label>
              </div>

              <button type="submit" disabled={savingConfig} className="btn btn-primary" style={{ width: '100%' }}>
                <Save size={14} /> {savingConfig ? 'Saving Settings...' : 'Save Thresholds'}
              </button>
            </form>
          </div>

          {/* Scheduler Diagnostics Card */}
          {evaluation && evaluation.scheduler_diagnostics && (
            <div className="card" style={{ background: '#f8fafc', border: '1px solid var(--border)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <Server size={18} color="var(--gray-700)" />
                <h4 style={{ fontSize: '0.875rem', fontWeight: 700 }}>Scheduler Telemetry</h4>
              </div>

              <div style={{ fontSize: '0.75rem', color: 'var(--gray-700)', marginBottom: '8px' }}>
                <strong>Execution Mode:</strong> {evaluation.scheduler_diagnostics.scheduler_mode}
              </div>

              {evaluation.scheduler_diagnostics.missing_configurations.length > 0 && (
                <div style={{ marginBottom: '10px' }}>
                  <span style={{ fontSize: '0.6875rem', fontWeight: 700, color: 'var(--warning)', textTransform: 'uppercase' }}>
                    Missing Background Daemons:
                  </span>
                  <ul style={{ paddingLeft: '16px', fontSize: '0.75rem', color: 'var(--gray-600)', marginTop: '4px' }}>
                    {evaluation.scheduler_diagnostics.missing_configurations.map((item, idx) => (
                      <li key={idx}>{item}</li>
                    ))}
                  </ul>
                </div>
              )}

              <p style={{ fontSize: '0.6875rem', color: 'var(--gray-500)', lineHeight: '1.4' }}>
                {evaluation.scheduler_diagnostics.recommendation}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
