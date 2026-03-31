// frontend/src/types/index.ts
export interface VideoQuality {
  quality: number;
  label: string;
  has_audio: boolean;
  filesize: number;
  ext: string;
  format_id?: string;
  direct_url?: string;
}

export interface VideoInfo {
  title: string;
  duration: string;
  uploader: string;
  thumbnail: string;
  description: string;
  views: number;
  qualities: VideoQuality[];
  url: string;
}

export interface DownloadProgress {
  status: string;
  percent?: string;
  speed?: string;
  eta?: string;
}

export interface ApiResponse<T> {
  success?: boolean;
  data?: T;
  error?: string;
  download_id?: string;
}

export interface AdConfig {
  ads_enabled: boolean;
  provider: string;
  message: string;
}