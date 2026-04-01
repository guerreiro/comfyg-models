import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "./queryKeys";

export interface SettingsResponse {
  civitai_api_key_configured: boolean;
  preview_cache_enabled: boolean;
}

export interface SaveSettingsInput {
  civitai_api_key?: string;
  preview_cache_enabled: boolean;
}

export interface SaveSettingsResponse {
  ok: true;
  civitai_username?: string;
  settings: SettingsResponse;
}

interface ErrorPayload {
  error?: string;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const data = (await response.json()) as T & ErrorPayload;
  if (!response.ok) {
    throw new Error(data.error ?? "Request failed");
  }
  return data;
}

async function fetchSettings(): Promise<SettingsResponse> {
  const response = await fetch("/comfyg-models/api/settings");
  return parseResponse<SettingsResponse>(response);
}

async function saveSettings(input: SaveSettingsInput): Promise<SaveSettingsResponse> {
  const response = await fetch("/comfyg-models/api/settings", {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(input),
  });

  return parseResponse<SaveSettingsResponse>(response);
}

export function useSettingsQuery() {
  return useQuery({
    queryKey: queryKeys.settings,
    queryFn: fetchSettings,
  });
}

export function useSaveSettingsMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: saveSettings,
    onSuccess: async (payload) => {
      queryClient.setQueryData(queryKeys.settings, payload.settings);
      await queryClient.invalidateQueries({ queryKey: queryKeys.settings });
    },
  });
}
