# SignalForge v10.4 — Media Ingestion Layer

## Overview

The Media Ingestion Layer provides two controlled pathways for bringing approved client media into
SignalForge for processing. All ingested media is stored locally, starts review-gated, and is
**never published, uploaded, or transmitted to any third party by SignalForge**.

---

## Safety Guarantees

| Guarantee | Implementation |
|---|---|
| No external publishing | No social API calls anywhere in the pipeline |
| No auto-render | All ingested media requires operator review before use |
| No likeness/voice cloning | Explicitly out of scope for this layer |
| Simulation-safe records | All records: `simulation_only: true`, `outbound_actions_taken: 0` |
| Local storage only | Files stored in `YTDLP_OUTPUT_DIR` (default: `/tmp/signalforge_downloads`) |
| No shell injection | All subprocess calls use command arrays — never `shell=True` |

---

## Pathway 1 — Shared Folder / Drive Scan

Use this when the client has shared media via Google Drive (Desktop Sync), Dropbox, or a local
folder accessible on the host machine running SignalForge.

### Workflow

1. Client shares Google Drive folder or Dropbox folder with operator
2. Operator ensures the folder is synced to a local path on the SignalForge host
3. Navigate to **Creative Studio → Media Ingestion → Folder Scan**
4. Enter the local folder path (e.g. `/Users/you/Google Drive/My Drive/ClientName`)
5. Select the client profile and ingestion source type
6. Click **Scan Folder**
7. Each supported file is registered as a `media_intake_record` with `ingestion_status: discovered`
8. Navigate to the **Ingested Media** tab and select files to process

### Supported Extensions

| Extension | Type |
|---|---|
| `.mp4` | Video |
| `.mov` | Video |
| `.m4v` | Video |
| `.mp3` | Audio |
| `.wav` | Audio |
| `.m4a` | Audio |

### Duplicate Detection

The scanner skips files that have already been registered by comparing:
- Absolute file path (always checked)
- SHA-256 file hash (optional, enable with `compute_hashes: true`)

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `FFPROBE_PATH` | (auto-detected) | Path to ffprobe binary for duration extraction |

---

## Pathway 2 — Approved URL Download (yt-dlp)

Use this for downloading approved YouTube, Vimeo, or other supported videos for processing.
This pathway requires explicit operator permission confirmation and domain allowlisting.

### Prerequisites

1. Install yt-dlp on the host: `pip install yt-dlp` or via Homebrew
2. Set `YTDLP_ENABLED=true` in environment (default: `false`)
3. Add the target domain to `YTDLP_ALLOWED_DOMAINS`
4. Ensure you have the content owner's permission

### Workflow

1. Navigate to **Creative Studio → Media Ingestion → URL Download**
2. Paste the approved URL
3. Select client, format (video or audio-only), and add permission notes
4. Check the **permission confirmation** checkbox
5. Click **Download**
6. On success, a `media_intake_record` is created with `intake_method: yt_dlp`
7. Navigate to **Ingested Media** to process the downloaded file

### Domain Allowlist

Only domains listed in `YTDLP_ALLOWED_DOMAINS` are permitted. Subdomains are automatically
allowed (e.g. `youtube.com` allows `www.youtube.com`).

Default: `youtube.com,youtu.be`

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `YTDLP_ENABLED` | `false` | Must be explicitly set to `true` to enable downloads |
| `YTDLP_OUTPUT_DIR` | `/tmp/signalforge_downloads` | Local directory for downloaded files |
| `YTDLP_MAX_DURATION_SECONDS` | `7200` | Maximum allowed video duration (2 hours) |
| `YTDLP_ALLOWED_DOMAINS` | `youtube.com,youtu.be` | Comma-separated list of allowed domains |
| `YTDLP_PATH` | (auto-detected) | Explicit path to yt-dlp binary |
| `FFPROBE_PATH` | (auto-detected) | Path to ffprobe for duration extraction |

---

## API Reference

### Folder Scans

```
POST /media-folder-scans
GET  /media-folder-scans?workspace_slug=&client_id=
GET  /media-folder-scans/{scan_id}
```

**POST body:**
```json
{
  "workspace_slug": "john-maxwell-pilot",
  "client_id": "...",
  "folder_path": "/path/to/media",
  "source_label": "YouTube Recordings",
  "ingestion_source": "google_drive_sync",
  "compute_hashes": false
}
```

### Approved URL Downloads

```
POST /approved-url-downloads
GET  /approved-url-downloads?workspace_slug=&client_id=&status=
GET  /approved-url-downloads/{download_id}
```

**POST body:**
```json
{
  "workspace_slug": "john-maxwell-pilot",
  "client_id": "...",
  "url": "https://www.youtube.com/watch?v=...",
  "permission_confirmed": true,
  "requested_format": "audio",
  "notes": "Approved by client 2026-05-01"
}
```

### Diagnostics

```
GET /media-ingestion/diagnostics
```

Returns scanner status (supported extensions) and yt-dlp availability/configuration.

---

## Processing Pipeline (After Ingestion)

Once media is ingested, process it through:

1. **Extract Audio** — `POST /audio-extraction-runs/v4` with `media_intake_id`
2. **Transcribe** — `POST /transcript-runs/v4`
3. **Generate Snippets** — `POST /content-snippets/generate/v4`
4. **Score & Approve** — Review queue → approve top snippets
5. **Generate Prompt** — `POST /prompt-generations`
6. **Render Asset** — `POST /asset-renders` (when render infrastructure is available)

---

## Troubleshooting

### Folder scan finds 0 files
- Verify the path exists and is accessible: `ls /path/to/folder`
- Check file extensions — only `.mp4 .mov .m4v .mp3 .wav .m4a` are supported
- Ensure Google Drive / Dropbox sync is complete and files are downloaded locally

### yt-dlp download shows "skipped"
- Check `YTDLP_ENABLED` is set to `true`
- Verify the permission confirmation checkbox is checked
- Confirm the domain is in `YTDLP_ALLOWED_DOMAINS`

### yt-dlp download shows "failed — binary not found"
- Install yt-dlp: `pip install yt-dlp` or `brew install yt-dlp`
- Set `YTDLP_PATH` to the full binary path if not in `$PATH`
- Check with `GET /media-ingestion/diagnostics`

### Duration shows null
- Install ffprobe: `brew install ffmpeg`
- Set `FFPROBE_PATH` if not in `$PATH`
- Duration extraction is best-effort; null is safe and does not block ingestion

---

## Local Storage Notes

Downloaded files are stored at `{YTDLP_OUTPUT_DIR}/{workspace_slug}/`.

Example:
```
/tmp/signalforge_downloads/john-maxwell-pilot/The_Leadership_Principles_abc123.mp4
```

Files are never automatically deleted by SignalForge. Operators are responsible for managing
local disk usage.
