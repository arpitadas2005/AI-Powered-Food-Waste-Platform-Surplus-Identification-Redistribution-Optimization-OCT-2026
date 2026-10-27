import React, { useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Boxes,
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  DollarSign,
  Download,
  Globe,
  HeartHandshake,
  Leaf,
  PackageCheck,
  Plus,
  QrCode,
  RefreshCw,
  Sparkles,
  TrendingUp,
  Truck,
  Upload,
  Users,
} from 'lucide-react';
import { api } from '../services/api';
import {
  BusinessDashboardSummary,
  ExpiryEvaluationResponse,
  InventoryItem,
  NgoDashboardSummary,
  StockTransaction,
  SustainabilityMetrics,
  TimeSeriesPoint,
  TimeSeriesResponse,
} from '../types';

type DashboardSection = 'business' | 'ngo' | 'sustainability';
type DateFilter = '7d' | '30d' | '90d' | 'all';

interface DashboardViewProps {
  tenantSlug?: string;
  initialSection?: DashboardSection;
  onNavigate: (tab: any) => void;
  onOpenCreateItem: () => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  tenantSlug,
  initialSection,
  onNavigate,
  onOpenCreateItem,
}) => {
  const isNgoTenant = tenantSlug === 'community-food-bank';
  const [section, setSection] = useState<DashboardSection>(
    initialSection || (isNgoTenant ? 'ngo' : 'business')
  );

  const [dateFilter, setDateFilter] = useState<DateFilter>('30d');
  const [loading, setLoading] = useState<boolean>(true);
  const [exportingCsv, setExportingCsv] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Business state
  const [businessSummary, setBusinessSummary] = useState<BusinessDashboardSummary | null>(null);
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [expiryData, setExpiryData] = useState<ExpiryEvaluationResponse | null>(null);
  const [recentTransactions, setRecentTransactions] = useState<StockTransaction[]>([]);

  // NGO state
  const [ngoSummary, setNgoSummary] = useState<NgoDashboardSummary | null>(null);

  // Sustainability state
  const [sustainability, setSustainability] = useState<SustainabilityMetrics | null>(null);
  const [timeSeries, setTimeSeries] = useState<TimeSeriesResponse | null>(null);

  const calculateDateRange = (filter: DateFilter): { date_from?: string; date_to?: string } => {
    const today = new Date();
    const toIso = (d: Date) => d.toISOString().split('T')[0];
    const date_to = toIso(today);

    if (filter === 'all') return {};
    const d = new Date();
    if (filter === '7d') d.setDate(d.getDate() - 7);
    if (filter === '30d') d.setDate(d.getDate() - 30);
    if (filter === '90d') d.setDate(d.getDate() - 90);
    return { date_from: toIso(d), date_to };
  };

  const loadData = async () => {
    setLoading(true);
    setError(null);

    const dates = calculateDateRange(dateFilter);

    try {
      if (section === 'business') {
        const [biz, invRes, expRes] = await Promise.all([
          api.getBusinessDashboardSummary().catch(() => null),
          api.listInventory({ size: 100 }).catch(() => ({ data: [], pagination: { total: 0 } })),
          api.getExpiringInventory('ALL_AT_RISK').catch(() => null),
        ]);

        if (biz) setBusinessSummary(biz);
        setItems(invRes.data);
        setTotalCount(invRes.pagination.total);
        setExpiryData(expRes);

        // Fetch recent ledger transactions
        const txPromises = invRes.data.slice(0, 5).map((item) =>
          api.getItemTransactions(item.id).catch(() => [])
        );
        const allTxLists = await Promise.all(txPromises);
        const flattened = allTxLists.flat().sort((a, b) => (b.created_at > a.created_at ? 1 : -1));
        setRecentTransactions(flattened.slice(0, 6));
      } else if (section === 'ngo') {
        const ngo = await api.getNgoDashboardSummary();
        setNgoSummary(ngo);
      } else if (section === 'sustainability') {
        const [sust, ts] = await Promise.all([
          api.getSustainabilityMetrics(dates),
          api.getTimeSeriesAnalytics({ ...dates, interval: 'daily' }),
        ]);
        setSustainability(sust);
        setTimeSeries(ts);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load dashboard metrics');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [section, dateFilter, tenantSlug]);

  const handleExportCsv = async () => {
    setExportingCsv(true);
    try {
      const dates = calculateDateRange(dateFilter);
      const blob = await api.exportSustainabilityCsv(dates);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `redistribution_sustainability_report_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(`Export failed: ${err.message}`);
    } finally {
      setExportingCsv(false);
    }
  };

  // Inventory fallback calculations if businessSummary is loading
  const totalStockValue =
    businessSummary?.total_stock_value ??
    items.reduce((acc, curr) => acc + Number(curr.current_quantity) * Number(curr.cost_per_unit), 0);
  const criticalCount = expiryData ? expiryData.summary.critical_count : 0;
  const expiredCount = expiryData ? expiryData.summary.expired_count : 0;
  const warningCount = expiryData ? expiryData.summary.warning_count : 0;
  const atRiskValue = expiryData ? expiryData.summary.total_at_risk_value : 0;

  return (
    <div>
      {/* Top Header & Section Selector */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
          marginBottom: '20px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-900)' }}>
              {section === 'business' && '🏬 Business Operations & Surplus Dashboard'}
              {section === 'ngo' && '🤝 NGO Recipient Portal & Allocation Dashboard'}
              {section === 'sustainability' && '🌍 Sustainability & Impact Analytics'}
            </h2>
            <span
              style={{
                fontSize: '0.75rem',
                padding: '2px 8px',
                borderRadius: '12px',
                background: isNgoTenant ? '#dbeafe' : '#dcfce7',
                color: isNgoTenant ? '#1d4ed8' : '#15803d',
                fontWeight: 600,
              }}
            >
              {isNgoTenant ? 'NGO Context' : 'Commercial Food Business'}
            </span>
          </div>
          <p style={{ fontSize: '0.875rem', color: 'var(--gray-500)', marginTop: '4px' }}>
            {section === 'business' &&
              'Live double-entry inventory ledger, waste risk assessments, active surplus, and claim workflows.'}
            {section === 'ngo' &&
              'Manage food bank intake, matched available donations, pickup logistics, and community meals.'}
            {section === 'sustainability' &&
              'Verified EPA WARM v15 carbon avoidance, Feeding America meal metrics, and loss prevention.'}
          </p>
        </div>

        {/* View Switcher Pills */}
        <div style={{ display: 'flex', gap: '6px', background: 'var(--gray-100)', padding: '4px', borderRadius: '10px' }}>
          <button
            onClick={() => setSection('business')}
            className={`btn ${section === 'business' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ fontSize: '0.8125rem', padding: '6px 12px' }}
          >
            <Boxes size={14} /> Business
          </button>
          <button
            onClick={() => setSection('ngo')}
            className={`btn ${section === 'ngo' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ fontSize: '0.8125rem', padding: '6px 12px' }}
          >
            <HeartHandshake size={14} /> NGO Portal
          </button>
          <button
            onClick={() => setSection('sustainability')}
            className={`btn ${section === 'sustainability' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ fontSize: '0.8125rem', padding: '6px 12px' }}
          >
            <BarChart3 size={14} /> Sustainability
          </button>
          <button
            onClick={loadData}
            title="Refresh current metrics"
            className="btn btn-secondary"
            style={{ padding: '6px 10px' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Error alert */}
      {error && (
        <div
          style={{
            padding: '12px 16px',
            background: 'var(--danger-bg)',
            color: 'var(--danger)',
            borderRadius: '8px',
            marginBottom: '16px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <AlertCircle size={18} />
          <span>
            <strong>Error loading dashboard:</strong> {error}
          </span>
        </div>
      )}

      {loading && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            minHeight: '260px',
            gap: '10px',
          }}
        >
          <RefreshCw className="animate-spin" size={24} color="var(--primary)" />
          <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
            Calculating persisted ledger & redistribution analytics...
          </span>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION 1: BUSINESS OPERATIONS VIEW                                       */}
      {/* ========================================================================= */}
      {!loading && section === 'business' && (
        <div>
          {/* Critical Expiry Alert Banner */}
          {(criticalCount > 0 || expiredCount > 0) && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '16px',
                background: 'var(--danger-bg)',
                border: '1px solid #fecaca',
                borderRadius: '12px',
                marginBottom: '24px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <AlertCircle size={28} color="var(--danger)" />
                <div>
                  <h4 style={{ fontWeight: 700, color: '#991b1b', fontSize: '0.9375rem' }}>
                    Action Required: {criticalCount} Critical & {expiredCount} Expired Lots Detected
                  </h4>
                  <p style={{ fontSize: '0.8125rem', color: '#b91c1c' }}>
                    Total at-risk food value is ${Number(atRiskValue).toFixed(2)}. Flag items for NGO donation hold or markdown.
                  </p>
                </div>
              </div>
              <button className="btn btn-danger" onClick={() => onNavigate('expiry')}>
                Review At-Risk Stock
              </button>
            </div>
          )}

          {/* Primary Commercial Inventory Metrics */}
          <div className="grid-cols-4" style={{ marginBottom: '20px' }}>
            {/* Total Stock */}
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
                <span>TOTAL STOCK IN LEDGER</span>
                <Boxes size={18} color="var(--primary)" />
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: 'var(--gray-900)' }}>
                {businessSummary?.total_inventory_items ?? totalCount}{' '}
                <span style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--gray-500)' }}>SKUs</span>
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--success)', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <CheckCircle2 size={12} /> Double-entry verified
              </div>
            </div>

            {/* Valuation */}
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
                <span>INVENTORY VALUATION</span>
                <DollarSign size={18} color="var(--success)" />
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: 'var(--gray-900)' }}>
                ${Number(totalStockValue).toFixed(2)}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                Across all active categories
              </div>
            </div>

            {/* Expiring Soon */}
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
                <span>EXPIRING SOON (≤3 DAYS)</span>
                <Clock size={18} color="var(--warning)" />
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: 'var(--warning)' }}>
                {businessSummary?.items_expiring_soon_count ?? (criticalCount + warningCount)}{' '}
                <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>lots</span>
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--warning)', marginTop: '4px' }}>
                ${businessSummary?.at_risk_value ?? Number(atRiskValue).toFixed(2)} at risk of waste
              </div>
            </div>

            {/* High ML Waste Risk */}
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
                <span>HIGH / CRITICAL RISK</span>
                <AlertTriangle size={18} color="var(--danger)" />
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: 'var(--danger)' }}>
                {businessSummary?.high_risk_items_count ?? criticalCount}{' '}
                <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>items</span>
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                Model demand &lt; remaining shelf-life
              </div>
            </div>
          </div>

          {/* Surplus & Redistribution Operations Cards */}
          <div style={{ marginBottom: '24px' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--gray-900)', marginBottom: '12px' }}>
              Surplus Donation & NGO Redistribution Pipeline
            </h3>
            <div className="grid-cols-4">
              <div className="card" style={{ borderLeft: '4px solid var(--primary)' }}>
                <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--gray-500)' }}>
                  ACTIVE SURPLUS LISTINGS
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, marginTop: '6px', color: 'var(--primary)' }}>
                  {businessSummary?.active_surplus_listings_count ?? 0}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                  Open for NGO requests
                </div>
              </div>

              <div className="card" style={{ borderLeft: '4px solid #f59e0b' }}>
                <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--gray-500)' }}>
                  INCOMING CLAIM REQUESTS
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, marginTop: '6px', color: '#b45309' }}>
                  {businessSummary?.pending_claims_count ?? 0}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                  Awaiting review & accept
                </div>
              </div>

              <div className="card" style={{ borderLeft: '4px solid #3b82f6' }}>
                <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--gray-500)' }}>
                  UPCOMING SCHEDULED PICKUPS
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, marginTop: '6px', color: '#1d4ed8' }}>
                  {businessSummary?.upcoming_pickups_count ?? 0}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                  Logistics slots scheduled
                </div>
              </div>

              <div className="card" style={{ borderLeft: '4px solid #10b981' }}>
                <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--gray-500)' }}>
                  COMPLETED REDISTRIBUTIONS
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, marginTop: '6px', color: '#047857' }}>
                  {businessSummary?.completed_transfers_count ?? 0}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                  ${(businessSummary?.total_value_rescued ?? 0).toFixed(2)} value rescued
                </div>
              </div>
            </div>
          </div>

          {/* Quick Action Navigation Bar */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
              gap: '12px',
              marginBottom: '24px',
            }}
          >
            <button
              onClick={() => onNavigate('surplus')}
              className="card"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                cursor: 'pointer',
                textAlign: 'left',
                border: '1px solid var(--border)',
              }}
            >
              <div style={{ background: '#dcfce7', padding: '10px', borderRadius: '8px' }}>
                <HeartHandshake size={20} color="#15803d" />
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>Surplus & Claims Hub</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Earmark stock & review NGOs</div>
              </div>
            </button>

            <button
              onClick={() => onNavigate('expiry')}
              className="card"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                cursor: 'pointer',
                textAlign: 'left',
                border: '1px solid var(--border)',
              }}
            >
              <div style={{ background: '#fee2e2', padding: '10px', borderRadius: '8px' }}>
                <Clock size={20} color="#b91c1c" />
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>Expiry Engine</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Evaluate waste horizons</div>
              </div>
            </button>

            <button
              onClick={() => onNavigate('scanner')}
              className="card"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                cursor: 'pointer',
                textAlign: 'left',
                border: '1px solid var(--border)',
              }}
            >
              <div style={{ background: 'var(--primary-light)', padding: '10px', borderRadius: '8px' }}>
                <QrCode size={20} color="var(--primary)" />
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>Barcode / QR Scan</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Mobile camera & manual SKU</div>
              </div>
            </button>

            <button
              onClick={() => onNavigate('csv')}
              className="card"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                cursor: 'pointer',
                textAlign: 'left',
                border: '1px solid var(--border)',
              }}
            >
              <div style={{ background: '#fef3c7', padding: '10px', borderRadius: '8px' }}>
                <Upload size={20} color="#b45309" />
              </div>
              <div>
                <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>CSV Bulk Ingestion</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Preview & partial commit</div>
              </div>
            </button>
          </div>

          {/* Double-entry Ledger Transactions */}
          <div className="card">
            <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '12px' }}>
              Recent Double-Entry Stock Ledger Transactions
            </h3>
            {recentTransactions.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--gray-500)', fontSize: '0.875rem' }}>
                No stock adjustments recorded yet. Items will log double-entry transactions here.
              </div>
            ) : (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Timestamp</th>
                      <th>Transaction Type</th>
                      <th>Quantity Delta</th>
                      <th>Before → After</th>
                      <th>Reason & Reference</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentTransactions.map((tx) => (
                      <tr key={tx.id}>
                        <td style={{ fontSize: '0.8125rem', color: 'var(--gray-500)' }}>
                          {new Date(tx.created_at).toLocaleString()}
                        </td>
                        <td>
                          <span className="badge badge-notice">{tx.transaction_type}</span>
                        </td>
                        <td
                          style={{
                            fontWeight: 700,
                            color: tx.quantity_change >= 0 ? 'var(--success)' : 'var(--danger)',
                          }}
                        >
                          {tx.quantity_change > 0 ? `+${tx.quantity_change}` : tx.quantity_change}
                        </td>
                        <td style={{ fontSize: '0.8125rem' }}>
                          {tx.quantity_before} → <strong>{tx.quantity_after}</strong>
                        </td>
                        <td style={{ fontSize: '0.8125rem', color: 'var(--gray-700)' }}>
                          {tx.reason || tx.reference_type || 'System adjustment'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION 2: NGO RECIPIENT PORTAL VIEW                                      */}
      {/* ========================================================================= */}
      {!loading && section === 'ngo' && ngoSummary && (
        <div>
          {/* NGO Profile Header Banner */}
          <div
            className="card"
            style={{
              background: 'linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%)',
              color: 'white',
              marginBottom: '20px',
              padding: '20px 24px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '1.25rem', fontWeight: 800 }}>{ngoSummary.organization_name}</span>
                  <span
                    style={{
                      background: ngoSummary.is_verified ? '#10b981' : '#f59e0b',
                      color: 'white',
                      fontSize: '0.6875rem',
                      padding: '2px 8px',
                      borderRadius: '12px',
                      fontWeight: 700,
                    }}
                  >
                    {ngoSummary.is_verified ? '✓ VERIFIED RECIPIENT' : 'VERIFICATION PENDING'}
                  </span>
                </div>
                <p style={{ fontSize: '0.875rem', opacity: 0.9, marginTop: '4px' }}>
                  Organization Type: <strong>{ngoSummary.organization_type}</strong> • Service Radius:{' '}
                  <strong>{ngoSummary.service_radius_km} km</strong>
                </p>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '8px' }}>
                  {ngoSummary.storage_facilities.map((fac) => (
                    <span
                      key={fac}
                      style={{
                        fontSize: '0.6875rem',
                        background: 'rgba(255,255,255,0.2)',
                        padding: '2px 8px',
                        borderRadius: '4px',
                      }}
                    >
                      {fac}
                    </span>
                  ))}
                </div>
              </div>

              <button
                className="btn btn-secondary"
                onClick={() => onNavigate('surplus')}
                style={{ background: 'white', color: '#1e3a8a', fontWeight: 700 }}
              >
                Browse Surplus Feed
              </button>
            </div>
          </div>

          {/* Operational Intake KPIs */}
          <div className="grid-cols-4" style={{ marginBottom: '20px' }}>
            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
                <span>AVAILABLE SURPLUS</span>
                <Sparkles size={18} color="#3b82f6" />
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: '#1d4ed8' }}>
                {ngoSummary.eligible_surplus_listings_count}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                Matching your accepted criteria
              </div>
            </div>

            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
                <span>PENDING CLAIMS</span>
                <Clock size={18} color="#f59e0b" />
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: '#b45309' }}>
                {ngoSummary.pending_claims_count}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                Submitted to donor businesses
              </div>
            </div>

            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
                <span>ACCEPTED / READY</span>
                <PackageCheck size={18} color="#10b981" />
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: '#047857' }}>
                {ngoSummary.accepted_claims_count}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                Ready for logistics pickup
              </div>
            </div>

            <div className="card">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
                <span>SCHEDULED PICKUPS</span>
                <Truck size={18} color="#6366f1" />
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: '#4338ca' }}>
                {ngoSummary.upcoming_pickups_count}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                Upcoming transport windows
              </div>
            </div>
          </div>

          {/* Social Impact & Food Received Cards */}
          <div className="card" style={{ marginBottom: '20px' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '16px' }}>
              Cumulative Food Assistance & Rescue Impact
            </h3>
            <div className="grid-cols-4">
              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gray-500)', textTransform: 'uppercase' }}>
                  Total Food Rescued
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--gray-900)', marginTop: '4px' }}>
                  {ngoSummary.total_food_rescued_kg.toFixed(1)} <span style={{ fontSize: '0.875rem' }}>kg</span>
                </div>
                {ngoSummary.total_food_rescued_units > 0 && (
                  <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                    + {ngoSummary.total_food_rescued_units} discrete units
                  </div>
                )}
              </div>

              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gray-500)', textTransform: 'uppercase' }}>
                  Community Meals Served
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--success)', marginTop: '4px' }}>
                  {ngoSummary.meals_provided.toLocaleString()}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                  @ 0.42 kg/meal (USDA standard)
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gray-500)', textTransform: 'uppercase' }}>
                  Grocery Value Received
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--gray-900)', marginTop: '4px' }}>
                  ${ngoSummary.value_received.toFixed(2)}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                  Direct budget savings for mission
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--gray-500)', textTransform: 'uppercase' }}>
                  Completed Intakes
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--gray-900)', marginTop: '4px' }}>
                  {ngoSummary.completed_collections_count}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                  Verified physical handovers
                </div>
              </div>
            </div>
          </div>

          {/* Recent Claims Table */}
          <div className="card">
            <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '12px' }}>
              Recent NGO Claim Requests & Status
            </h3>
            {ngoSummary.recent_claims.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--gray-500)', fontSize: '0.875rem' }}>
                No surplus claims placed yet. Explore the surplus feed to request food donations.
              </div>
            ) : (
              <div className="table-container">
                <table>
                  <thead>
                    <tr>
                      <th>Claim ID</th>
                      <th>Item Description</th>
                      <th>Requested Quantity</th>
                      <th>Status</th>
                      <th>Pickup Window</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ngoSummary.recent_claims.map((c) => (
                      <tr key={c.claim_id}>
                        <td style={{ fontSize: '0.75rem', fontFamily: 'monospace' }}>{c.claim_id.slice(0, 8)}...</td>
                        <td style={{ fontWeight: 600 }}>{c.listing_title}</td>
                        <td>
                          {c.quantity} {c.unit}
                        </td>
                        <td>
                          <span
                            className={`badge ${
                              c.status === 'COMPLETED'
                                ? 'badge-success'
                                : c.status === 'ACCEPTED' || c.status === 'READY_FOR_PICKUP'
                                ? 'badge-notice'
                                : c.status === 'REQUESTED' || c.status === 'PENDING'
                                ? 'badge-warning'
                                : 'badge-danger'
                            }`}
                          >
                            {c.status}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.8125rem', color: 'var(--gray-500)' }}>
                          {c.pickup_time ? new Date(c.pickup_time).toLocaleString() : 'Pending confirmation'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* SECTION 3: SUSTAINABILITY & IMPACT ANALYTICS VIEW                          */}
      {/* ========================================================================= */}
      {!loading && section === 'sustainability' && sustainability && (
        <div>
          {/* Controls Bar: Date Filter + Export CSV */}
          <div
            className="card"
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: '12px',
              marginBottom: '20px',
              padding: '12px 16px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Calendar size={18} color="var(--gray-500)" />
              <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--gray-700)' }}>
                Reporting Horizon:
              </span>
              <div style={{ display: 'flex', gap: '4px' }}>
                {(['7d', '30d', '90d', 'all'] as DateFilter[]).map((f) => (
                  <button
                    key={f}
                    onClick={() => setDateFilter(f)}
                    className={`btn ${dateFilter === f ? 'btn-primary' : 'btn-secondary'}`}
                    style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                  >
                    {f === '7d' && 'Last 7 Days'}
                    {f === '30d' && 'Last 30 Days'}
                    {f === '90d' && 'Last 90 Days'}
                    {f === 'all' && 'All Time'}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={handleExportCsv}
              disabled={exportingCsv}
              className="btn btn-secondary"
              style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8125rem' }}
            >
              <Download size={14} />
              {exportingCsv ? 'Generating CSV...' : 'Export Verified CSV Report'}
            </button>
          </div>

          {/* Primary Environmental & Social Impact Cards */}
          <div className="grid-cols-4" style={{ marginBottom: '20px' }}>
            {/* Weight Rescued */}
            <div className="card" style={{ borderTop: '4px solid #10b981' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
                <span>VERIFIED FOOD RESCUED</span>
                <Boxes size={18} color="#10b981" />
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: 'var(--gray-900)' }}>
                {sustainability.total_rescued_weight_kg.toFixed(1)}{' '}
                <span style={{ fontSize: '0.875rem', fontWeight: 500, color: 'var(--gray-500)' }}>kg</span>
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                {sustainability.total_rescued_units_count > 0
                  ? `+ ${sustainability.total_rescued_units_count} packaged units`
                  : 'Mass recorded from completed transfers'}
              </div>
            </div>

            {/* Avoided Emissions */}
            <div className="card" style={{ borderTop: '4px solid #059669' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
                <span>AVOIDED GHG EMISSIONS</span>
                <Leaf size={18} color="#059669" />
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: '#059669' }}>
                {sustainability.co2e_avoided_kg.toFixed(1)}{' '}
                <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>kg CO₂e</span>
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                EPA WARM v15 (2.5 kg CO₂e / kg food)
              </div>
            </div>

            {/* Meals Provided */}
            <div className="card" style={{ borderTop: '4px solid #3b82f6' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
                <span>MEAL EQUIVALENTS</span>
                <HeartHandshake size={18} color="#3b82f6" />
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: '#1d4ed8' }}>
                {sustainability.total_meals_provided.toLocaleString()}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                Feeding America (0.42 kg/meal)
              </div>
            </div>

            {/* Value Rescued */}
            <div className="card" style={{ borderTop: '4px solid #f59e0b' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--gray-500)', fontSize: '0.8125rem', fontWeight: 600 }}>
                <span>FINANCIAL VALUE RESCUED</span>
                <DollarSign size={18} color="#f59e0b" />
              </div>
              <div style={{ fontSize: '1.75rem', fontWeight: 800, marginTop: '8px', color: 'var(--gray-900)' }}>
                ${sustainability.total_value_rescued.toFixed(2)}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '4px' }}>
                From {sustainability.completed_claims_count} completed transfers
              </div>
            </div>
          </div>

          {/* Tangible Environmental Equivalencies Section */}
          <div className="card" style={{ marginBottom: '20px', background: '#f0fdf4', border: '1px solid #bbf7d0' }}>
            <h3 style={{ fontSize: '0.9375rem', fontWeight: 700, color: '#166534', marginBottom: '12px' }}>
              🌱 Real-World Environmental Equivalencies (EPA Impact Standard)
            </h3>
            <div className="grid-cols-4">
              <div>
                <div style={{ fontSize: '0.75rem', color: '#166534', fontWeight: 600 }}>URBAN TREES PLANTED</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#14532d', marginTop: '4px' }}>
                  {sustainability.equivalencies.trees_planted_equivalent.toFixed(1)}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#166534' }}>
                  Tree seedlings grown for 10 years
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.75rem', color: '#166534', fontWeight: 600 }}>CAR MILES AVOIDED</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#14532d', marginTop: '4px' }}>
                  {sustainability.equivalencies.passenger_car_miles_avoided.toFixed(0)} mi
                </div>
                <div style={{ fontSize: '0.75rem', color: '#166534' }}>
                  Passenger vehicle miles off the road
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.75rem', color: '#166534', fontWeight: 600 }}>DONOR BUSINESSES</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#14532d', marginTop: '4px' }}>
                  {sustainability.participating_businesses_count}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#166534' }}>
                  Participating food businesses
                </div>
              </div>

              <div>
                <div style={{ fontSize: '0.75rem', color: '#166534', fontWeight: 600 }}>RECIPIENT PARTNERS</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, color: '#14532d', marginTop: '4px' }}>
                  {sustainability.participating_ngos_count}
                </div>
                <div style={{ fontSize: '0.75rem', color: '#166534' }}>
                  NGOs, kitchens & pantries benefiting
                </div>
              </div>
            </div>
          </div>

          {/* Interactive Pure-SVG Time Series Chart */}
          <div className="card" style={{ marginBottom: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--gray-900)' }}>
                  Food Redistribution & Meals Provided Timeline
                </h3>
                <p style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                  Chronological progression of rescued kilograms and community meals.
                </p>
              </div>
              <div style={{ display: 'flex', gap: '16px', fontSize: '0.75rem', fontWeight: 600 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#10b981' }}>
                  <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#10b981' }} />
                  Food Rescued (kg)
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#3b82f6' }}>
                  <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#3b82f6' }} />
                  Meals Provided
                </span>
              </div>
            </div>

            {(!timeSeries || timeSeries.points.length === 0) ? (
              <div
                style={{
                  height: '220px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexDirection: 'column',
                  gap: '8px',
                  color: 'var(--gray-400)',
                  background: 'var(--gray-50)',
                  borderRadius: '8px',
                }}
              >
                <TrendingUp size={32} />
                <span style={{ fontSize: '0.875rem' }}>
                  No completed redistribution transfers logged in this date range.
                </span>
                <span style={{ fontSize: '0.75rem' }}>
                  Once donor claims are marked COMPLETED, verified trend points render automatically.
                </span>
              </div>
            ) : (
              <div style={{ width: '100%', overflowX: 'auto' }}>
                {(() => {
                  const pts = timeSeries.points;
                  const maxKg = Math.max(...pts.map((p) => p.rescued_kg), 10);
                  const width = Math.max(pts.length * 60, 600);
                  const height = 220;
                  const padX = 40;
                  const padY = 30;
                  const plotW = width - padX * 2;
                  const plotH = height - padY * 2;

                  return (
                    <svg width={width} height={height} style={{ display: 'block', margin: '0 auto' }}>
                      {/* Grid lines */}
                      {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
                        const y = padY + plotH * (1 - ratio);
                        return (
                          <g key={ratio}>
                            <line
                              x1={padX}
                              y1={y}
                              x2={width - padX}
                              y2={y}
                              stroke="var(--gray-200)"
                              strokeDasharray="4,4"
                            />
                            <text
                              x={padX - 8}
                              y={y + 4}
                              fontSize="10"
                              fill="var(--gray-400)"
                              textAnchor="end"
                            >
                              {(maxKg * ratio).toFixed(0)}kg
                            </text>
                          </g>
                        );
                      })}

                      {/* Line chart for Rescued Kg */}
                      {pts.length > 1 && (
                        <polyline
                          fill="none"
                          stroke="#10b981"
                          strokeWidth="2.5"
                          points={pts
                            .map((p, i) => {
                              const x = padX + (i / (pts.length - 1)) * plotW;
                              const y = padY + plotH * (1 - p.rescued_kg / maxKg);
                              return `${x},${y}`;
                            })
                            .join(' ')}
                        />
                      )}

                      {/* Bar / Points representation */}
                      {pts.map((p, i) => {
                        const x = pts.length > 1 ? padX + (i / (pts.length - 1)) * plotW : padX + plotW / 2;
                        const y = padY + plotH * (1 - p.rescued_kg / maxKg);
                        return (
                          <g key={p.date}>
                            <circle cx={x} cy={y} r="5" fill="#10b981" stroke="#ffffff" strokeWidth="2" />
                            <text
                              x={x}
                              y={height - 8}
                              fontSize="9"
                              fill="var(--gray-500)"
                              textAnchor="middle"
                            >
                              {p.date.slice(5)}
                            </text>
                            <title>{`${p.date}: ${p.rescued_kg} kg rescued (${p.meals_provided} meals)`}</title>
                          </g>
                        );
                      })}
                    </svg>
                  );
                })()}
              </div>
            )}
          </div>

          {/* Category Breakdown Progress & Table */}
          <div className="card">
            <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '16px' }}>
              Redistribution Breakdown by Food Category
            </h3>
            {sustainability.category_breakdown.length === 0 ? (
              <div style={{ padding: '24px', textAlign: 'center', color: 'var(--gray-500)', fontSize: '0.875rem' }}>
                No category data available for this range.
              </div>
            ) : (
              <div>
                {/* Visual percentage shares */}
                <div style={{ marginBottom: '20px' }}>
                  {sustainability.category_breakdown.map((cat) => {
                    const totalMass = sustainability.total_rescued_weight_kg || 1;
                    const pct = Math.min(100, (cat.rescued_kg / totalMass) * 100);
                    return (
                      <div key={cat.category_id} style={{ marginBottom: '10px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8125rem', marginBottom: '4px' }}>
                          <span style={{ fontWeight: 600 }}>{cat.category_name}</span>
                          <span style={{ color: 'var(--gray-500)' }}>
                            {cat.rescued_kg.toFixed(1)} kg ({pct.toFixed(0)}%)
                          </span>
                        </div>
                        <div style={{ height: '8px', background: 'var(--gray-100)', borderRadius: '4px', overflow: 'hidden' }}>
                          <div
                            style={{
                              width: `${pct}%`,
                              height: '100%',
                              background: 'var(--primary)',
                              borderRadius: '4px',
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>

                {/* Detailed Table */}
                <div className="table-container">
                  <table>
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th>Mass Rescued (kg)</th>
                        <th>Units</th>
                        <th>Avoided CO₂e (kg)</th>
                        <th>Meals Provided</th>
                        <th>Value Rescued ($)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sustainability.category_breakdown.map((cat) => (
                        <tr key={cat.category_id}>
                          <td style={{ fontWeight: 600 }}>{cat.category_name}</td>
                          <td>{cat.rescued_kg.toFixed(2)}</td>
                          <td>{cat.rescued_units}</td>
                          <td style={{ color: '#059669', fontWeight: 600 }}>{cat.co2e_avoided_kg.toFixed(2)}</td>
                          <td style={{ color: '#1d4ed8', fontWeight: 600 }}>{cat.meals_provided}</td>
                          <td style={{ fontWeight: 600 }}>${cat.value_rescued.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          {/* Environmental Standards Notice */}
          <div
            style={{
              marginTop: '16px',
              padding: '12px 16px',
              background: 'var(--gray-100)',
              borderRadius: '8px',
              fontSize: '0.75rem',
              color: 'var(--gray-600)',
            }}
          >
            <strong>Methodology & Environmental Standards:</strong> {sustainability.methodology_notes}
          </div>
        </div>
      )}
    </div>
  );
};
