# SIPHON

A simple window for downloading videos. No commands to type.
Works on Windows, macOS and Linux.

## How to use it

**Windows** — double-click **`launch.bat`**
**macOS / Linux** — run **`./launch.sh`** in Terminal

Then:

1. A console window opens — **leave it open**, that's the engine
2. Your browser opens automatically to the SIPHON page
3. Paste a video link, click **FETCH**
4. Pick a quality, click **DOWNLOAD**
5. When it says FINISHED, click **OPEN FOLDER**

When you're done for the day, close the console window (Ctrl+C on Mac/Linux).

## Where files go

| Type | macOS | Windows / Linux |
|---|---|---|
| Video | `~/Movies/YouTube` | `~/Videos/YouTube` |
| MP3 | `~/Music/YouTube` | `~/Music/YouTube` |

If you already keep downloads in the other location, SIPHON uses that instead
rather than starting a second library.

## The three dots at the bottom

Green means healthy. If one turns red:

| Dot | Windows | macOS | Linux |
|---|---|---|---|
| **yt-dlp** | `python -m pip install --upgrade yt-dlp` | same, with `python3` | same, with `python3` |
| **ffmpeg** | `winget install Gyan.FFmpeg` | `brew install ffmpeg` | `sudo apt install ffmpeg` |
| **deno** | `winget install DenoLand.Deno` | `brew install deno` | `sudo apt install deno` |

ffmpeg is required to merge video and audio. Deno is optional — without it some
downloads get throttled or miss the highest-quality formats.

## If a download suddenly stops working

YouTube changes things regularly and breaks the downloader. This fixes it
almost every time:

```
python -m pip install --upgrade yt-dlp
```

Use `python3` on macOS and Linux. Then restart SIPHON.

## Requirements

- Python 3.9 or newer
- ffmpeg on your PATH
- On macOS, Homebrew installs land in `/opt/homebrew/bin` (Apple Silicon) or
  `/usr/local/bin` (Intel). SIPHON adds both to its own PATH at startup, so it
  finds ffmpeg even when launched from Finder rather than a terminal.

## Notes

- Everything runs on your own machine. Nothing is uploaded anywhere.
- SIPHON ignores the global yt-dlp config file on purpose, so what you pick
  in the window is exactly what you get.
- Downloading videos you don't own is against YouTube's terms of service.
