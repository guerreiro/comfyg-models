# comfyg-models

A ComfyUI custom node that adds a dedicated web interface for managing local AI models and exploring generated images — available at `/comfyg-models` inside your ComfyUI instance.

## Features

### 🗂️ Library (Models)

- Tabbed navigation by model type (Checkpoints, LoRAs, VAEs, ControlNets, Embeddings, Upscalers, CLIP, CLIP Vision)
- Search, sort, and filter by name, file size, CivitAI rating, base model, or tags
- Thumbnail gallery per model — upload reference images via drag-and-drop or file picker
- CivitAI integration: auto-sync metadata, trigger words, descriptions, and example images

### 🖼️ Results (Generated Images)

- Gallery view of all generated images found in configured scan folders
- Supports **PNG**, **WEBP**, and **AVIF** formats
- Automatic metadata extraction from image files:
  - ComfyUI `prompt` and `workflow` chunks (PNG `tEXt`/`zTXt`/`iTXt`)
  - WEBP `EXIF` and `XMP` chunks
  - AVIF `Exif` and `xml ` ISO boxes
- Extracted data stored efficiently — **workflow JSON is not stored in the database**, only indexed metadata (prompt text, model/LoRA refs, base model, tags)
- Workflow JSON available on-demand via `GET /comfyg-models/api/images/{id}/workflow`
- Filter by base model, checkpoint, LoRA, metadata presence, or free-text search
- Auto-tagging: source type, base model, model/LoRA names, prompt terms, subfolder
- Image deduplication via SHA256 — the same file added twice is stored once

### ⚙️ Settings

- CivitAI API key (stored server-side only — never exposed to the frontend)
- Configurable generated image scan paths with folder picker

## Access

After installing the plugin, open:

```
http://127.0.0.1:8188/comfyg-models
```

A direct-access button is also available in the ComfyUI top bar and the legacy floating menu.

## Installation

Clone or copy this repository into your ComfyUI custom nodes folder:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/guerreiro/comfyg-models
```

Dependencies are installed automatically by ComfyUI Manager. To install manually:

```bash
pip install blake3 aiosqlite watchdog
```

## Runtime Data

Plugin data is stored in:

```
ComfyUI/user/comfyg-models/
├── models.db        # Models, hashes, CivitAI data, tags, notes, ratings
├── images.db        # Generated image index (metadata only, no image blobs)
├── settings.json    # Plugin settings
└── user-images/     # Uploaded reference images for models
```

The two SQLite databases are intentionally split to keep the model database compact regardless of how many generated images are indexed. Image blobs are never stored — only the file path and extracted metadata.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/comfyg-models/api/models` | List models (supports filters, pagination) |
| `GET` | `/comfyg-models/api/models/{id}` | Model detail with gallery and prompts |
| `POST` | `/comfyg-models/api/models/{id}/sync` | Force re-sync model with CivitAI |
| `POST` | `/comfyg-models/api/models/{id}/images` | Upload image to model gallery |
| `GET` | `/comfyg-models/api/images` | List generated images (filters, pagination) |
| `GET` | `/comfyg-models/api/images/{id}` | Image detail |
| `GET` | `/comfyg-models/api/images/{id}/content` | Serve image file (PNG/WEBP/AVIF) |
| `GET` | `/comfyg-models/api/images/{id}/workflow` | Read ComfyUI workflow JSON from file on-demand |
| `POST` | `/comfyg-models/api/images/{id}/reveal` | Open image folder in file manager |
| `GET` | `/comfyg-models/api/images/filters` | Available filter buckets for the Results UI |
| `POST` | `/comfyg-models/api/scan` | Start model library scan |
| `POST` | `/comfyg-models/api/scan/stop` | Stop running model scan |
| `POST` | `/comfyg-models/api/results/scan` | Start generated image scan |
| `POST` | `/comfyg-models/api/results/scan/stop` | Stop running image scan |
| `GET` | `/comfyg-models/api/settings` | Read settings |
| `PUT` | `/comfyg-models/api/settings` | Update settings |
| `GET` | `/comfyg-models/api/export-data` | Download raw SQLite database |

## Notes

- Requires Python ≥ 3.8 and `aiosqlite`, `blake3`, `watchdog`
- CivitAI API key is stored server-side only and never sent to the frontend
- SHA256 deduplication prevents storing the same image twice
- Workflow JSON is read from the source file on-demand — not cached in the DB — keeping `images.db` small even with tens of thousands of images
- Scan jobs can be stopped at any time without corrupting the database