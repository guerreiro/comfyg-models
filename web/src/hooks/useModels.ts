import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Model, ModelDetail } from "../types/model";
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

async function fetchModels(): Promise<ModelsResponse> {
  const response = await fetch("/comfyg-models/api/models");
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

export function useModelsQuery() {
  return useQuery({
    queryKey: queryKeys.models,
    queryFn: fetchModels,
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
      if (modelId) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.modelDetail(modelId) });
      }
    },
  });
}
