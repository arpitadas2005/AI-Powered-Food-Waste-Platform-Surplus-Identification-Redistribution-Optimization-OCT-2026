import React, { useEffect, useState } from 'react';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Boxes,
  CheckCircle2,
  Clock,
  History,
  RefreshCw,
  X,
} from 'lucide-react';
import { api } from '../services/api';
import { InventoryItem, StockAdjustmentPayload, StockTransaction } from '../types';

interface ItemDetailsModalProps {
  item: InventoryItem;
  onClose: () => void;
  onItemUpdated: (updatedItem: InventoryItem) => void;
}

export const ItemDetailsModal: React.FC<ItemDetailsModalProps> = ({
  item: initialItem,
  onClose,
  onItemUpdated,
}) => {
  const [item, setItem] = useState<InventoryItem>(initialItem);
  const [transactions, setTransactions] = useState<StockTransaction[]>([]);
  const [loadingTransactions, setLoadingTransactions] = useState<boolean>(true);

  // Adjustment Form States
  const [quantityDelta, setQuantityDelta] = useState<string>('5.0');
  const [adjustmentType, setAdjustmentType] = useState<string>('RESTOCK');
  const [reason, setReason] = useState<string>('Stock verification delivery');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [adjustError, setAdjustError] = useState<string | null>(null);
  const [adjustSuccess, setAdjustSuccess] = useState<string | null>(null);

  const loadTransactions = async () => {
    setLoadingTransactions(true);
    try {
      const txs = await api.getItemTransactions(item.id);
      setTransactions(txs);
    } catch {
      // Failed to load transactions
    } finally {
      setLoadingTransactions(false);
    }
  };

  useEffect(() => {
    loadTransactions();
  }, [item.id]);

  const handleStockAdjustment = async (e: React.FormEvent) => {
    e.preventDefault();
    setAdjustError(null);
    setAdjustSuccess(null);

    const delta = parseFloat(quantityDelta);
    if (isNaN(delta) || delta === 0) {
      setAdjustError('Quantity delta must be non-zero');
      return;
    }

    setIsSubmitting(true);
    // Generate UUIDv4 idempotency key
    const idempotencyKey = `idemp_modal_${crypto.randomUUID()}`;

    try {
      const payload: StockAdjustmentPayload = {
        quantity_delta: delta,
        adjustment_type: adjustmentType,
        reason: reason.trim(),
        reference_type: 'MANUAL_MODAL_ADJUST',
        reference_id: idempotencyKey,
        idempotency_key: idempotencyKey,
      };

      const result = await api.adjustStock(item.id, payload);
      setItem(result.item);
      onItemUpdated(result.item);
      setAdjustSuccess(`Adjusted stock by ${delta > 0 ? '+' : ''}${delta} ${item.unit}. New balance: ${result.item.current_quantity}`);
      setQuantityDelta('1.0');
      loadTransactions();
    } catch (err: any) {
      setAdjustError(err.message || 'Stock adjustment failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content" style={{ maxWidth: '750px' }}>
        {/* Modal Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--gray-900)' }}>{item.name}</h3>
              <span className={`badge ${item.days_to_expiry <= 2 ? 'badge-critical' : 'badge-fresh'}`}>
                {item.status}
              </span>
            </div>
            <p style={{ fontSize: '0.8125rem', color: 'var(--gray-500)' }}>
              Category: {item.category?.name || 'Uncategorized'} • Storage: {item.storage_requirement}
            </p>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--gray-500)' }}>
            <X size={20} />
          </button>
        </div>

        {/* Item Specifications Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '10px', background: 'var(--gray-50)', padding: '14px', borderRadius: '10px', border: '1px solid var(--border)', marginBottom: '20px' }}>
          <div>
            <span style={{ fontSize: '0.6875rem', fontWeight: 600, color: 'var(--gray-500)', textTransform: 'uppercase' }}>Current Stock</span>
            <div style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--primary)' }}>
              {item.current_quantity} {item.unit}
            </div>
          </div>

          <div>
            <span style={{ fontSize: '0.6875rem', fontWeight: 600, color: 'var(--gray-500)', textTransform: 'uppercase' }}>SKU / Barcode</span>
            <div style={{ fontSize: '0.8125rem', fontWeight: 600 }}>{item.sku || 'N/A'}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>{item.barcode || 'No barcode'}</div>
          </div>

          <div>
            <span style={{ fontSize: '0.6875rem', fontWeight: 600, color: 'var(--gray-500)', textTransform: 'uppercase' }}>Expiry Horizon</span>
            <div style={{ fontSize: '0.8125rem', fontWeight: 700, color: item.days_to_expiry <= 2 ? 'var(--danger)' : 'var(--gray-900)' }}>
              {item.expiry_date}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>{item.days_to_expiry.toFixed(1)} days remaining</div>
          </div>

          <div>
            <span style={{ fontSize: '0.6875rem', fontWeight: 600, color: 'var(--gray-500)', textTransform: 'uppercase' }}>Storage Location</span>
            <div style={{ fontSize: '0.8125rem' }}>{item.storage_location || 'General'}</div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Batch: {item.batch_number || 'None'}</div>
          </div>
        </div>

        {/* Stock Adjustment Section */}
        <div style={{ border: '1px solid var(--border)', borderRadius: '10px', padding: '16px', marginBottom: '24px' }}>
          <h4 style={{ fontSize: '0.875rem', fontWeight: 700, marginBottom: '8px' }}>Adjust Physical Stock (Immutable Ledger)</h4>
          
          {adjustError && (
            <div style={{ padding: '8px 12px', background: 'var(--danger-bg)', color: 'var(--danger)', borderRadius: '6px', fontSize: '0.75rem', marginBottom: '10px' }}>
              {adjustError}
            </div>
          )}

          {adjustSuccess && (
            <div style={{ padding: '8px 12px', background: 'var(--success-bg)', color: 'var(--success)', borderRadius: '6px', fontSize: '0.75rem', marginBottom: '10px' }}>
              {adjustSuccess}
            </div>
          )}

          <form onSubmit={handleStockAdjustment} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '8px', alignItems: 'flex-end' }}>
            <div>
              <label className="form-label">Action</label>
              <select value={adjustmentType} onChange={(e) => setAdjustmentType(e.target.value)} className="form-select">
                <option value="RESTOCK">Restock (+)</option>
                <option value="POS_SALE">Point of Sale (-)</option>
                <option value="MANUAL_ADJUSTMENT">Manual (+/-)</option>
                <option value="SPOILAGE_DISCARD">Spoilage / Expired (-)</option>
                <option value="DONATION_HOLD">Donation Hold (-)</option>
              </select>
            </div>

            <div>
              <label className="form-label">Delta ({item.unit})</label>
              <input
                type="number"
                step="0.01"
                required
                value={quantityDelta}
                onChange={(e) => setQuantityDelta(e.target.value)}
                className="form-input"
              />
            </div>

            <div style={{ gridColumn: 'span 2' }}>
              <label className="form-label">Audit Reason</label>
              <input
                type="text"
                required
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                className="form-input"
              />
            </div>

            <div>
              <button type="submit" disabled={isSubmitting} className="btn btn-primary" style={{ width: '100%' }}>
                {isSubmitting ? 'Adjusting...' : 'Commit Adjustment'}
              </button>
            </div>
          </form>
        </div>

        {/* Transaction History Ledger */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <h4 style={{ fontSize: '0.875rem', fontWeight: 700 }}>Double-Entry Transaction History ({transactions.length})</h4>
            <button onClick={loadTransactions} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--primary)', fontSize: '0.75rem' }}>
              Refresh History
            </button>
          </div>

          <div className="table-container" style={{ maxHeight: '220px', overflowY: 'auto' }}>
            {loadingTransactions ? (
              <div style={{ textAlign: 'center', padding: '20px', color: 'var(--gray-500)', fontSize: '0.8125rem' }}>
                Loading ledger entries...
              </div>
            ) : transactions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '20px', color: 'var(--gray-500)', fontSize: '0.8125rem' }}>
                No transaction records found for this item.
              </div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Timestamp</th>
                    <th>Type</th>
                    <th>Delta</th>
                    <th>Balance</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map((tx) => (
                    <tr key={tx.id}>
                      <td style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        {new Date(tx.created_at).toLocaleString()}
                      </td>
                      <td>
                        <span className="badge badge-notice" style={{ fontSize: '0.6875rem' }}>{tx.transaction_type}</span>
                      </td>
                      <td style={{ fontWeight: 700, fontSize: '0.8125rem', color: tx.quantity_change >= 0 ? 'var(--success)' : 'var(--danger)' }}>
                        {tx.quantity_change > 0 ? `+${tx.quantity_change}` : tx.quantity_change}
                      </td>
                      <td style={{ fontSize: '0.75rem' }}>
                        {tx.quantity_before} $\rightarrow$ <strong>{tx.quantity_after}</strong>
                      </td>
                      <td style={{ fontSize: '0.75rem', color: 'var(--gray-700)' }}>
                        {tx.reason || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
