'use client';

import React, { useState, useRef } from 'react';
import {
  UploadCloud,
  FileText,
  CheckCircle,
  AlertTriangle,
  XCircle,
  ArrowRight,
  Download,
  X,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { CSVPreviewResponse, CSVCommitResponse } from '@/types';
import { downloadCSVTemplate, uploadCSVPreview, commitCSVImport } from '@/services/api';

interface CSVImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportComplete: () => void;
}

export const CSVImportModal: React.FC<CSVImportModalProps> = ({
  isOpen,
  onClose,
  onImportComplete,
}) => {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isCommitting, setIsCommitting] = useState(false);
  const [preview, setPreview] = useState<CSVPreviewResponse | null>(null);
  const [commitResult, setCommitResult] = useState<CSVCommitResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const handleDownloadTemplate = async () => {
    try {
      const blob = await downloadCSVTemplate();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'profitguard_order_template.csv';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to download template');
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setErrorMsg(null);
    }
  };

  const handleUploadPreview = async () => {
    if (!file) return;
    setIsUploading(true);
    setErrorMsg(null);
    try {
      const res = await uploadCSVPreview(file);
      setPreview(res);
    } catch (err: any) {
      setErrorMsg(err.message || 'Validation failed. Please inspect CSV format.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleCommit = async () => {
    if (!preview) return;
    setIsCommitting(true);
    setErrorMsg(null);
    try {
      const res = await commitCSVImport(preview.preview_id);
      setCommitResult(res);
      onImportComplete();
    } catch (err: any) {
      setErrorMsg(err.message || 'Commit transaction failed.');
    } finally {
      setIsCommitting(false);
    }
  };

  const resetState = () => {
    setFile(null);
    setPreview(null);
    setCommitResult(null);
    setErrorMsg(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="relative flex max-h-[90vh] w-full max-w-4xl flex-col rounded-xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div className="flex items-center space-x-3">
            <div className="rounded-lg bg-emerald-50 p-2 text-emerald-600">
              <UploadCloud className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900">Two-Stage CSV Order Ingestion</h2>
              <p className="text-sm text-slate-500">
                Stage A Preview & Validate → Stage B Transactional Commit
              </p>
            </div>
          </div>
          <button
            onClick={() => {
              resetState();
              onClose();
            }}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto px-6 py-6">
          {errorMsg && (
            <div className="mb-6 flex items-start space-x-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
              <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" />
              <div className="text-sm font-medium">{errorMsg}</div>
            </div>
          )}

          {/* Stage A: Upload State */}
          {!preview && !commitResult && (
            <div className="space-y-6">
              <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center space-x-3">
                  <FileText className="h-5 w-5 text-slate-600" />
                  <span className="text-sm font-medium text-slate-700">
                    Use our standard RFC 4180 template with required headers
                  </span>
                </div>
                <button
                  type="button"
                  onClick={handleDownloadTemplate}
                  className="flex items-center space-x-2 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                >
                  <Download className="h-3.5 w-3.5" />
                  <span>Download Sample CSV</span>
                </button>
              </div>

              {/* Drag & Drop Area */}
              <div
                onClick={() => fileInputRef.current?.click()}
                className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50/50 p-10 text-center transition hover:border-emerald-500 hover:bg-emerald-50/20"
              >
                <UploadCloud className="mb-4 h-12 w-12 text-slate-400" />
                <h3 className="text-base font-semibold text-slate-800">
                  {file ? file.name : 'Click to select CSV export or drag and drop'}
                </h3>
                <p className="mt-1 text-xs text-slate-500">
                  Supports UTF-8 and UTF-8 with BOM up to 10 MB and 5,000 rows
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv"
                  onChange={handleFileChange}
                  className="hidden"
                />
              </div>

              {file && (
                <div className="flex justify-end">
                  <button
                    type="button"
                    disabled={isUploading}
                    onClick={handleUploadPreview}
                    className="flex items-center space-x-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow hover:bg-emerald-700 disabled:opacity-50"
                  >
                    {isUploading ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        <span>Validating Stage A...</span>
                      </>
                    ) : (
                      <>
                        <span>Validate & Preview</span>
                        <ArrowRight className="h-4 w-4" />
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Stage A: Preview Results */}
          {preview && !commitResult && (
            <div className="space-y-6">
              {/* Summary Badges */}
              <div className="grid grid-cols-4 gap-4">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="text-xs font-semibold uppercase text-slate-500">Total Rows</div>
                  <div className="mt-1 text-2xl font-bold text-slate-800">{preview.total_rows}</div>
                </div>
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                  <div className="text-xs font-semibold uppercase text-emerald-600">Valid Rows</div>
                  <div className="mt-1 text-2xl font-bold text-emerald-700">{preview.valid_rows}</div>
                </div>
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                  <div className="text-xs font-semibold uppercase text-amber-600">Duplicates</div>
                  <div className="mt-1 text-2xl font-bold text-amber-700">{preview.duplicate_rows}</div>
                </div>
                <div className="rounded-lg border border-red-200 bg-red-50 p-4">
                  <div className="text-xs font-semibold uppercase text-red-600">Errors</div>
                  <div className="mt-1 text-2xl font-bold text-red-700">{preview.invalid_rows}</div>
                </div>
              </div>

              {/* Sample Valid Rows Table */}
              {preview.sample_valid_rows.length > 0 && (
                <div>
                  <h4 className="mb-2 text-sm font-semibold text-slate-800">
                    Sample Valid Rows Preview ({preview.sample_valid_rows.length} shown)
                  </h4>
                  <div className="overflow-x-auto rounded-lg border border-slate-200">
                    <table className="w-full text-left text-xs">
                      <thead className="border-b bg-slate-50 font-medium text-slate-600">
                        <tr>
                          <th className="px-3 py-2">External ID</th>
                          <th className="px-3 py-2">Amount (₹)</th>
                          <th className="px-3 py-2">Method</th>
                          <th className="px-3 py-2">Customer</th>
                          <th className="px-3 py-2">Phone</th>
                          <th className="px-3 py-2">City</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100 font-mono">
                        {preview.sample_valid_rows.map((row, idx) => (
                          <tr key={idx} className="hover:bg-slate-50/50">
                            <td className="px-3 py-2 font-semibold text-slate-900">{row.external_order_id}</td>
                            <td className="px-3 py-2 text-slate-700">₹{row.order_value}</td>
                            <td className="px-3 py-2">
                              <span
                                className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                  row.payment_method === 'COD'
                                    ? 'bg-amber-100 text-amber-800'
                                    : 'bg-emerald-100 text-emerald-800'
                                }`}
                              >
                                {row.payment_method}
                              </span>
                            </td>
                            <td className="px-3 py-2 font-sans text-slate-700">{row.customer_name || '—'}</td>
                            <td className="px-3 py-2 text-slate-600">{row.customer_phone || '—'}</td>
                            <td className="px-3 py-2 font-sans text-slate-600">{row.shipping_city || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Errors List */}
              {preview.errors.length > 0 && (
                <div>
                  <h4 className="mb-2 flex items-center space-x-1.5 text-sm font-semibold text-red-700">
                    <AlertTriangle className="h-4 w-4" />
                    <span>Row Validation Errors ({preview.errors.length})</span>
                  </h4>
                  <div className="max-h-48 overflow-y-auto rounded-lg border border-red-200 bg-red-50/40 p-2">
                    <table className="w-full text-left text-xs">
                      <thead className="border-b border-red-200 font-medium text-red-800">
                        <tr>
                          <th className="px-3 py-1.5">Row</th>
                          <th className="px-3 py-1.5">Order ID</th>
                          <th className="px-3 py-1.5">Column</th>
                          <th className="px-3 py-1.5">Error Details</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-red-100">
                        {preview.errors.map((err, idx) => (
                          <tr key={idx}>
                            <td className="px-3 py-1.5 font-mono text-red-800">#{err.row_index}</td>
                            <td className="px-3 py-1.5 font-mono text-slate-700">{err.external_order_id || '—'}</td>
                            <td className="px-3 py-1.5 font-mono text-slate-600">{err.column_name || '—'}</td>
                            <td className="px-3 py-1.5 text-red-700">{err.error_message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Stage B Commit Footer */}
              <div className="flex items-center justify-between border-t border-slate-200 pt-4">
                <button
                  type="button"
                  onClick={resetState}
                  className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Upload Different File
                </button>
                <button
                  type="button"
                  disabled={isCommitting || preview.valid_rows === 0}
                  onClick={handleCommit}
                  className="flex items-center space-x-2 rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-semibold text-white shadow hover:bg-emerald-700 disabled:opacity-50"
                >
                  {isCommitting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      <span>Committing Orders...</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle className="h-4 w-4" />
                      <span>Commit & Insert {preview.valid_rows} Valid Orders</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}

          {/* Post-Commit Summary */}
          {commitResult && (
            <div className="flex flex-col items-center justify-center space-y-4 py-8 text-center">
              <div className="rounded-full bg-emerald-100 p-3 text-emerald-600">
                <CheckCircle className="h-10 w-10" />
              </div>
              <h3 className="text-xl font-bold text-slate-900">Import Batch Successfully Committed!</h3>
              <p className="max-w-md text-sm text-slate-600">
                <span className="font-semibold text-emerald-700">{commitResult.inserted_count} orders</span>{' '}
                were transactionally inserted into your account with complete audit trail records.
                {commitResult.skipped_count > 0 && (
                  <span> ({commitResult.skipped_count} duplicates skipped).</span>
                )}
              </p>
              <div className="pt-4">
                <button
                  type="button"
                  onClick={() => {
                    resetState();
                    onClose();
                  }}
                  className="rounded-lg bg-emerald-600 px-6 py-2.5 text-sm font-semibold text-white shadow hover:bg-emerald-700"
                >
                  Done & View Orders
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
