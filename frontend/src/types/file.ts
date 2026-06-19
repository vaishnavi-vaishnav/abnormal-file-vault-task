export interface StoredFile {
  id: string;
  file: string;
  file_hash: string;
  file_type: string;
  size: number;
  ref_count: number;
  created_at: string;
}

export interface File {
  id: string;
  original_filename: string;
  file_type: string;
  size: number;
  uploaded_at: string;
  file: string;
  stored_file?: StoredFile;
}

export interface StorageSummary {
  total_actual_bytes: number;
  total_logical_bytes: number;
  savings_bytes: number;
} 