#!/usr/bin/env python3
"""
SIPHON - a local web UI for yt-dlp.

Everything runs on this machine. No accounts, no uploads, no telemetry.
Double-click launch.bat instead of running this directly.
"""

import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
HOME = Path.home()


def _pick(primary, fallback):
    """Prefer whichever folder already holds files, else the platform default."""
    has = lambda d: d.is_dir() and any(d.iterdir())
    return fallback if has(fallback) and not has(primary) else primary


# macOS keeps video in ~/Movies; Windows and Linux in ~/Videos. ~/Music is
# the right place for audio on all three.
if sys.platform == "darwin":
    VIDEO_DIR = _pick(HOME / "Movies" / "YouTube", HOME / "Videos" / "YouTube")
else:
    VIDEO_DIR = _pick(HOME / "Videos" / "YouTube", HOME / "Movies" / "YouTube")
AUDIO_DIR = HOME / "Music" / "YouTube"
PORT = 8777

# Keep spawned yt-dlp from flashing a console window on Windows.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

FORMATS = {
    "best": "bv*+ba/b",
    "1080": "bv*[height<=1080]+ba/b",
    "720":  "bv*[height<=720]+ba/b",
}

JOBS = {}
LOCK = threading.Lock()


def augment_path():
    """Find deno/ffmpeg even if this process started with a stale PATH."""
    extra = []
    if sys.platform == "win32":
        pkgs = HOME / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
        if pkgs.is_dir():
            for exe in ("deno.exe", "ffmpeg.exe"):
                if shutil.which(exe[:-4]):
                    continue
                for found in pkgs.glob(f"*/**/{exe}"):
                    extra.append(str(found.parent))
                    break
    else:
        # A GUI-launched process often misses Homebrew's bin dirs, and Apple
        # Silicon puts them somewhere Intel Macs never did.
        current = os.environ.get("PATH", "")
        for d in ("/opt/homebrew/bin", "/usr/local/bin"):
            if Path(d).is_dir() and d not in current:
                extra.append(d)
    if extra:
        os.environ["PATH"] = os.pathsep.join(extra + [os.environ.get("PATH", "")])
    return extra


def ytdlp(*args):
    """Base yt-dlp command. --ignore-config so the global config file can't
    fight with the choices made in the UI."""
    return [sys.executable, "-m", "yt_dlp", "--ignore-config",
            "--remote-components", "ejs:github", *args]


def run(cmd, timeout=180):
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, creationflags=NO_WINDOW)


def tidy_error(text):
    """Turn yt-dlp's noise into one sentence a human can act on."""
    if not text:
        return "Something went wrong."
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("ERROR:"):
            msg = line[6:].strip()
            low = msg.lower()
            if "private" in low:
                return "That video is private."
            if "unavailable" in low or "removed" in low:
                return "That video is unavailable or has been removed."
            if "age" in low and "confirm" in low:
                return "That video is age-restricted and needs a signed-in account."
            if "not a valid url" in low or "unsupported url" in low:
                return "That doesn't look like a video link."
            return msg.split(";")[0][:220]
    return text.strip().splitlines()[-1][:220]


def health():
    try:
        ok_yt = run([sys.executable, "-m", "yt_dlp", "--version"], timeout=60).returncode == 0
    except Exception:
        ok_yt = False
    return {
        "ytdlp": ok_yt,
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "deno": shutil.which("deno") is not None,
        "video_dir": str(VIDEO_DIR),
        "audio_dir": str(AUDIO_DIR),
    }


def fetch_info(url):
    p = run(ytdlp("--dump-single-json", "--no-playlist", "--no-warnings", url))
    if p.returncode != 0 or not p.stdout.strip():
        raise RuntimeError(tidy_error(p.stderr))
    d = json.loads(p.stdout)
    return {
        "title": d.get("title") or "Untitled",
        "uploader": d.get("uploader") or d.get("channel") or "",
        "duration": d.get("duration") or 0,
        "thumbnail": d.get("thumbnail") or "",
        "maybe_playlist": "list=" in url,
    }


