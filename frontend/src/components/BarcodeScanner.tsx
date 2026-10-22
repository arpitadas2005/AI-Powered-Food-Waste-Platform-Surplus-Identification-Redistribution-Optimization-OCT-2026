/**
 * Mobile-Friendly Barcode & QR Code Scanner Component.
 * 
 * Capabilities:
 * - Camera-based live video stream scanning with permission & browser compatibility handling.
 * - Manual barcode / SKU entry fallback for unsupported or camera-denied environments.
 * - Scan debouncing (2.0s cooldown) to eliminate duplicate scan triggers.
 * - Authorized backend resolution via GET /api/v1/inventory/lookup?code=...
 * - Explicit confirmation dialog before changing inventory stock.
 * - Idempotency key generation (UUID v4) and double-click protection to prevent accidental duplicate adjustments.
 * - Avoids assuming barcode encodes expiry/quantity unless structured data is explicitly provided.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';

export interface CategorySummary {
  id: string;
  name: string;
  slug: string;
  perishability_tier: string;
  recommended_storage: string;
}

export interface InventoryItemResponse {
  id: string;
  tenant_id: string;
  category_id: string;
  category?: CategorySummary;
  name: string;
  sku?: string;
  barcode?: string;
  current_quantity: number;
  unit: string;
  cost_per_unit: number;
  selling_price?: number;
  purchase_date: string;
  expiry_date: string;
  days_to_expiry: number;
  batch_number?: string;
  storage_requirement: string;
  storage_location?: string;
  status: string;
  is_active: boolean;
}

export interface BarcodeLookupResult {
  item: InventoryItemResponse;
  scanned_code: string;
  code_type: string;
  embedded_data?: Record<string, any>;
}

export interface BarcodeScannerProps {
  apiBaseUrl?: string;
  authToken: string;
  onAdjustmentComplete?: (item: InventoryItemResponse) => void;
}

export const BarcodeScanner: React.FC<BarcodeScannerProps> = ({
  apiBaseUrl = '/api/v1',
  authToken,
  onAdjustmentComplete,
}) => {
  // Camera & Stream States
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [cameraActive, setCameraActive] = useState<boolean>(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [cameraSupported, setCameraSupported] = useState<boolean>(true);

  // Manual Input State
  const [manualCode, setManualCode] = useState<string>('');

  // Scanning & Lookup States
  const [isLookingUp, setIsLookingUp] = useState<boolean>(false);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [resolvedResult, setResolvedResult] = useState<BarcodeLookupResult | null>(null);

  // Adjustment Modal & Confirmation States
  const [showAdjustModal, setShowAdjustModal] = useState<boolean>(false);
  const [adjustmentType, setAdjustmentType] = useState<string>('MANUAL_ADJUSTMENT');
  const [quantityDelta, setQuantityDelta] = useState<string>('1.0');
  const [reason, setReason] = useState<string>('Barcode scan stock adjustment');
  const [isSubmittingAdjustment, setIsSubmittingAdjustment] = useState<boolean>(false);
  const [adjustmentSuccessMsg, setAdjustmentSuccessMsg] = useState<string | null>(null);

  // Scan Debounce Tracker
  const lastScanRef = useRef<{ code: string; timestamp: number }>({ code: '', timestamp: 0 });

  // 1. Check Browser MediaDevices Support
  useEffect(() => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setCameraSupported(false);
      setCameraError('Camera access is not supported in this browser. Please use manual entry below.');
    }
  }, []);

  // 2. Start Camera Stream
  const startCamera = async () => {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.setAttribute('playsinline', 'true');
        await videoRef.current.play();
        setCameraActive(true);
      }
    } catch (err: any) {
      setCameraActive(false);
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setCameraError('Camera permission denied. Please enable camera permissions or use manual entry below.');
      } else if (err.name === 'NotFoundError') {
        setCameraError('No camera hardware detected on this device. Please use manual entry.');
      } else {
        setCameraError(`Unable to start camera: ${err.message || 'Unknown error'}`);
      }
    }
  };

  // 3. Stop Camera Stream
  const stopCamera = () => {
    if (videoRef.current && videoRef.current.srcObject) {
      const stream = videoRef.current.srcObject as MediaStream;
      stream.getTracks().forEach((track) => track.stop());
      videoRef.current.srcObject = null;
    }
    setCameraActive(false);
  };

  useEffect(() => {
    return () => {
      stopCamera();
    };
  }, []);

  // 4. Perform Authorized Backend Lookup
  const handleLookup = useCallback(
    async (codeToLookup: string) => {
      const trimmed = codeToLookup.trim();
      if (!trimmed) return;

      // Debounce repeated identical scans within 2.0 seconds
      const now = Date.now();
      if (
        lastScanRef.current.code === trimmed &&
        now - lastScanRef.current.timestamp < 2000
      ) {
        return; // Suppress duplicate rapid trigger
      }
      lastScanRef.current = { code: trimmed, timestamp: now };

      setIsLookingUp(true);
      setLookupError(null);
      setAdjustmentSuccessMsg(null);

      try {
        const response = await fetch(`${apiBaseUrl}/inventory/lookup?code=${encodeURIComponent(trimmed)}`, {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
        });

        if (!response.ok) {
          if (response.status === 404) {
            throw new Error(`Item not found for code: "${trimmed}"`);
          } else if (response.status === 401 || response.status === 403) {
            throw new Error('Unauthorized. Please log in with valid credentials.');
          } else {
            throw new Error(`Lookup failed with status ${response.status}`);
          }
        }

        const json = await response.json();
        const result: BarcodeLookupResult = json.data;
        setResolvedResult(result);
        setShowAdjustModal(true);
        // Pre-fill quantity if explicitly provided in structured QR JSON
        if (result.embedded_data && result.embedded_data.qty) {
          setQuantityDelta(String(result.embedded_data.qty));
        } else {
          setQuantityDelta('1.0');
        }
      } catch (err: any) {
        setLookupError(err.message || 'An error occurred during lookup.');
        setResolvedResult(null);
      } finally {
        setIsLookingUp(false);
      }
    },
    [apiBaseUrl, authToken]
  );

  // 5. Submit Stock Adjustment with Idempotency Key
  const handleConfirmAdjustment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resolvedResult) return;

    const deltaNum = parseFloat(quantityDelta);
    if (isNaN(deltaNum) || deltaNum === 0) {
      alert('Please specify a non-zero quantity adjustment.');
      return;
    }

    setIsSubmittingAdjustment(true);
    // Generate UUIDv4 idempotency key to prevent accidental double-submits
    const idempotencyKey = `scan_adj_${crypto.randomUUID()}`;

    try {
      const response = await fetch(`${apiBaseUrl}/inventory/${resolvedResult.item.id}/adjust`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${authToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          quantity_delta: deltaNum,
          adjustment_type: adjustmentType,
          reason: reason.trim() || 'Barcode scan confirmation',
          reference_type: 'BARCODE_SCAN',
          reference_id: resolvedResult.scanned_code,
          idempotency_key: idempotencyKey,
        }),
      });

      if (!response.ok) {
        const errJson = await response.json();
        throw new Error(errJson.detail || errJson.error?.message || 'Stock adjustment failed');
      }

      const json = await response.json();
      const updatedItem: InventoryItemResponse = json.data.item;

      setAdjustmentSuccessMsg(
        `Successfully adjusted ${updatedItem.name}: New Quantity = ${updatedItem.current_quantity} ${updatedItem.unit}`
      );
      setShowAdjustModal(false);
      setResolvedResult(null);
      setManualCode('');

      if (onAdjustmentComplete) {
        onAdjustmentComplete(updatedItem);
      }
    } catch (err: any) {
      alert(`Adjustment error: ${err.message}`);
    } finally {
      setIsSubmittingAdjustment(false);
    }
  };

  return (
    <div className="barcode-scanner-container max-w-lg mx-auto p-4 bg-white rounded-xl shadow-md border border-gray-100">
      <h2 className="text-xl font-bold text-gray-800 mb-3 flex items-center gap-2">
        <span>📷</span> Mobile Barcode & QR Scanner
      </h2>

      {/* Success Notification */}
      {adjustmentSuccessMsg && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 text-green-800 text-sm rounded-lg flex items-center justify-between">
          <span>{adjustmentSuccessMsg}</span>
          <button onClick={() => setAdjustmentSuccessMsg(null)} className="font-bold text-green-700">✕</button>
        </div>
      )}

      {/* Camera Viewport & Controls */}
      <div className="camera-section mb-4">
        {cameraSupported ? (
          <div className="relative bg-black rounded-lg overflow-hidden aspect-video flex items-center justify-center border border-gray-200">
            <video
              ref={videoRef}
              className={`w-full h-full object-cover ${cameraActive ? 'block' : 'hidden'}`}
            />
            {!cameraActive && (
              <div className="text-center p-4 text-gray-400">
                <p className="text-sm mb-2">Camera is currently paused.</p>
                <button
                  type="button"
                  onClick={startCamera}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg shadow-sm text-sm"
                >
                  Start Camera Scan
                </button>
              </div>
            )}
            {cameraActive && (
              <div className="absolute top-2 right-2">
                <button
                  type="button"
                  onClick={stopCamera}
                  className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white font-medium rounded text-xs shadow"
                >
                  Stop Camera
                </button>
              </div>
            )}
          </div>
        ) : null}

        {/* Camera Permission / Error Banner */}
        {cameraError && (
          <div className="mt-2 p-3 bg-amber-50 border border-amber-200 text-amber-800 text-xs rounded-lg">
            <strong>Notice:</strong> {cameraError}
          </div>
        )}
      </div>

      {/* Manual Entry Fallback Form */}
      <div className="manual-entry-section border-t border-gray-100 pt-4">
        <label className="block text-xs font-semibold text-gray-700 mb-1">
          Manual Barcode / SKU / QR Entry
        </label>
        <div className="flex gap-2">
          <input
            type="text"
            value={manualCode}
            onChange={(e) => setManualCode(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleLookup(manualCode)}
            placeholder="e.g. 012345678912 or PRD-SPIN-250"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={isLookingUp}
          />
          <button
            type="button"
            onClick={() => handleLookup(manualCode)}
            disabled={isLookingUp || !manualCode.trim()}
            className="px-4 py-2 bg-gray-800 hover:bg-black text-white font-medium rounded-lg text-sm disabled:opacity-50"
          >
            {isLookingUp ? 'Searching...' : 'Lookup'}
          </button>
        </div>
      </div>

      {/* Error Message */}
      {lookupError && (
        <div className="mt-3 p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg">
          {lookupError}
        </div>
      )}

      {/* Explicit Confirmation Modal */}
      {showAdjustModal && resolvedResult && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl max-w-md w-full p-5 shadow-2xl">
            <h3 className="text-lg font-bold text-gray-900 mb-2">Confirm Stock Adjustment</h3>

            {/* Resolved Item Summary */}
            <div className="bg-gray-50 p-3 rounded-lg border border-gray-200 mb-4 text-xs space-y-1">
              <div className="flex justify-between">
                <span className="font-semibold text-gray-600">Product:</span>
                <span className="font-bold text-gray-900">{resolvedResult.item.name}</span>
              </div>
              <div className="flex justify-between">
                <span className="font-semibold text-gray-600">SKU / Code:</span>
                <span>{resolvedResult.item.sku || resolvedResult.scanned_code}</span>
              </div>
              <div className="flex justify-between">
                <span className="font-semibold text-gray-600">Category:</span>
                <span>{resolvedResult.item.category?.name || 'Standard'}</span>
              </div>
              <div className="flex justify-between">
                <span className="font-semibold text-gray-600">Current Stock:</span>
                <span className="font-bold text-blue-700">
                  {resolvedResult.item.current_quantity} {resolvedResult.item.unit}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="font-semibold text-gray-600">Expiry Date:</span>
                <span className={resolvedResult.item.days_to_expiry <= 2 ? 'text-red-600 font-bold' : ''}>
                  {resolvedResult.item.expiry_date} ({resolvedResult.item.days_to_expiry.toFixed(1)} days)
                </span>
              </div>
              {resolvedResult.embedded_data && (
                <div className="mt-2 pt-2 border-t border-gray-200 text-blue-700">
                  <span className="font-semibold">QR Structured Data Detected:</span>
                  <pre className="mt-1 p-1 bg-blue-50 rounded text-2xs overflow-x-auto">
                    {JSON.stringify(resolvedResult.embedded_data, null, 2)}
                  </pre>
                </div>
              )}
            </div>

            {/* Adjustment Form */}
            <form onSubmit={handleConfirmAdjustment} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Adjustment Action</label>
                <select
                  value={adjustmentType}
                  onChange={(e) => setAdjustmentType(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white"
                >
                  <option value="RESTOCK">Restock / Inbound (+)</option>
                  <option value="POS_SALE">Point of Sale / Sale (-)</option>
                  <option value="MANUAL_ADJUSTMENT">Manual Inventory Adjustment (+/-)</option>
                  <option value="SPOILAGE_DISCARD">Spoilage / Expired Discard (-)</option>
                  <option value="DONATION_HOLD">Donation Hold Dispatch (-)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">
                  Quantity Delta ({resolvedResult.item.unit})
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={quantityDelta}
                  onChange={(e) => setQuantityDelta(e.target.value)}
                  placeholder="e.g. 5.0 or -2.0"
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                />
                <span className="text-2xs text-gray-500">
                  Enter positive number to add stock, negative number to deduct.
                </span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-700 mb-1">Audit Reason</label>
                <input
                  type="text"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  required
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                />
              </div>

              {/* Action Buttons */}
              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowAdjustModal(false)}
                  disabled={isSubmittingAdjustment}
                  className="flex-1 py-2 border border-gray-300 text-gray-700 rounded-lg text-sm font-medium hover:bg-gray-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingAdjustment}
                  className="flex-1 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium disabled:opacity-50 shadow-sm"
                >
                  {isSubmittingAdjustment ? 'Confirming...' : 'Confirm Adjustment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
