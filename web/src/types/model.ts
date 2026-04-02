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
  prompts: ModelPrompt[];
  civitai_previews: ModelPreview[];
}

export interface ModelFilters {
  type?: ModelType[];
  base_model?: string[];
  tags?: string[];
  search?: string;
  sort?: "name" | "date" | "size" | "civitai_rating" | "last_used";
  sort_dir?: "asc" | "desc";
}
