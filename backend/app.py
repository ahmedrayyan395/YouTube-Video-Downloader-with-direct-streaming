"""
YouTube Downloader - Flask Backend (Direct Browser Stream)
==========================================================
Videos pipe straight from yt-dlp -> browser.
NOTHING is ever saved on the server.

Install:
    pip install flask flask-cors yt-dlp

Run:
    python app.py
"""

import os
import re
import json
import shutil
import threading
import subprocess
import urllib.parse

from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import yt_dlp

app = Flask(__name__)
CORS(app, origins=[
    "http://localhost:5173",
    "http://localhost:3000", 
    "https://raahmed395.pythonanywhere.com",
    "https://you-tube-video-downloader-with-dire.vercel.app/",  # Add your frontend URL
    "*"  # Allow all for testing (remove in production)
])

# ─────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    ffmpeg_ok = shutil.which('ffmpeg') is not None
    return jsonify({
        'status':  'healthy',
        'ffmpeg':  ffmpeg_ok,
        'message': 'All systems ready' if ffmpeg_ok else 'ffmpeg not found — install it for HD quality'
    })


@app.route('/ad/status', methods=['GET'])
def ad_status():
    return jsonify({'ads_enabled': False, 'provider': 'google', 'message': 'Ad integration ready'})


# ─────────────────────────────────────────────────────────
# Video info
# ─────────────────────────────────────────────────────────

@app.route('/video-info', methods=['POST', 'OPTIONS'])
def video_info():
    if request.method == 'OPTIONS':
        return '', 200

    data = request.get_json(force=True) or {}
    url  = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            info = ydl.extract_info(url, download=False)

        ffmpeg_ok = shutil.which('ffmpeg') is not None
        seen      = set()
        qualities = []

        for f in info.get('formats', []):
            height = f.get('height')
            vcodec = f.get('vcodec', 'none')
            ext    = f.get('ext', '')
            if height and vcodec != 'none' and ext in ('mp4', 'webm'):
                label = f'{height}p'
                if label not in seen:
                    seen.add(label)
                    has_audio = f.get('acodec', 'none') != 'none'
                    qualities.append({
                        'quality':   height,
                        'label':     label,
                        'has_audio': has_audio,
                        'filesize':  f.get('filesize') or 0,
                        'ext':       ext,
                        'note':      '' if (has_audio or ffmpeg_ok) else 'Requires ffmpeg',
                    })

        qualities.sort(key=lambda x: x['quality'], reverse=True)

        return jsonify({
            'success': True,
            'data': {
                'title':       info.get('title', 'Unknown'),
                'duration':    info.get('duration_string', 'Unknown'),
                'uploader':    info.get('uploader', 'Unknown'),
                'thumbnail':   info.get('thumbnail', ''),
                'description': (info.get('description') or '')[:300],
                'views':       info.get('view_count', 0),
                'qualities':   qualities,
                'url':         url,
            }
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────
# Core: stream video bytes straight to browser
# ─────────────────────────────────────────────────────────

@app.route('/stream', methods=['GET'])
def stream_video():
    """
    Runs yt-dlp with -o - (stdout output) and pipes chunks
    directly to the HTTP response. The browser receives a
    standard file download — nothing is written to disk on
    the server.

    Query params:
        url     — YouTube video URL
        quality — e.g. "1080p"
    """
    url     = request.args.get('url', '').strip()
    quality = request.args.get('quality', '').strip()

    if not url or not quality:
        return jsonify({'error': 'url and quality are required'}), 400

    height    = re.sub(r'[^0-9]', '', quality) or '1080'
    ffmpeg_ok = shutil.which('ffmpeg') is not None

    if ffmpeg_ok:
        fmt = (
            f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/'
            f'bestvideo[height<={height}]+bestaudio/'
            f'best[height<={height}]'
        )
    else:
        # Without ffmpeg we can only serve pre-muxed streams (usually up to 720p)
        fmt = f'best[height<={height}][ext=mp4]/best[height<={height}]'

    # Get video title for the filename
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True}) as ydl:
            meta  = ydl.extract_info(url, download=False)
        title = meta.get('title', 'video')
    except Exception:
        title = 'video'

    safe_title   = re.sub(r'[^\w\s\-]', '', title).strip() or 'video'
    encoded_name = urllib.parse.quote(safe_title + '.mp4')

    # yt-dlp command — "-o -" tells it to write to stdout
    cmd = ['yt-dlp', '--format', fmt, '--no-playlist', '--quiet', '-o', '-', url]
    if ffmpeg_ok:
        cmd = ['yt-dlp', '--format', fmt, '--merge-output-format', 'mp4',
               '--no-playlist', '--quiet', '-o', '-', url]

    def generate():
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            while True:
                chunk = proc.stdout.read(65536)  # 64 KB chunks
                if not chunk:
                    break
                yield chunk
        finally:
            proc.stdout.close()
            proc.wait()

    return Response(
        stream_with_context(generate()),
        status=200,
        headers={
            'Content-Type':        'video/mp4',
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_name}",
            'Transfer-Encoding':   'chunked',
            'X-Accel-Buffering':   'no',
            'Cache-Control':       'no-cache',
        },
        direct_passthrough=True,
    )


