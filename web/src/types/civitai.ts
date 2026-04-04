export interface CivitaiFileHashes {
  SHA256?: string;
  BLAKE3?: string;
}

export interface CivitaiModelFile {
  id: number;
  name: string;
  sizeKB?: number;
  hashes?: CivitaiFileHashes;
}

export interface CivitaiModelImageMeta {
  prompt?: string;
  negativePrompt?: string;
  sampler?: string;
  cfgScale?: number;
  steps?: number;
  seed?: number;
}

export interface CivitaiModelImage {
  id: number;
  url: string;
  nsfw?: string;
  width?: number;
  height?: number;
  meta?: CivitaiModelImageMeta;
}

export interface CivitaiModelStats {
  downloadCount?: number;
  favoriteCount?: number;
  rating?: number;
  ratingCount?: number;
}

export interface CivitaiModelVersion {
  id: number;
  name: string;
  baseModel?: string;
  trainedWords?: string[];
  files?: CivitaiModelFile[];
  images?: CivitaiModelImage[];
}

export interface CivitaiModelData {
  id: number;
  modelId?: number;
  name: string;
  type?: string;
  baseModel?: string;
  images?: CivitaiModelImage[];
  model?: {
    name?: string;
    baseModel?: string;
  };
  modelVersion?: {
    baseModel?: string;
    images?: CivitaiModelImage[];
  };
  description?: string;
  stats?: CivitaiModelStats;
  trainedWords?: string[];
  modelVersions?: CivitaiModelVersion[];
}
