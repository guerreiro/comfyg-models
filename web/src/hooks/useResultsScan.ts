import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "./queryKeys";

interface ErrorPayload {
  error?: string;
}

export interface ResultsScanStatusResponse {
  status: "idle" | "scanning";
  total: number;
  done: number;
  linked: number;
  unresolved_models: number;
  current_directory?: string;
  current_file?: string;
  error?: string;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const data = (await response.json()) as T & ErrorPayload;
  if (!response.ok) {
    throw new Error(data.error ?? "Request failed");
  }
  return data;
}

async function fetchResultsScanStatus(): Promise<ResultsScanStatusResponse> {
  const response = await fetch("/comfyg-models/api/results/scan/status");
  return parseResponse<ResultsScanStatusResponse>(response);
}


async function stopResultsScan(): Promise<{ stopped: boolean }> {
  const response = await fetch("/comfyg-models/api/results/scan/stop", {
    method: "POST",
  });
  return parseResponse<{ stopped: boolean }>(response);
}

async function startResultsScan(): Promise<{ status: "started" | "already_running" }> {
  const response = await fetch("/comfyg-models/api/results/scan", {
    method: "POST",
  });
  return parseResponse<{ status: "started" | "already_running" }>(response);
}

export function useResultsScanStatusQuery() {
  return useQuery({
    queryKey: queryKeys.resultsScanStatus,
    queryFn: fetchResultsScanStatus,
    refetchInterval: (query) => (query.state.data?.status === "scanning" ? 1000 : false),
  });
}

export function useStartResultsScanMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: startResultsScan,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.resultsScanStatus });
      await queryClient.invalidateQueries({ queryKey: queryKeys.images });
    },
  });
}

export function useStopResultsScanMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: stopResultsScan,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.resultsScanStatus });
    },
  });
}
