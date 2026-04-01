import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "./queryKeys";

export interface ScanStatusResponse {
  status: "idle" | "scanning";
  total: number;
  done: number;
  hashing_progress: {
    total: number;
    done: number;
  };
  civitai_progress: {
    total: number;
    done: number;
  };
  error?: string;
  current_directory?: string;
  current_hash_file?: string;
  current_civitai_model?: string;
}

interface StartScanResponse {
  status: "started" | "already_running";
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

async function fetchScanStatus(): Promise<ScanStatusResponse> {
  const response = await fetch("/comfyg-models/api/scan/status");
  return parseResponse<ScanStatusResponse>(response);
}

async function startScan(): Promise<StartScanResponse> {
  const response = await fetch("/comfyg-models/api/scan", {
    method: "POST",
  });
  return parseResponse<StartScanResponse>(response);
}

export function useScanStatusQuery() {
  return useQuery({
    queryKey: queryKeys.scanStatus,
    queryFn: fetchScanStatus,
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.status === "scanning" ? 1000 : false;
    },
  });
}

export function useStartScanMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: startScan,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.scanStatus });
    },
  });
}
