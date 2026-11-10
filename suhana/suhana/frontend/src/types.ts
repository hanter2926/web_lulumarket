export type RegistrationStep = "register" | "verify" | "success" | "login" | "logged-in";
export type ActiveView = "auth" | "dashboard" | "storage" | "converter" | "compare" | "history" | "reset" | "plans";

export type FolderItem = { id: number; name: string; parent_id: number | null };
export type FileItem = { id: number; name: string; size_bytes: number; content_type: string; folder_id: number | null };
export type ReportItem = {
  id: number;
  first_name: string;
  second_name: string;
  comparison_type: string;
  result: { same_content: boolean };
  created_at: string;
};

export type PdfPageResult = {
  page: number;
  status?: string;
  text_same: boolean;
  first_text?: string;
  second_text?: string;
  visual?: {
    difference_percentage: number;
    differing_pixels: number | null;
    overlay_png: string | null;
  } | null;
};

export type PdfComparisonResult = {
  first: { page_count: number; has_text_layer: boolean; scanned_likely: boolean };
  second: { page_count: number; has_text_layer: boolean; scanned_likely: boolean };
  text_differences: number;
  visual_differences: number;
  page_results: PdfPageResult[];
};

export type ApiResponse = {
  success?: boolean;
  message?: string;
  csrfToken?: string;
  email?: string;
  wait_seconds?: number;
  result?: number;
  username?: string;
  storage?: { used_bytes: number; quota_bytes: number; plan: string } | null;
  file_count?: number;
  recent_files?: Array<{ id: number; name: string; size_bytes: number; content_type: string }>;
  files?: FileItem[];
  reports?: ReportItem[];
  folders?: FolderItem[];
  job_id?: string;
  job_token?: string;
  status?: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  status_url?: string;
  cancel_url?: string;
  cancel_requested?: boolean;
};

export type ComparisonResult = {
  same_content: boolean;
  same_type: boolean;
  first: { name: string; size_bytes: number; content_type: string };
  second: { name: string; size_bytes: number; content_type: string };
  pdf_comparison?: PdfComparisonResult;
  image_comparison?: { same_visual: boolean };
};

export type ComparisonResponse = ApiResponse & {
  comparison?: ComparisonResult;
};
