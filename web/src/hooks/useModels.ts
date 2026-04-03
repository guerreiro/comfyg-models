import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Model, ModelDetail, ModelFilters } from "../types/model";
import { queryKeys } from "./queryKeys";

interface ErrorPayload {
  error?: string;
}

interface ModelsResponse {
  items: Model[];
  count: number;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const data = (await response.json()) as T & ErrorPayload;
  if (!response.ok) {
    throw new Error(data.error ?? "Request failed");
  }
  return data;
}

function buildModelsUrl(filters: ModelFilters): string {
  const params = new URLSearchParams();

  if (filters.type?.length) {
    params.set("type", filters.type.join(","));
  }
  if (filters.base_model?.length) {
    params.set("base_model", filters.base_model.join(","));
  }
  if (filters.tags?.length) {
    params.set("tags", filters.tags.join(","));
  }
  if (filters.search) {
    params.set("search", filters.search);
  }
  if (filters.sort) {
    params.set("sort", filters.sort);
  }
  if (filters.sort_dir) {
    params.set("sort_dir", filters.sort_dir);
  }

  const query = params.toString();
  return `/comfyg-models/api/models${query ? `?${query}` : ""}`;
}

async function fetchModels(filters: ModelFilters): Promise<ModelsResponse> {
  const response = await fetch(buildModelsUrl(filters));
  return parseResponse<ModelsResponse>(response);
}

async function fetchModelDetail(modelId: string): Promise<ModelDetail> {
  const response = await fetch(`/comfyg-models/api/models/${encodeURIComponent(modelId)}`);
  return parseResponse<ModelDetail>(response);
}

interface UploadModelImageInput {
  file: File;
  caption?: string;
}

async function setPrimaryModelImage(modelId: string, imageId: number): Promise<{ ok: true }> {
  const response = await fetch(
    `/comfyg-models/api/models/${encodeURIComponent(modelId)}/images/${imageId}/primary`,
    { method: "PUT" },
  );
  return parseResponse<{ ok: true }>(response);
}

async function deleteModelImage(modelId: string, imageId: number): Promise<{ ok: true }> {
  const response = await fetch(
    `/comfyg-models/api/models/${encodeURIComponent(modelId)}/images/${imageId}`,
    { method: "DELETE" },
  );
  return parseResponse<{ ok: true }>(response);
}

async function uploadModelImage(modelId: string, input: UploadModelImageInput): Promise<{ ok: true }> {
  const form = new FormData();
  form.append("file", input.file);
  if (input.caption) {
    form.append("caption", input.caption);
  }

  const response = await fetch(`/comfyg-models/api/models/${encodeURIComponent(modelId)}/images`, {
    method: "POST",
    body: form,
  });
  return parseResponse<{ ok: true }>(response);
}

export function useModelsQuery(filters: ModelFilters) {
  return useQuery({
    queryKey: [...queryKeys.models, filters],
    queryFn: () => fetchModels(filters),
  });
}

export function useModelDetailQuery(modelId: string | null) {
  return useQuery({
    queryKey: modelId ? queryKeys.modelDetail(modelId) : ["models", "detail", "idle"],
    queryFn: () => fetchModelDetail(modelId!),
    enabled: Boolean(modelId),
  });
}

export function useModelImageUploadMutation(modelId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (input: UploadModelImageInput) => uploadModelImage(modelId!, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.models });
      await queryClient.invalidateQueries({ queryKey: queryKeys.images });
      if (modelId) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.modelDetail(modelId) });
      }
    },
  });
}

export function useModelPrimaryImageMutation(modelId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (imageId: number) => setPrimaryModelImage(modelId!, imageId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.models });
      await queryClient.invalidateQueries({ queryKey: queryKeys.images });
      if (modelId) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.modelDetail(modelId) });
      }
    },
  });
}

export function useModelImageDeleteMutation(modelId: string | null) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (imageId: number) => deleteModelImage(modelId!, imageId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.models });
      await queryClient.invalidateQueries({ queryKey: queryKeys.images });
      if (modelId) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.modelDetail(modelId) });
      }
    },
  });
}
