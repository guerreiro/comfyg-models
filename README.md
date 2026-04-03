# comfyg-models

`comfyg-models` is a ComfyUI plugin to manage local AI models and generated images through a dedicated web interface.

The plugin provides two main workspaces: **Library** for managing local models and **Results** for exploring generated images with ComfyUI metadata.

## What it does

- Provides a dedicated page within ComfyUI at `/comfyg-models`
- Organizes local model collections in one place
- Connects local model files to CivitAI metadata
- Scans folders to find generated images with ComfyUI metadata
- Stores plugin data in ComfyUI's `user/` directory
- Allows uploading and organizing reference images for each model

## Supported Model Categories

- Checkpoints
- LoRAs
- VAEs
- ControlNets
- Embeddings
- Upscalers
- CLIP
- CLIP Vision

### Library (Models)
- Local model list with preview
- Set main image for each model
- View model metadata
- Automatically scan model folders

### Results (Gallery)
- Generated image gallery
- Automatic scanning of configured folders
- Automatic metadata extraction (prompt, workflow, models used)
- Search by prompt, filename, or tags
- Auto tags: model, LoRA, base model, prompt terms
- Drag-and-drop image upload

### Settings
- CivitAI API key (stored securely)
- Local cache preview

### Images and Metadata
- ComfyUI PNG metadata extraction (prompt, workflow, etc.)
- Automatic identification of models and LoRAs used

## Access

After installing the plugin at `ComfyUI/custom_nodes/comfyg-models`, open:

```text
http://127.0.0.1:8188/comfyg-models
```

## Runtime Data

The plugin stores runtime data in:

```text
ComfyUI/user/comfyg-models/
```

This includes:

- `cache.db` - SQLite database with models, images, and settings
- `settings.json` - Plugin settings
- `user-images/` - Uploaded reference images
- Cached preview images

## Notes

- CivitAI API key is never returned to the frontend
- Runtime data is intentionally kept outside the plugin folder
- SQLite database enables efficient offline queries
- Images are deduplicated via SHA256 to save space