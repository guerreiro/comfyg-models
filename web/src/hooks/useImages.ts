import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { GalleryImage, GalleryImageFilters, ImageFilterBuckets } from "../types/model";
import { queryKeys } from "./queryKeys";

interface ErrorPayload {
  error?: string;
}

interface ImagesResponse {
  items: GalleryImage[];
  count: number;
  total: number;
  page: number;
  limit: number;
}

interface RevealImageResponse {
  ok: true;
  path: string;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const data = (await response.json()) as T & ErrorPayload;
  if (!response.ok) {
    throw new Error(data.error ?? "Request failed");
  }
  return data;
}

function buildImagesUrl(filters: GalleryImageFilters): string {
  const params = new URLSearchParams();
  if (filters.model_id) {
    params.set("model_id", filters.model_id);
  }
  if (filters.base_model) {
    const baseModel = filters.base_model;
    if (Array.isArray(baseModel)) {
      baseModel.forEach((v) => params.append("base_model", v));
    } else {
      params.set("base_model", baseModel);
    }
  }
  if (filters.model_ref) {
    const modelRef = filters.model_ref;
    if (Array.isArray(modelRef)) {
      modelRef.forEach((v) => params.append("model_ref", v));
    } else {
      params.set("model_ref", modelRef);
    }
  }
  if (filters.lora_ref) {
    const loraRef = filters.lora_ref;
    if (Array.isArray(loraRef)) {
      loraRef.forEach((v) => params.append("lora_ref", v));
    } else {
      params.set("lora_ref", loraRef);
    }
  }
  if (filters.source_type) {
    params.set("source_type", filters.source_type);
  }
  if (typeof filters.has_metadata === "boolean") {
    params.set("has_metadata", String(filters.has_metadata));
  }
  if (filters.search) {
    params.set("search", filters.search);
  }
  if (filters.page) params.set("page", String(filters.page));
  if (filters.limit) params.set("limit", String(filters.limit));
  const query = params.toString();
  return `/comfyg-models/api/images${query ? `?${query}` : ""}`;
}

async function fetchImages(filters: GalleryImageFilters): Promise<ImagesResponse> {
  const response = await fetch(buildImagesUrl(filters));
  return parseResponse<ImagesResponse>(response);
}

async function fetchImageFilters(filters: GalleryImageFilters): Promise<ImageFilterBuckets> {
  const query = buildImagesUrl(filters).split("?")[1];
  const response = await fetch(`/comfyg-models/api/images/filters${query ? `?${query}` : ""}`);
  return parseResponse<ImageFilterBuckets>(response);
}

async function fetchImageDetail(imageId: number): Promise<GalleryImage> {
  const response = await fetch(`/comfyg-models/api/images/${imageId}`);
  return parseResponse<GalleryImage>(response);
}

async function uploadImageToResults(file: File): Promise<{ ok: true; image_id: number; deduplicated: boolean }> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/comfyg-models/api/images", {
    method: "POST",
    body: form,
  });
  return parseResponse<{ ok: true; image_id: number; deduplicated: boolean }>(response);
}

async function revealImage(imageId: number): Promise<RevealImageResponse> {
  const response = await fetch(`/comfyg-models/api/images/${imageId}/reveal`, {
    method: "POST",
  });
  return parseResponse<RevealImageResponse>(response);
}

export function useImagesQuery(filters: GalleryImageFilters) {
  return useQuery({
    queryKey: [...queryKeys.images, filters],
    queryFn: () => fetchImages(filters),
  });
}

export function useImageFiltersQuery(filters: GalleryImageFilters) {
  return useQuery({
    queryKey: [...queryKeys.imageFilters, filters],
    queryFn: () => fetchImageFilters(filters),
  });
}

async function fetchAllImageTags(): Promise<string[]> {
  const response = await fetch("/comfyg-models/api/images/tags");
  return parseResponse<{ tags: string[] }>(response).then((data) => data.tags);
}

export function useAllImageTagsQuery() {
  return useQuery({
    queryKey: queryKeys.allImageTags,
    queryFn: fetchAllImageTags,
  });
}

export function useImageDetailQuery(imageId: number | null) {
  return useQuery({
    queryKey: imageId ? queryKeys.imageDetail(imageId) : ["images", "detail", "idle"],
    queryFn: () => fetchImageDetail(imageId!),
    enabled: imageId !== null,
  });
}

export function useResultsImageUploadMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (file: File) => uploadImageToResults(file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.images });
      await queryClient.invalidateQueries({ queryKey: queryKeys.imageFilters });
    },
  });
}

export function useRevealImageMutation() {
  return useMutation({
    mutationFn: (imageId: number) => revealImage(imageId),
  });
}
