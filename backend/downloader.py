import yt_dlp
import os
import re
from typing import Dict, List, Optional, Tuple
import time

class YouTubeDownloader:
    def __init__(self):
        pass
    
    def get_video_info(self, url: str) -> Dict:
        """Extract video information without downloading"""
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Get available formats
                formats = info.get("formats", [])
                qualities = []
                seen = set()
                
                for f in formats:
                    height = f.get("height")
                    ext = f.get("ext")
                    vcodec = f.get("vcodec", "none")
                    acodec = f.get("acodec", "none")
                    
                    # Filter for video formats with reasonable quality
                    if height and vcodec != "none" and ext in ("mp4", "webm"):
                        label = f"{height}p"
                        if label not in seen:
                            seen.add(label)
                            has_audio = acodec != "none"
                            
                            # Get the direct URL if available
                            direct_url = f.get("url")
                            
                            qualities.append({
                                "quality": height,
                                "label": label,
                                "has_audio": has_audio,
                                "filesize": f.get("filesize", 0),
                                "ext": ext,
                                "format_id": f.get("format_id"),
                                "direct_url": direct_url
                            })
                
                # Sort from highest to lowest quality
                qualities.sort(key=lambda x: x["quality"], reverse=True)
                
                # Also add best quality option
                best_quality = None
                for f in formats:
                    if f.get("vcodec") != "none" and f.get("acodec") != "none":
                        if not best_quality or f.get("height", 0) > best_quality.get("height", 0):
                            best_quality = f
                
                if best_quality and best_quality.get("height"):
                    best_label = f"{best_quality['height']}p (Best)"
                    if best_label not in [q["label"] for q in qualities]:
                        qualities.insert(0, {
                            "quality": best_quality["height"],
                            "label": best_label,
                            "has_audio": True,
                            "filesize": best_quality.get("filesize", 0),
                            "ext": best_quality.get("ext", "mp4"),
                            "format_id": best_quality.get("format_id"),
                            "direct_url": best_quality.get("url"),
                            "is_best": True
                        })
                
                return {
                    "title": info.get("title", "Unknown"),
                    "duration": info.get("duration_string", "Unknown"),
                    "uploader": info.get("uploader", "Unknown"),
                    "thumbnail": info.get("thumbnail", ""),
                    "description": info.get("description", "")[:500],
                    "views": info.get("view_count", 0),
                    "qualities": qualities,
                    "url": url
                }
        except Exception as e:
            raise Exception(f"Failed to fetch video info: {str(e)}")
    
    def get_stream_url(self, url: str, quality_label: str) -> Dict:
        """Get the direct stream URL for a specific quality"""
        try:
            # First, get video info without downloading
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Extract quality number from label
                quality_num = quality_label.replace("p", "").split()[0]
                
                # Find the best format matching the requested quality
                selected_format = None
                formats = info.get("formats", [])
                
                # Priority: exact quality with both audio and video, then video only, then fallback
                for f in formats:
                    height = f.get("height")
                    if height and int(height) <= int(quality_num):
                        vcodec = f.get("vcodec", "none")
                        acodec = f.get("acodec", "none")
                        
                        # Prefer formats with both audio and video
                        if vcodec != "none" and acodec != "none":
                            if not selected_format or height > selected_format.get("height", 0):
                                selected_format = f
                        # Then video only formats
                        elif vcodec != "none" and not selected_format:
                            selected_format = f
                
                # If we found a format with direct URL
                if selected_format and selected_format.get("url"):
                    filename = self.sanitize_filename(info["title"])
                    ext = selected_format.get("ext", "mp4")
                    
                    return {
                        "success": True,
                        "url": selected_format["url"],
                        "filename": f"{filename}.{ext}",
                        "filesize": selected_format.get("filesize", 0),
                        "format_id": selected_format.get("format_id")
                    }
                
                # Alternative method: Use format specification string
                format_spec = f"best[height<={quality_num}]"
                try:
                    # This is the correct way to get format in yt-dlp
                    best_format = None
                    for f in formats:
                        height = f.get("height")
                        if height and height <= int(quality_num):
                            if not best_format or height > best_format.get("height", 0):
                                best_format = f
                    
                    if best_format and best_format.get("url"):
                        filename = self.sanitize_filename(info["title"])
                        ext = best_format.get("ext", "mp4")
                        
                        return {
                            "success": True,
                            "url": best_format["url"],
                            "filename": f"{filename}.{ext}",
                            "filesize": best_format.get("filesize", 0)
                        }
                except Exception:
                    pass
                
                # Last resort: Get the best available format
                for f in formats:
                    if f.get("vcodec") != "none" and f.get("url"):
                        if not selected_format or f.get("height", 0) > selected_format.get("height", 0):
                            selected_format = f
                
                if selected_format and selected_format.get("url"):
                    filename = self.sanitize_filename(info["title"])
                    ext = selected_format.get("ext", "mp4")
                    
                    return {
                        "success": True,
                        "url": selected_format["url"],
                        "filename": f"{filename}.{ext}",
                        "filesize": selected_format.get("filesize", 0)
                    }
                
                return {"success": False, "error": "No downloadable format found"}
                
        except Exception as e:
            return {"success": False, "error": f"Failed to get stream URL: {str(e)}"}
    
    def download_video_direct(self, url: str, quality_label: str, output_path: str = None) -> Tuple[bool, str]:
        """Download video directly to server (alternative method)"""
        quality_num = quality_label.replace("p", "").split()[0]
        
        # Format selector for yt-dlp
        format_spec = f"bestvideo[height<={quality_num}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality_num}]/best"
        
        if not output_path:
            output_path = os.path.join(os.getcwd(), "downloads")
        
        os.makedirs(output_path, exist_ok=True)
        
        ydl_opts = {
            "format": format_spec,
            "outtmpl": os.path.join(output_path, "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": False,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                
                if not filename.endswith('.mp4'):
                    base = os.path.splitext(filename)[0]
                    filename = base + '.mp4'
                
                return True, filename
        except Exception as e:
            return False, str(e)
    
    def sanitize_filename(self, filename: str) -> str:
        """Remove invalid characters from filename"""
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        filename = filename.strip()
        return filename[:200]