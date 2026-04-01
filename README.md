# comfyg-models

`comfyg-models` is a ComfyUI plugin for managing local AI models through a dedicated web interface.

It is designed to be more than a file list. The plugin aims to become the place where you keep context around your models: what they are, where they came from, how you use them, and what is worth remembering about each one.

## What It Does

- Provides a dedicated page inside ComfyUI at `/comfyg-models`
- Organizes local model collections in one place
- Connects local model files to CivitAI metadata
- Stores plugin data outside the repository in the ComfyUI `user/` directory
- Creates a foundation for personal notes, tags, reference images, favorite prompts, and usage history

## Supported Model Categories

- Checkpoints
- LoRAs
- VAEs
- ControlNets
- Embeddings
- Upscalers
- CLIP
- CLIP Vision

## Current Features

- Custom plugin page served by ComfyUI
- Settings screen
- Secure CivitAI API key storage and verification
- Local SQLite cache bootstrap

## Access

After installing the plugin in `ComfyUI/custom_nodes/comfyg-models`, open:

```text
http://127.0.0.1:8188/comfyg-models
```

## Runtime Data

The plugin stores its runtime data in:

```text
ComfyUI/user/comfyg-models/
```

This includes:

- `cache.db`
- `settings.json`
- cached preview images
- user reference images

## Notes

- The CivitAI API key is never returned to the frontend
- Runtime data is intentionally kept outside the plugin folder