def run_job(job_id, url, quality, playlist):
    job = JOBS[job_id]
    outdir = AUDIO_DIR if quality == "audio" else VIDEO_DIR
    outdir.mkdir(parents=True, exist_ok=True)

    args = [
        "--newline",
        "--progress-template",
        "download:PRG|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
        "--print", "after_move:FINAL|%(filepath)s",
        "--no-warnings",
        "-o", str(outdir / "%(title)s [%(id)s].%(ext)s"),
        "--concurrent-fragments", "4",
        "--embed-metadata", "--embed-thumbnail", "--embed-chapters",
        "--yes-playlist" if playlist else "--no-playlist",
    ]
    if quality == "audio":
        args += ["-x", "--audio-format", "mp3"]
    else:
        args += ["-f", FORMATS.get(quality, FORMATS["best"]),
                 "--merge-output-format", "mp4"]
    args.append(url)

    try:
        proc = subprocess.Popen(
            ytdlp(*args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=NO_WINDOW)
    except Exception as exc:
        with LOCK:
            job.update(status="error", error=str(exc))
        return

    job["proc"] = proc
    tail = []

    for raw in proc.stdout:
        line = raw.rstrip("\r\n")
        if not line:
            continue
        tail.append(line)
        del tail[:-40]

        with LOCK:
            if line.startswith("PRG|"):
                parts = line.split("|")
                if len(parts) >= 4:
                    try:
                        job["percent"] = float(parts[1].strip().rstrip("%"))
                    except ValueError:
                        pass
                    job["speed"] = parts[2].strip()
                    job["eta"] = parts[3].strip()
                job["status"] = "downloading"
                job["stage"] = "Downloading"
            elif line.startswith("FINAL|"):
                job["file"] = line[6:].strip()
                job["files"] = job.get("files", 0) + 1
            elif line.startswith("ERROR:"):
                job["error"] = tidy_error(line)
            elif "[Merger]" in line:
                job.update(status="processing", stage="Merging video and audio", percent=100.0)
            elif "[ExtractAudio]" in line:
                job.update(status="processing", stage="Converting to MP3", percent=100.0)
            elif "[EmbedThumbnail]" in line or "[Metadata]" in line:
                job.update(status="processing", stage="Adding cover art and details", percent=100.0)

    code = proc.wait()
    with LOCK:
        if job.get("cancelled"):
            job["status"] = "cancelled"
        elif code == 0 and not job.get("error"):
            job.update(status="done", percent=100.0, stage="Finished")
        else:
            job["status"] = "error"
            if not job.get("error"):
                job["error"] = tidy_error("\n".join(tail))
        job.pop("proc", None)


def reveal(target):
    """Open the OS file manager at a file or folder, selecting the file if we can."""
    select = target if target.is_file() else None
    folder = target.parent if select else (target if target.is_dir() else VIDEO_DIR)
    folder.mkdir(parents=True, exist_ok=True)

    if sys.platform == "win32":
        cmd = ["explorer", "/select,", str(select)] if select else ["explorer", str(folder)]
    elif sys.platform == "darwin":
        cmd = ["open", "-R", str(select)] if select else ["open", str(folder)]
    else:
        cmd = ["xdg-open", str(folder)]          # most Linux desktops ignore -R
    subprocess.Popen(cmd)


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, *a):
        pass  # keep the console quiet

    def _send(self, obj, code=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path == "/api/health":
            return self._send(health())
        if self.path.startswith("/api/progress/"):
            jid = self.path.rsplit("/", 1)[-1]
            with LOCK:
                job = JOBS.get(jid)
                if not job:
                    return self._send({"error": "no such job"}, 404)
                return self._send({k: v for k, v in job.items() if k != "proc"})
        return super().do_GET()

    def do_POST(self):
        try:
            if self.path == "/api/info":
                return self._send(fetch_info(self._body().get("url", "").strip()))

            if self.path == "/api/download":
                b = self._body()
                url = b.get("url", "").strip()
                if not url:
                    return self._send({"error": "No link given."}, 400)
                jid = uuid.uuid4().hex[:12]
                JOBS[jid] = {"id": jid, "status": "starting", "percent": 0.0,
                             "speed": "", "eta": "", "stage": "Starting up",
                             "title": b.get("title", ""), "file": "", "error": ""}
                threading.Thread(target=run_job, daemon=True, args=(
                    jid, url, b.get("quality", "best"), bool(b.get("playlist")))).start()
                return self._send({"id": jid})

            if self.path.startswith("/api/cancel/"):
                jid = self.path.rsplit("/", 1)[-1]
                with LOCK:
                    job = JOBS.get(jid) or {}
                    job["cancelled"] = True
                    proc = job.get("proc")
                if proc:
                    proc.terminate()
                return self._send({"ok": True})

            if self.path == "/api/reveal":
                reveal(Path(self._body().get("path") or VIDEO_DIR))
                return self._send({"ok": True})

        except Exception as exc:
            return self._send({"error": tidy_error(str(exc))}, 400)

        self._send({"error": "unknown endpoint"}, 404)


def main():
    found = augment_path()
    VIDEO_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 58)
    print("  SIPHON  -  video downloader")
    print("=" * 58)
    if found:
        print("  found tools in:", ", ".join(found))
    print(f"  Videos go to : {VIDEO_DIR}")
    print(f"  Audio  go to : {AUDIO_DIR}")
    print(f"\n  Open in your browser:  http://localhost:{PORT}")
    print("\n  Leave this black window open while downloading.")
    print("  Close it when you're done.")
    print("=" * 58)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down.")


if __name__ == "__main__":
    main()
