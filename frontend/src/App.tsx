import { useState, useEffect, useRef } from 'react';
import { Toaster, toast } from 'react-hot-toast';
import { Play, Loader2, Video, Clock, User, Eye, Download, Wifi, WifiOff } from 'lucide-react';
import axios from 'axios';
import './App.css';

// const API = 'http://localhost:5000/api';
// At the top of App.tsx, replace the API constant
const API = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';

interface VideoQuality {
  quality: number;
  label: string;
  has_audio: boolean;
  filesize: number;
  ext: string;
  note: string;
}

interface VideoInfo {
  title: string;
  duration: string;
  uploader: string;
  thumbnail: string;
  description: string;
  views: number;
  qualities: VideoQuality[];
  url: string;
}

interface ProgressState {
  pct: number;
  speed: string;
  eta: string;
  status: 'idle' | 'starting' | 'downloading' | 'merging' | 'ready' | 'streaming' | 'error';
  error: string | null;
}

export default function App() {
  const [url, setUrl]           = useState('');
  const [loading, setLoading]   = useState(false);
  const [videoInfo, setVideoInfo] = useState<VideoInfo | null>(null);
  const [backend, setBackend]   = useState<'checking' | 'online' | 'offline'>('checking');
  const [progress, setProgress] = useState<ProgressState>({
    pct: 0, speed: '—', eta: '—', status: 'idle', error: null
  });
  const [selectedQuality, setSelectedQuality] = useState('');
  const sseRef = useRef<EventSource | null>(null);

  useEffect(() => {
    checkBackend();
    return () => sseRef.current?.close();
  }, []);

  // ── Backend health ────────────────────────────────────
  const checkBackend = async () => {
    try {
      const res = await axios.get(`${API}/health`);
      setBackend(res.data.status === 'healthy' ? 'online' : 'offline');
      if (!res.data.ffmpeg) {
        toast('ffmpeg not found — HD quality may not include audio', { icon: '⚠️' });
      }
    } catch {
      setBackend('offline');
      toast.error('Flask server offline. Run: python app.py');
    }
  };

  // ── Fetch video info ──────────────────────────────────
  const fetchVideoInfo = async () => {
    if (!url.trim()) { toast.error('Paste a YouTube URL first'); return; }
    if (backend !== 'online') { toast.error('Backend is offline'); return; }

    setLoading(true);
    setVideoInfo(null);
    setProgress({ pct: 0, speed: '—', eta: '—', status: 'idle', error: null });

    try {
      const res = await axios.post(`${API}/video-info`, { url });
      if (res.data.success) {
        setVideoInfo(res.data.data);
        toast.success('Video info loaded');
      } else {
        toast.error(res.data.error || 'Failed to load video');
      }
    } catch (e: any) {
      toast.error(e.response?.data?.error || 'Failed to fetch video info');
    } finally {
      setLoading(false);
    }
  };

  // ── Start download flow ───────────────────────────────
  const handleDownload = (quality: VideoQuality) => {
    if (!videoInfo) return;
    setSelectedQuality(quality.label);
    setProgress({ pct: 0, speed: '—', eta: '—', status: 'starting', error: null });

    // Close any existing SSE
    sseRef.current?.close();

    const params = new URLSearchParams({ url: videoInfo.url, quality: quality.label });

    // Step 1: open SSE to track yt-dlp progress (simulate mode)
    const sse = new EventSource(`${API}/stream-progress?${params}`);
    sseRef.current = sse;

    sse.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        setProgress({
          pct:    data.pct    ?? 0,
          speed:  data.speed  ?? '—',
          eta:    data.eta    ?? '—',
          status: data.status ?? 'downloading',
          error:  data.error  ?? null,
        });

        if (data.status === 'ready') {
          // Step 2: SSE done — now trigger the actual stream download
          sse.close();
          triggerBrowserDownload(videoInfo.url, quality.label, videoInfo.title);
        }

        if (data.status === 'error') {
          sse.close();
          toast.error(data.error || 'Download failed');
        }
      } catch {}
    };

    sse.onerror = () => {
      sse.close();
      // If SSE fails (e.g. simulate not supported), go straight to stream
      triggerBrowserDownload(videoInfo.url, quality.label, videoInfo.title);
    };
  };

  // ── Actually stream the file to browser ──────────────
  const triggerBrowserDownload = (videoUrl: string, quality: string, title: string) => {
    setProgress(p => ({ ...p, status: 'streaming', pct: 100 }));

    // Build the stream URL — browser navigates to it and receives the file
    const params = new URLSearchParams({ url: videoUrl, quality });
    const streamUrl = `${API}/stream?${params}`;

    // Create an invisible <a> and click it — browser shows its native Save dialog
    const a = document.createElement('a');
    a.href     = streamUrl;
    a.download = `${title}.mp4`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    toast.success('Download started — check your browser downloads bar');

    // Reset UI after a moment
    setTimeout(() => {
      setProgress({ pct: 0, speed: '—', eta: '—', status: 'idle', error: null });
      setSelectedQuality('');
    }, 4000);
  };

  // ── Helpers ───────────────────────────────────────────
  const formatSize = (bytes: number) => {
    if (!bytes) return '';
    const units = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
  };

  const formatViews = (v: number) => {
    if (!v) return 'N/A';
    if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M';
    if (v >= 1_000)     return (v / 1_000).toFixed(1) + 'K';
    return v.toString();
  };

  const isDownloading = ['starting','downloading','merging','streaming'].includes(progress.status);

  const statusLabel: Record<string, string> = {
    starting:   'Preparing…',
    downloading: `Downloading ${selectedQuality}…`,
    merging:    'Merging video + audio…',
    streaming:  'Sending to your browser…',
    error:      'Failed',
  };

  return (
    <div className="container">
      <Toaster position="top-right" toastOptions={{ style: { fontFamily: 'inherit' } }} />

      {/* Status badge */}
      <div className="backend-status" style={{
        position: 'fixed', top: 12, right: 12, zIndex: 1000,
        padding: '5px 12px', borderRadius: 6, fontSize: 12,
        display: 'flex', alignItems: 'center', gap: 6,
        background: backend === 'online' ? '#10b981' : backend === 'offline' ? '#ef4444' : '#6b7280',
        color: '#fff'
      }}>
        {backend === 'online'
          ? <><Wifi size={12} /> Backend Online</>
          : backend === 'offline'
          ? <><WifiOff size={12} /> Backend Offline</>
          : 'Checking…'
        }
      </div>

      {/* Header */}
      <div className="header">
        <div className="header-icon"><Play /></div>
        <h1>YouTube Video Downloader</h1>
        <p>Videos stream directly to your device — nothing stored on the server</p>
      </div>

      {/* URL input */}
      <div className="card">
        <div className="url-section">
          <input
            type="text"
            value={url}
            onChange={e => { setUrl(e.target.value); setVideoInfo(null); }}
            onKeyDown={e => e.key === 'Enter' && fetchVideoInfo()}
            placeholder="Paste YouTube URL here…"
            className="url-input"
            disabled={loading || isDownloading}
          />
          <button
            onClick={fetchVideoInfo}
            disabled={loading || isDownloading || !url.trim()}
            className="btn-primary"
          >
            {loading ? <Loader2 className="spinner" size={16} /> : <Video size={16} />}
            {loading ? 'Loading…' : 'Get Info'}
          </button>
        </div>
      </div>

      {/* Video info */}
      {videoInfo && !isDownloading && (
        <div className="video-info-grid">
          <div className="card">
            {videoInfo.thumbnail && (
              <img src={videoInfo.thumbnail} alt={videoInfo.title} className="thumbnail"
                onError={e => (e.currentTarget.style.display = 'none')} />
            )}
          </div>
          <div className="card">
            <h2 className="video-title">{videoInfo.title}</h2>
            <div className="video-meta">
              <div className="meta-item"><User className="meta-icon" size={14} /><span>{videoInfo.uploader}</span></div>
              <div className="meta-item"><Clock className="meta-icon" size={14} /><span>{videoInfo.duration}</span></div>
              <div className="meta-item"><Eye className="meta-icon" size={14} /><span>{formatViews(videoInfo.views)} views</span></div>
            </div>
            {videoInfo.description && (
              <p className="video-description">{videoInfo.description}</p>
            )}
          </div>
        </div>
      )}

      {/* Quality grid */}
      {videoInfo && !isDownloading && videoInfo.qualities.length > 0 && (
        <div className="card">
          <h2 style={{ marginBottom: '1rem' }}>Select Quality to Download</h2>
          <div className="quality-grid">
            {videoInfo.qualities.map((q, i) => (
              <button key={i} className="quality-card" onClick={() => handleDownload(q)}>
                <div className="quality-title">{q.label}</div>
                <div className="quality-audio">
                  {q.has_audio ? '✅ Video + Audio' : '🎵 Audio will be merged'}
                </div>
                {q.filesize > 0 && (
                  <div className="quality-size">{formatSize(q.filesize)}</div>
                )}
                {q.note && (
                  <div style={{ fontSize: '0.7rem', color: '#f59e0b', marginTop: 4 }}>{q.note}</div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Progress panel */}
      {isDownloading && (
        <div className="card">
          <div className="download-progress">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: '0.75rem' }}>
              <Loader2 className="spinner" size={18} />
              <h3 style={{ margin: 0 }}>{statusLabel[progress.status] ?? 'Processing…'}</h3>
            </div>

            <div className="progress-bar-container">
              <div className="progress-bar" style={{ width: `${progress.pct}%`, transition: 'width 0.6s ease' }}>
                {progress.pct > 5 && `${progress.pct.toFixed(1)}%`}
              </div>
            </div>

            <div className="progress-stats" style={{ marginTop: '0.75rem', display: 'flex', gap: '1.5rem' }}>
              {progress.speed !== '—' && (
                <div>
                  <span style={{ fontSize: '0.75rem', opacity: 0.6 }}>SPEED</span>
                  <div style={{ fontFamily: 'monospace', fontSize: '0.9rem' }}>{progress.speed}</div>
                </div>
              )}
              {progress.eta !== '—' && (
                <div>
                  <span style={{ fontSize: '0.75rem', opacity: 0.6 }}>ETA</span>
                  <div style={{ fontFamily: 'monospace', fontSize: '0.9rem' }}>{progress.eta}</div>
                </div>
              )}
            </div>

            {progress.status === 'streaming' && (
              <div style={{ marginTop: '0.75rem', padding: '0.6rem 1rem', background: 'rgba(16,185,129,0.1)',
                border: '1px solid rgba(16,185,129,0.3)', borderRadius: 8, fontSize: '0.875rem', color: '#10b981' }}>
                <Download size={14} style={{ display: 'inline', marginRight: 6 }} />
                File is streaming to your device — check your downloads bar
              </div>
            )}
          </div>
        </div>
      )}

      <div className="footer">
        <p>For personal / fair-use downloads only. Respect copyright laws.</p>
      </div>
    </div>
  );
}
