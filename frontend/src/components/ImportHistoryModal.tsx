'use client';

import React, { useEffect, useState } from 'react';
import { History, X, CheckCircle, Clock, AlertTriangle, Loader2 } from 'lucide-react';
import { ImportJob } from '@/types';
import { fetchImportHistory, fetchImportJobDetails } from '@/services/api';

interface ImportHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ImportHistoryModal: React.FC<ImportHistoryModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [selectedJob, setSelectedJob] = useState<ImportJob | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadHistory();
    }
  }, [isOpen]);

  const loadHistory = async () => {
    setIsLoading(true);
    try {
      const res = await fetchImportHistory(50, 0);
      setJobs(res.jobs);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectJob = async (job: ImportJob) => {
    setIsLoadingDetails(true);
    try {
      const details = await fetchImportJobDetails(job.id);
      setSelectedJob(details);
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoadingDetails(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="relative flex max-h-[85vh] w-full max-w-4xl flex-col rounded-xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div className="flex items-center space-x-3">
            <div className="rounded-lg bg-blue-50 p-2 text-blue-600">
              <History className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900">CSV Import History</h2>
              <p className="text-sm text-slate-500">Audit trail of past file uploads and staging batches</p>
            </div>
          </div>
          <button
            onClick={() => {
              setSelectedJob(null);
              onClose();
            }}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          {selectedJob ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-slate-900">
                    File: {selectedJob.filename}
                  </h3>
                  <p className="text-xs text-slate-500">Batch ID: {selectedJob.id}</p>
                </div>
                <button
                  onClick={() => setSelectedJob(null)}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                >
                  Back to List
                </button>
              </div>

              <div className="grid grid-cols-4 gap-3 text-center">
                <div className="rounded-lg bg-slate-50 p-3">
                  <div className="text-xs text-slate-500">Total</div>
                  <div className="text-lg font-bold text-slate-800">{selectedJob.total_rows}</div>
                </div>
                <div className="rounded-lg bg-emerald-50 p-3">
                  <div className="text-xs text-emerald-600">Valid</div>
                  <div className="text-lg font-bold text-emerald-700">{selectedJob.valid_rows}</div>
                </div>
                <div className="rounded-lg bg-amber-50 p-3">
                  <div className="text-xs text-amber-600">Duplicates</div>
                  <div className="text-lg font-bold text-amber-700">{selectedJob.duplicate_rows}</div>
                </div>
                <div className="rounded-lg bg-red-50 p-3">
                  <div className="text-xs text-red-600">Invalid</div>
                  <div className="text-lg font-bold text-red-700">{selectedJob.invalid_rows}</div>
                </div>
              </div>

              <div>
                <h4 className="mb-2 text-sm font-semibold text-slate-800">
                  Logged Row Errors ({selectedJob.errors?.length || 0})
                </h4>
                {selectedJob.errors && selectedJob.errors.length > 0 ? (
                  <div className="max-h-60 overflow-y-auto rounded-lg border border-red-200 bg-red-50/40 p-2">
                    <table className="w-full text-left text-xs">
                      <thead className="border-b border-red-200 font-semibold text-red-800">
                        <tr>
                          <th className="px-3 py-1.5">Row</th>
                          <th className="px-3 py-1.5">Order ID</th>
                          <th className="px-3 py-1.5">Column</th>
                          <th className="px-3 py-1.5">Error Message</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-red-100">
                        {selectedJob.errors.map((err) => (
                          <tr key={err.id}>
                            <td className="px-3 py-1.5 font-mono text-red-800">#{err.row_index}</td>
                            <td className="px-3 py-1.5 font-mono text-slate-700">
                              {err.external_order_id || '—'}
                            </td>
                            <td className="px-3 py-1.5 font-mono text-slate-600">{err.column_name || '—'}</td>
                            <td className="px-3 py-1.5 text-red-700">{err.error_message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">No row errors recorded for this import.</p>
                )}
              </div>
            </div>
          ) : (
            <div>
              {isLoading ? (
                <div className="flex items-center justify-center py-12 text-slate-400">
                  <Loader2 className="h-6 w-6 animate-spin" />
                </div>
              ) : jobs.length === 0 ? (
                <div className="py-12 text-center text-sm text-slate-400">
                  No previous import jobs recorded.
                </div>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-slate-200">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b bg-slate-50 font-semibold text-slate-600">
                      <tr>
                        <th className="px-4 py-2.5">Filename</th>
                        <th className="px-4 py-2.5">Status</th>
                        <th className="px-4 py-2.5">Total Rows</th>
                        <th className="px-4 py-2.5">Valid</th>
                        <th className="px-4 py-2.5">Errors</th>
                        <th className="px-4 py-2.5">Uploaded Date</th>
                        <th className="px-4 py-2.5">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {jobs.map((job) => (
                        <tr key={job.id} className="hover:bg-slate-50/60">
                          <td className="px-4 py-2.5 font-medium text-slate-900">{job.filename}</td>
                          <td className="px-4 py-2.5">
                            <span
                              className={`rounded px-2 py-0.5 font-bold ${
                                job.status === 'COMMITTED'
                                  ? 'bg-emerald-100 text-emerald-800'
                                  : 'bg-amber-100 text-amber-800'
                              }`}
                            >
                              {job.status}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 text-slate-700">{job.total_rows}</td>
                          <td className="px-4 py-2.5 text-emerald-700 font-semibold">{job.valid_rows}</td>
                          <td className="px-4 py-2.5 text-red-600 font-semibold">{job.invalid_rows}</td>
                          <td className="px-4 py-2.5 text-slate-500">
                            {new Date(job.created_at).toLocaleString('en-IN', {
                              dateStyle: 'short',
                              timeStyle: 'short',
                            })}
                          </td>
                          <td className="px-4 py-2.5">
                            <button
                              onClick={() => handleSelectJob(job)}
                              className="font-medium text-blue-600 hover:text-blue-800"
                            >
                              View Details
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
