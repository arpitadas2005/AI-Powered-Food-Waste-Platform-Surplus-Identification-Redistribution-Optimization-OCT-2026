import React, { useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  ShieldCheck,
  Upload,
} from 'lucide-react';
import { api } from '../services/api';
import { CsvImportResponse } from '../types';

export const CsvImportView: React.FC = () => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dryRun, setDryRun] = useState<boolean>(true);
  const [allowPartial, setAllowPartial] = useState<boolean>(false);

  const [uploading, setUploading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<CsvImportResponse | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFile(e.target.files[0]);
      setImportResult(null);
      setErrorMsg(null);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setErrorMsg('Please select a CSV file first.');
      return;
    }

    setUploading(true);
    setErrorMsg(null);

    try {
      const res = await api.uploadCsv(selectedFile, dryRun, allowPartial);
      setImportResult(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'CSV Ingestion failed');
      setImportResult(null);
    } finally {
      setUploading(false);
    }
  };

  const downloadTemplate = () => {
    window.open('/api/v1/inventory/bulk-import/template', '_blank');
  };

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-900)' }}>CSV Bulk Inventory Ingestion</h2>
          <p style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
            High-throughput inventory batch import with multi-stage data quality validation and CWE-1236 injection defense.
          </p>
        </div>
        <button className="btn btn-secondary" onClick={downloadTemplate}>
          <Download size={16} /> Download CSV Template
        </button>
      </div>

      {/* Upload & Configuration Card */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <form onSubmit={handleUpload}>
          <div style={{ border: '2px dashed var(--border)', borderRadius: '12px', padding: '32px', textAlign: 'center', background: 'var(--gray-50)', marginBottom: '16px' }}>
            <FileSpreadsheet size={40} color="var(--primary)" style={{ margin: '0 auto 12px' }} />
            <p style={{ fontWeight: 600, color: 'var(--gray-800)', marginBottom: '4px' }}>
              {selectedFile ? selectedFile.name : 'Select or drop inventory CSV file'}
            </p>
            <p style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginBottom: '16px' }}>
              RFC 4180 format • Max 10MB • Max 10,000 rows • UTF-8 / Latin-1 encoding
            </p>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={handleFileChange}
              id="csvFileInput"
              style={{ display: 'none' }}
            />
            <label htmlFor="csvFileInput" className="btn btn-primary" style={{ cursor: 'pointer' }}>
              <Upload size={16} /> Browse Files
            </label>
          </div>

          {/* Import Policy Options */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', background: 'white', padding: '12px 16px', border: '1px solid var(--border)', borderRadius: '8px', marginBottom: '16px' }}>
            <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={dryRun}
                onChange={(e) => setDryRun(e.target.checked)}
                style={{ marginTop: '3px' }}
              />
              <div>
                <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>Dry Run Preview</span>
                <p style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                  Inspect validation errors without committing changes to the database.
                </p>
              </div>
            </label>

            <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={allowPartial}
                onChange={(e) => setAllowPartial(e.target.checked)}
                style={{ marginTop: '3px' }}
              />
              <div>
                <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>Permissive Partial Import</span>
                <p style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                  Insert valid records and log row errors, instead of strict atomic rollback.
                </p>
              </div>
            </label>
          </div>

          {/* Security Note */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', color: 'var(--gray-500)', marginBottom: '16px' }}>
            <ShieldCheck size={16} color="var(--success)" />
            <span>CWE-1236 Formula Injection Sanitization active for all imported strings and error reports.</span>
          </div>

          {/* Submit */}
          <button
            type="submit"
            disabled={!selectedFile || uploading}
            className="btn btn-primary"
            style={{ width: '100%', padding: '10px' }}
          >
            {uploading ? 'Processing Ingestion Pipeline...' : dryRun ? 'Execute Dry-Run Preview' : 'Commit CSV Records to Database'}
          </button>
        </form>
      </div>

      {/* Error alert */}
      {errorMsg && (
        <div style={{ padding: '12px', background: 'var(--danger-bg)', color: 'var(--danger)', borderRadius: '8px', marginBottom: '20px' }}>
          <strong>Import Error:</strong> {errorMsg}
        </div>
      )}

      {/* Ingestion Results Card */}
      {importResult && (
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ fontSize: '1.125rem', fontWeight: 700 }}>
              Ingestion Results: <span style={{ color: 'var(--primary)' }}>{importResult.filename}</span>
            </h3>
            <span
              className={`badge ${
                importResult.status === 'COMPLETED'
                  ? 'badge-fresh'
                  : importResult.status === 'COMPLETED (Dry Run)'
                  ? 'badge-notice'
                  : 'badge-critical'
              }`}
            >
              {importResult.status}
            </span>
          </div>

          {/* Counters Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '10px', marginBottom: '20px' }}>
            <div style={{ background: 'var(--gray-50)', padding: '12px', borderRadius: '8px', textAlign: 'center' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--gray-500)', textTransform: 'uppercase' }}>Total Rows</span>
              <div style={{ fontSize: '1.25rem', fontWeight: 700 }}>{importResult.summary.total_rows}</div>
            </div>

            <div style={{ background: '#f0fdf4', padding: '12px', borderRadius: '8px', textAlign: 'center' }}>
              <span style={{ fontSize: '0.75rem', color: '#166534', textTransform: 'uppercase' }}>Accepted</span>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#166534' }}>
                {importResult.summary.accepted_rows}
              </div>
            </div>

            <div style={{ background: '#fef2f2', padding: '12px', borderRadius: '8px', textAlign: 'center' }}>
              <span style={{ fontSize: '0.75rem', color: '#991b1b', textTransform: 'uppercase' }}>Rejected</span>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#991b1b' }}>
                {importResult.summary.rejected_rows}
              </div>
            </div>

            <div style={{ background: '#fffbeb', padding: '12px', borderRadius: '8px', textAlign: 'center' }}>
              <span style={{ fontSize: '0.75rem', color: '#92400e', textTransform: 'uppercase' }}>Duplicates</span>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#92400e' }}>
                {importResult.summary.duplicate_rows}
              </div>
            </div>
          </div>

          {/* Row Errors Table */}
          {importResult.errors && importResult.errors.length > 0 ? (
            <div>
              <h4 style={{ fontSize: '0.875rem', fontWeight: 700, marginBottom: '8px', color: 'var(--danger)' }}>
                Row Validation Errors ({importResult.errors.length})
              </h4>
              <div className="table-container" style={{ maxHeight: '300px', overflowY: 'auto' }}>
                <table>
                  <thead>
                    <tr>
                      <th>Line #</th>
                      <th>Field</th>
                      <th>Invalid Value</th>
                      <th>Error Code</th>
                      <th>Diagnostic Message</th>
                    </tr>
                  </thead>
                  <tbody>
                    {importResult.errors.map((err, idx) => (
                      <tr key={idx}>
                        <td style={{ fontWeight: 700 }}>{err.row_number}</td>
                        <td style={{ fontFamily: 'monospace', fontSize: '0.8125rem' }}>{err.field_name || '—'}</td>
                        <td style={{ color: 'var(--danger)', fontSize: '0.8125rem' }}>{err.invalid_value || 'None'}</td>
                        <td>
                          <span className="badge badge-warning">{err.error_code}</span>
                        </td>
                        <td style={{ fontSize: '0.8125rem' }}>{err.error_message}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--success)', padding: '12px', background: 'var(--success-bg)', borderRadius: '8px' }}>
              <CheckCircle2 size={18} />
              <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>All rows passed validation with zero errors.</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