# ─────────────────────────────────────────────────────────
# SSE progress — tracks yt-dlp progress hooks (simulate mode)
# so the UI can show a real progress bar while the user waits
# for the stream to start.
# ─────────────────────────────────────────────────────────

@app.route('/stream-progress', methods=['GET'])
def stream_progress():
    """
    SSE endpoint.  Runs yt-dlp in --simulate mode (no download)
    with progress hooks so we can report % / speed / eta.
    The frontend shows this bar, then triggers /api/stream
    once status == 'ready'.

    Query params: url, quality
    """
    url     = request.args.get('url', '').strip()
    quality = request.args.get('quality', '').strip()

    if not url or not quality:
        return jsonify({'error': 'url and quality are required'}), 400

    height    = re.sub(r'[^0-9]', '', quality) or '1080'
    ffmpeg_ok = shutil.which('ffmpeg') is not None

    fmt = (
        f'bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/'
        f'bestvideo[height<={height}]+bestaudio/best[height<={height}]'
        if ffmpeg_ok else
        f'best[height<={height}][ext=mp4]/best[height<={height}]'
    )

    state = {'pct': 0, 'speed': '—', 'eta': '—', 'status': 'starting', 'done': False, 'error': None}

    def hook(d):
        if d['status'] == 'downloading':
            raw = d.get('_percent_str', '0%').replace('%', '').strip()
            try:
                state['pct'] = round(float(raw), 1)
            except ValueError:
                pass
            state['speed']  = d.get('_speed_str', '—').strip()
            state['eta']    = d.get('_eta_str',   '—').strip()
            state['status'] = 'downloading'
        elif d['status'] == 'finished':
            state['pct']    = 100
            state['status'] = 'merging'

    def run():
        try:
            opts = {
                'format':              fmt,
                'merge_output_format': 'mp4',
                'noplaylist':          True,
                'quiet':               True,
                'no_warnings':         True,
                'progress_hooks':      [hook],
                'simulate':            True,
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.extract_info(url, download=True)
            state['status'] = 'ready'
        except Exception as e:
            state['error']  = str(e)
            state['status'] = 'error'
        finally:
            state['done'] = True

    threading.Thread(target=run, daemon=True).start()

    def generate():
        import time
        while not state['done']:
            yield f"data: {json.dumps({k: state[k] for k in ('pct','speed','eta','status')})}\n\n"
            time.sleep(0.7)
        yield f"data: {json.dumps({'pct': state['pct'], 'speed': '—', 'eta': '—', 'status': state['status'], 'error': state['error']})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


if __name__ == '__main__':
    ffmpeg = shutil.which('ffmpeg')
    print("=" * 55)
    print("  YT Downloader  —  Direct Stream Mode")
    print("=" * 55)
    print("  http://localhost:5000")
    print("  Videos stream straight to the browser.")
    print("  Zero server storage used.")
    print(f"  ffmpeg : {'✓  ' + ffmpeg if ffmpeg else '✗  Not found (install for 1080p+)'}")
    print("=" * 55)
    app.run(debug=True, port=5000, host='127.0.0.1', threaded=True)
    
     # Get port from environment variable (for Render)
    # port =5000
    # app.run(debug=False, host='0.0.0.0', port=port)