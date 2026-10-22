import React, { useEffect, useState } from 'react';
import { api } from '../services/api';
import { CategorySummary, InventoryItem, InventoryItemCreatePayload } from '../types';

interface ItemFormModalProps {
  itemToEdit?: InventoryItem | null;
  onClose: () => void;
  onSuccess: (item: InventoryItem) => void;
}

export const ItemFormModal: React.FC<ItemFormModalProps> = ({
  itemToEdit,
  onClose,
  onSuccess,
}) => {
  const isEditing = Boolean(itemToEdit);

  const [categories, setCategories] = useState<CategorySummary[]>([]);
  const [name, setName] = useState<string>(itemToEdit?.name || '');
  const [categoryId, setCategoryId] = useState<string>(itemToEdit?.category_id || '');
  const [sku, setSku] = useState<string>(itemToEdit?.sku || '');
  const [barcode, setBarcode] = useState<string>(itemToEdit?.barcode || '');
  const [quantity, setQuantity] = useState<string>(itemToEdit ? String(itemToEdit.current_quantity) : '10');
  const [unit, setUnit] = useState<string>(itemToEdit?.unit || 'units');
  const [costPerUnit, setCostPerUnit] = useState<string>(itemToEdit ? String(itemToEdit.cost_per_unit) : '2.50');
  const [sellingPrice, setSellingPrice] = useState<string>(itemToEdit?.selling_price ? String(itemToEdit.selling_price) : '');
  
  const todayStr = new Date().toISOString().split('T')[0];
  const [purchaseDate, setPurchaseDate] = useState<string>(itemToEdit?.purchase_date || todayStr);
  const [expiryDate, setExpiryDate] = useState<string>(itemToEdit?.expiry_date || '');
  const [batchNumber, setBatchNumber] = useState<string>(itemToEdit?.batch_number || '');
  const [storageReq, setStorageReq] = useState<string>(itemToEdit?.storage_requirement || 'REFRIGERATED');
  const [storageLocation, setStorageLocation] = useState<string>(itemToEdit?.storage_location || '');

  const [submitting, setSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    api.getCategories().then((cats) => {
      setCategories(cats);
      if (!categoryId && cats.length > 0) {
        setCategoryId(cats[0].id);
        setStorageReq(cats[0].recommended_storage);
      }
    }).catch(() => {});
  }, []);

  // When category changes, auto-suggest recommended storage
  const handleCategoryChange = (newCatId: string) => {
    setCategoryId(newCatId);
    const cat = categories.find((c) => c.id === newCatId);
    if (cat) {
      setStorageReq(cat.recommended_storage);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);

    if (expiryDate && purchaseDate && expiryDate < purchaseDate) {
      setErrorMsg('Expiry date cannot precede purchase date');
      return;
    }

    setSubmitting(true);
    try {
      if (isEditing && itemToEdit) {
        const updated = await api.updateInventoryItem(itemToEdit.id, {
          name: name.trim(),
          category_id: categoryId,
          sku: sku.trim() || undefined,
          barcode: barcode.trim() || undefined,
          cost_per_unit: parseFloat(costPerUnit),
          selling_price: sellingPrice ? parseFloat(sellingPrice) : undefined,
          purchase_date: purchaseDate,
          expiry_date: expiryDate,
          batch_number: batchNumber.trim() || undefined,
          storage_requirement: storageReq,
          storage_location: storageLocation.trim() || undefined,
        });
        onSuccess(updated);
      } else {
        const payload: InventoryItemCreatePayload = {
          name: name.trim(),
          category_id: categoryId,
          sku: sku.trim() || undefined,
          barcode: barcode.trim() || undefined,
          initial_quantity: parseFloat(quantity),
          unit,
          cost_per_unit: parseFloat(costPerUnit),
          selling_price: sellingPrice ? parseFloat(sellingPrice) : undefined,
          purchase_date: purchaseDate,
          expiry_date: expiryDate,
          batch_number: batchNumber.trim() || undefined,
          storage_requirement: storageReq,
          storage_location: storageLocation.trim() || undefined,
        };
        const created = await api.createInventoryItem(payload);
        onSuccess(created);
      }
      onClose();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to save inventory item');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '16px' }}>
          {isEditing ? `Edit Item: ${itemToEdit?.name}` : 'Add New Inventory Item'}
        </h3>

        {errorMsg && (
          <div style={{ padding: '10px 14px', background: 'var(--danger-bg)', color: 'var(--danger)', borderRadius: '8px', marginBottom: '16px', fontSize: '0.8125rem' }}>
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            {/* Item Name */}
            <div className="form-group" style={{ gridColumn: 'span 2' }}>
              <label className="form-label">Item Name *</label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Organic Strawberries 250g"
                className="form-input"
              />
            </div>

            {/* Category */}
            <div className="form-group">
              <label className="form-label">Food Category *</label>
              <select
                required
                value={categoryId}
                onChange={(e) => handleCategoryChange(e.target.value)}
                className="form-select"
              >
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} ({c.perishability_tier})
                  </option>
                ))}
              </select>
            </div>

            {/* Storage Requirement */}
            <div className="form-group">
              <label className="form-label">Storage Requirement *</label>
              <select
                value={storageReq}
                onChange={(e) => setStorageReq(e.target.value)}
                className="form-select"
              >
                <option value="REFRIGERATED">Refrigerated (0-4°C)</option>
                <option value="FROZEN">Frozen (≤ -18°C)</option>
                <option value="AMBIENT">Ambient (18-22°C)</option>
                <option value="DRY_PANTRY">Dry Pantry</option>
                <option value="CLIMATE_CONTROLLED">Climate Controlled</option>
              </select>
            </div>

            {/* SKU */}
            <div className="form-group">
              <label className="form-label">SKU</label>
              <input
                type="text"
                value={sku}
                onChange={(e) => setSku(e.target.value)}
                placeholder="e.g. PRD-STR-250"
                className="form-input"
              />
            </div>

            {/* Barcode */}
            <div className="form-group">
              <label className="form-label">Barcode / UPC</label>
              <input
                type="text"
                value={barcode}
                onChange={(e) => setBarcode(e.target.value)}
                placeholder="e.g. 012345678912"
                className="form-input"
              />
            </div>

            {/* Initial Quantity (Only on create) */}
            {!isEditing && (
              <>
                <div className="form-group">
                  <label className="form-label">Initial Quantity *</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    min="0"
                    value={quantity}
                    onChange={(e) => setQuantity(e.target.value)}
                    className="form-input"
                  />
                </div>

                <div className="form-group">
                  <label className="form-label">Unit of Measure *</label>
                  <select value={unit} onChange={(e) => setUnit(e.target.value)} className="form-select">
                    <option value="units">units (each)</option>
                    <option value="kg">kg (kilograms)</option>
                    <option value="g">g (grams)</option>
                    <option value="liters">liters</option>
                    <option value="ml">ml (milliliters)</option>
                    <option value="boxes">boxes</option>
                    <option value="packs">packs</option>
                  </select>
                </div>
              </>
            )}

            {/* Cost Per Unit */}
            <div className="form-group">
              <label className="form-label">Cost per Unit ($) *</label>
              <input
                type="number"
                step="0.01"
                required
                min="0"
                value={costPerUnit}
                onChange={(e) => setCostPerUnit(e.target.value)}
                className="form-input"
              />
            </div>

            {/* Selling Price */}
            <div className="form-group">
              <label className="form-label">Selling Price ($)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={sellingPrice}
                onChange={(e) => setSellingPrice(e.target.value)}
                placeholder="Optional"
                className="form-input"
              />
            </div>

            {/* Purchase Date */}
            <div className="form-group">
              <label className="form-label">Purchase Date *</label>
              <input
                type="date"
                required
                value={purchaseDate}
                onChange={(e) => setPurchaseDate(e.target.value)}
                className="form-input"
              />
            </div>

            {/* Expiry Date */}
            <div className="form-group">
              <label className="form-label">Expiry Date *</label>
              <input
                type="date"
                required
                value={expiryDate}
                onChange={(e) => setExpiryDate(e.target.value)}
                className="form-input"
              />
            </div>

            {/* Batch / Lot */}
            <div className="form-group">
              <label className="form-label">Batch / Lot Number</label>
              <input
                type="text"
                value={batchNumber}
                onChange={(e) => setBatchNumber(e.target.value)}
                placeholder="e.g. LOT-2026-OCT-1"
                className="form-input"
              />
            </div>

            {/* Storage Location */}
            <div className="form-group">
              <label className="form-label">Storage Location</label>
              <input
                type="text"
                value={storageLocation}
                onChange={(e) => setStorageLocation(e.target.value)}
                placeholder="e.g. Walk-in Cooler Shelf 2"
                className="form-input"
              />
            </div>
          </div>

          {/* Action buttons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
            <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? 'Saving...' : isEditing ? 'Update Item' : 'Create Inventory Item'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
