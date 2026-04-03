import type { CivitaiModelData } from "./civitai";

export type ModelType =
  | "checkpoint"
  | "lora"
  | "vae"
  | "controlnet"
  | "embedding"
  | "upscaler"
  | "clip"
  | "clip_vision";

export interface Model {
  id: string;
  filename: string;
  directory: string;
  type: ModelType;
  file_size: number | null;
  sha256: string | null;
  blake3: string | null;
  civitai_model_id: number | null;
  civitai_version_id: number | null;
  civitai_data: CivitaiModelData | null;
  last_hash_at: string | null;
  last_civitai_sync: string | null;
  last_used_at: string | null;
  use_count: number;
  created_at: string;
  primary_user_image?: string | null;
  note?: string | null;
  tags?: string[];
  rating?: number | null;
}

export interface ModelUserImage {
  id: number;
  filename: string;
  caption: string | null;
  prompt: string | null;
  negative_prompt: string | null;
  is_primary: number;
  created_at: string;
  source_type?: string;
  storage_type?: string;
  path?: string | null;
  sha256?: string | null;
  has_comfy_metadata?: number;
  prompt_text?: string | null;
}

export interface ModelPrompt {
  id: number;
  title: string | null;
  prompt: string;
  negative_prompt: string | null;
  notes: string | null;
  created_at: string;
}

export interface ModelPreview {
  url: string;
  local_filename: string | null;
}

export interface ModelDetail extends Model {
  user_images: ModelUserImage[];
  gallery_images?: GalleryImage[];
  prompts: ModelPrompt[];
  civitai_previews: ModelPreview[];
}

export interface GalleryImageSource {
  id: number;
  source_type: "upload" | "scanned_file";
  storage_type: "managed" | "external";
  path: string | null;
  filename: string;
  caption: string | null;
  prompt: string | null;
  negative_prompt: string | null;
  scan_root?: string | null;
  is_present: number;
  created_at: string;
}

export interface GalleryImageTag {
  tag: string;
  tag_type: string;
}

export interface GalleryImageModelLink {
  model_id: string;
  relation_type: "manual" | "workflow";
  is_primary: number;
  filename?: string;
  type?: ModelType;
}

export interface GalleryImage {
  id: number;
  sha256: string;
  width: number | null;
  height: number | null;
  format: string | null;
  has_comfy_metadata: number;
  prompt_text: string | null;
  workflow_json: unknown;
  metadata_json: unknown;
  created_at: string;
  updated_at: string;
  preview_url: string;
  is_primary?: number;
  sources: GalleryImageSource[];
  tags: GalleryImageTag[];
  models?: GalleryImageModelLink[];
}

export interface ImageFilterBucketItem {
  value: string;
  count: number;
}

export interface ImageFilterBuckets {
  model: ImageFilterBucketItem[];
  lora: ImageFilterBucketItem[];
  base_model: ImageFilterBucketItem[];
}

export interface GalleryImageFilters {
  model_id?: string;
  base_model?: string;
  model_ref?: string;
  lora_ref?: string;
  source_type?: "upload" | "scanned_file";
  has_metadata?: boolean;
  search?: string;
}

export interface ModelFilters {
  type?: ModelType[];
  base_model?: string[];
  tags?: string[];
  search?: string;
  sort?: "name" | "date" | "size" | "civitai_rating" | "last_used";
  sort_dir?: "asc" | "desc";
}
