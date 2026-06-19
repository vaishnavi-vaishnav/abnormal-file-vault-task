import React, { useState } from 'react';
import { fileService } from '../services/fileService';
import { File as FileType } from '../types/file';
import { DocumentIcon, TrashIcon, ArrowDownTrayIcon, EyeIcon } from '@heroicons/react/24/outline';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

export const FileList: React.FC = () => {
  const queryClient = useQueryClient();
  const [detailsFile, setDetailsFile] = useState<FileType | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<{ id: string; name: string } | null>(null);

  const [search, setSearch] = useState('');
  const [fileTypeFilter, setFileTypeFilter] = useState('');
  const [sizeMin, setSizeMin] = useState('');
  const [sizeMax, setSizeMax] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  // Applied filters are set when the user clicks "Search"
  const [appliedFilters, setAppliedFilters] = useState<Record<string, any>>({});

  const handleApplyFilters = () => {
    setAppliedFilters({
      search: search || undefined,
      file_type: fileTypeFilter || undefined,
      size_min: sizeMin || undefined,
      size_max: sizeMax || undefined,
      date_from: dateFrom || undefined,
      date_to: dateTo || undefined,
    });
  };

  const handleClearFilters = () => {
    setSearch('');
    setFileTypeFilter('');
    setSizeMin('');
    setSizeMax('');
    setDateFrom('');
    setDateTo('');
    setAppliedFilters({});
  };

  // Query for fetching files (runs when appliedFilters changes)
  const { data: files, isLoading, error } = useQuery({
    queryKey: ['files', appliedFilters],
    queryFn: () =>
      fileService.getFiles({
        search: appliedFilters.search,
        file_type: appliedFilters.file_type,
        size_min: appliedFilters.size_min,
        size_max: appliedFilters.size_max,
        date_from: appliedFilters.date_from,
        date_to: appliedFilters.date_to,
      }),
  });

  const { data: summary } = useQuery({
    queryKey: ['files', 'summary'],
    queryFn: fileService.getStorageSummary,
  });

  // Fetch available file types for dropdown
  const { data: fileTypes } = useQuery({
    queryKey: ['fileTypes'],
    queryFn: fileService.getFileTypes,
  });

  // Mutation for deleting files
  const deleteMutation = useMutation({
    mutationFn: fileService.deleteFile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['files'] });
      queryClient.invalidateQueries({ queryKey: ['files', 'summary'] });
    },
  });

  // Mutation for downloading files
  const downloadMutation = useMutation({
    mutationFn: ({ fileUrl, filename }: { fileUrl: string; filename: string }) =>
      fileService.downloadFile(fileUrl, filename),
  });

  // Fetch single file details when user clicks the eye icon
  const viewFile = async (id: string) => {
    try {
      const data = await fileService.getFile(id);
      setDetailsFile(data);

      // For previewable types (pdf/text/image), fetch as blob and create object URL
      const ft = data.file_type || '';
      if (ft.startsWith('image/') || ft.includes('pdf') || ft.startsWith('text/')) {
        try {
          const blob = await fileService.fetchFileBlob(data.file);
          const url = window.URL.createObjectURL(blob);
          // revoke previous preview if any
          if (previewUrl) {
            window.URL.revokeObjectURL(previewUrl);
          }
          setPreviewUrl(url);
        } catch (err) {
          console.error('Failed to fetch preview blob:', err);
          setPreviewUrl(null);
        }
      } else {
        // non-previewable
        if (previewUrl) {
          window.URL.revokeObjectURL(previewUrl);
          setPreviewUrl(null);
        }
      }
    } catch (err) {
      console.error('View file error:', err);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteMutation.mutateAsync(id);
    } catch (err) {
      console.error('Delete error:', err);
    }
  };

  const handleDownload = async (fileUrl: string, filename: string) => {
    try {
      await downloadMutation.mutateAsync({ fileUrl, filename });
    } catch (err) {
      console.error('Download error:', err);
    }
  };

  if (isLoading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-gray-200 rounded w-1/4"></div>
          <div className="space-y-3">
            <div className="h-8 bg-gray-200 rounded"></div>
            <div className="h-8 bg-gray-200 rounded"></div>
            <div className="h-8 bg-gray-200 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border-l-4 border-red-400 p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg
                className="h-5 w-5 text-red-400"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <div className="ml-3">
              <p className="text-sm text-red-700">Failed to load files. Please try again.</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-4">Uploaded Files</h2>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filename"
          className="w-full sm:w-60 md:flex-1 md:min-w-0 h-8 text-sm px-2 border rounded"
        />
        <select
          value={fileTypeFilter}
          onChange={(e) => setFileTypeFilter(e.target.value)}
          className="w-full sm:w-44 md:flex-none h-8 text-sm px-2 border rounded bg-white"
        >
          <option value="">All types</option>
          {fileTypes && fileTypes.map((t: string) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <input
          value={sizeMin}
          onChange={(e) => setSizeMin(e.target.value)}
          placeholder="Min size bytes"
          className="w-full sm:w-32 md:w-40 h-8 text-sm px-2 border rounded"
        />
        <input
          value={sizeMax}
          onChange={(e) => setSizeMax(e.target.value)}
          placeholder="Max size bytes"
          className="w-full sm:w-32 md:w-40 h-8 text-sm px-2 border rounded"
        />
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          placeholder="Uploaded after"
          className="w-full sm:w-40 md:w-48 h-8 text-sm px-2 border rounded"
        />
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          placeholder="Uploaded before"
          className="w-full sm:w-40 md:w-48 h-8 text-sm px-2 border rounded"
        />
        <div className="flex w-full sm:w-auto gap-3 justify-start sm:justify-end">
          <button
            onClick={handleApplyFilters}
            className="w-full sm:w-auto px-3 py-1 text-sm bg-primary-600 text-white rounded"
          >
            Search
          </button>
          <button
            onClick={handleClearFilters}
            className="w-full sm:w-auto px-3 py-1 text-sm bg-gray-200 rounded"
          >
            Clear
          </button>
        </div>
      </div>
      {summary && (
        <div className="mb-4 p-3 bg-gray-50 rounded text-sm text-gray-700 space-y-1">
          <div>
            Storage saved: <strong>{(summary.savings_bytes / 1024).toFixed(2)} KB</strong>
            {summary.savings_bytes > 0 && summary.total_logical_bytes > 0 && (
              <span className="text-gray-500">
                {' '}({((summary.savings_bytes / summary.total_logical_bytes) * 100).toFixed(1)}% reduction)
              </span>
            )}
          </div>
          <div className="text-gray-500">
            Logical: {(summary.total_logical_bytes / 1024).toFixed(2)} KB · Actual: {(summary.total_actual_bytes / 1024).toFixed(2)} KB
          </div>
        </div>
      )}
      {!files || files.length === 0 ? (
        <div className="text-center py-12">
          <DocumentIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">No files</h3>
          <p className="mt-1 text-sm text-gray-500">
            Get started by uploading a file
          </p>
        </div>
      ) : (
        <div className="mt-6 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left text-sm font-medium text-gray-500">#</th>
                <th className="px-3 py-2 text-left text-sm font-medium text-gray-500">Filename</th>
                <th className="px-3 py-2 text-right text-sm font-medium text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {files.map((file, idx) => (
                <tr key={file.id}>
                  <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-500">{idx + 1}</td>
                  <td className="px-3 py-3 whitespace-nowrap text-sm text-gray-900">
                    <div className="flex items-center gap-3">
                      <DocumentIcon className="h-5 w-5 text-gray-400 flex-shrink-0" />
                      <button
                        onClick={() => setDetailsFile(file)}
                        className="text-left truncate w-full"
                        aria-label={`Show details for ${file.original_filename}`}
                      >
                        {file.original_filename}
                      </button>
                    </div>
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap text-sm text-right">
                    <div className="inline-flex items-center gap-2 justify-end">
                      <button
                        onClick={() => handleDownload(file.file, file.original_filename)}
                        className="inline-flex items-center p-2 rounded-md text-gray-600 hover:bg-gray-100"
                        aria-label={`Download ${file.original_filename}`}
                      >
                        <ArrowDownTrayIcon className="h-5 w-5" />
                        <span className="hidden sm:inline ml-1 text-sm"></span>
                      </button>
                      <button
                        onClick={() => viewFile(file.id)}
                        className="inline-flex items-center p-2 rounded-md text-gray-600 hover:bg-gray-100"
                        aria-label={`View details for ${file.original_filename}`}
                      >
                        <EyeIcon className="h-5 w-5" />
                        <span className="hidden sm:inline ml-1 text-sm"></span>
                      </button>
                      <button
                        onClick={() => setConfirmDelete({ id: file.id, name: file.original_filename })}
                        className="inline-flex items-center p-2 rounded-md text-red-600 hover:bg-red-50"
                        aria-label={`Delete ${file.original_filename}`}
                      >
                        <TrashIcon className="h-5 w-5" />
                        <span className="hidden sm:inline ml-1 text-sm text-red-600"></span>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {detailsFile && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => {
            // close and cleanup
            if (previewUrl) {
              window.URL.revokeObjectURL(previewUrl);
              setPreviewUrl(null);
            }
            setDetailsFile(null);
          }}
        >
          <div
            className="bg-white rounded-lg max-w-xl w-full shadow-lg p-6 relative"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => {
                if (previewUrl) {
                  window.URL.revokeObjectURL(previewUrl);
                  setPreviewUrl(null);
                }
                setDetailsFile(null);
              }}
              aria-label="Close details"
              className="absolute top-3 right-3 text-gray-500 hover:text-gray-700"
            >
              ✕
            </button>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">File details</h3>
            <p className="text-sm text-gray-700 break-all mb-2">{detailsFile.original_filename}</p>

            {/* Inline preview uses blob URL when available (previewUrl), otherwise fallback link */}
            <div className="mb-4">
              {previewUrl ? (
                detailsFile.file_type?.startsWith('image/') ? (
                  <img src={previewUrl} alt={detailsFile.original_filename} className="mx-auto max-h-96 w-auto rounded" />
                ) : (
                  <iframe src={previewUrl} title={detailsFile.original_filename} className="w-full h-96 border rounded" />
                )
              ) : (
                <div className="border rounded p-4 text-sm text-gray-600">
                  Preview not available for this file type.
                  <div className="mt-2">
                    <a href={detailsFile.file} target="_blank" rel="noopener noreferrer" className="text-primary-600 underline">Open in new tab</a>
                  </div>
                </div>
              )}
            </div>

            <div className="text-sm text-gray-500 space-y-1 mb-4">
              <div>Type: {detailsFile.file_type}</div>
              <div>Size: {(detailsFile.size / 1024).toFixed(2)} KB</div>
              <div>Uploaded: {new Date(detailsFile.uploaded_at).toLocaleString()}</div>
            </div>
            {/* Actions moved to the table row; details modal intentionally shows metadata only. */}
          </div>
        </div>
      )}
      {confirmDelete && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-60 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setConfirmDelete(null)}
        >
          <div
            className="bg-white rounded-lg max-w-md w-full shadow-lg p-6 relative"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Confirm delete</h3>
            <p className="text-sm text-gray-700 mb-4">Are you sure you want to delete <strong className="break-words">{confirmDelete.name}</strong>? This action cannot be undone.</p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(null)}
                className="px-3 py-2 bg-gray-200 rounded text-sm"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  await handleDelete(confirmDelete.id);
                  if (detailsFile && detailsFile.id === confirmDelete.id) setDetailsFile(null);
                  setConfirmDelete(null);
                }}
                className="px-3 py-2 bg-red-600 text-white rounded text-sm"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}; 