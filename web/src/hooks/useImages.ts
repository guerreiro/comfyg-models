import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { GalleryImage, GalleryImageFilters, ImageFilterBuckets } from "../types/model";
import { queryKeys } from "./queryKeys";

interface ErrorPayload {
  error?: string;
}

interface ImagesResponse {
  items: GalleryImage[];
  count: number;
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
    params.set("base_model", filters.base_model);
  }
  if (filters.model_ref) {
    params.set("model_ref", filters.model_ref);
  }
  if (filters.lora_ref) {
    params.set("lora_ref", filters.lora_ref);
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
