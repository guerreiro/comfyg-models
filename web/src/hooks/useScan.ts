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


async function stopScan(): Promise<{ stopped: boolean }> {
  const response = await fetch("/comfyg-models/api/scan/stop", {
    method: "POST",
  });
  return parseResponse<{ stopped: boolean }>(response);
}

async function startScan(filterTypes?: string[]): Promise<StartScanResponse> {
  const params = new URLSearchParams();
  if (filterTypes && filterTypes.length > 0) {
    params.set("types", filterTypes.join(","));
  }
  const queryString = params.toString();
  const url = queryString ? `/comfyg-models/api/scan?${queryString}` : "/comfyg-models/api/scan";
  
  const response = await fetch(url, {
    method: "POST",
  });
  return parseResponse<StartScanResponse>(response);
}

async function startWorker(filterTypes?: string[], syncMode: "new" | "full" | "filename" = "new"): Promise<{ status: string; filter_types?: string[], sync_mode?: string }> {
  const params = new URLSearchParams();
  if (filterTypes && filterTypes.length > 0) {
    params.set("types", filterTypes.join(","));
  }
  params.set("sync_mode", syncMode);
  
  const queryString = params.toString();
  const url = queryString ? `/comfyg-models/api/worker/start?${queryString}` : "/comfyg-models/api/worker/start";
  
  const response = await fetch(url, {
    method: "POST",
  });
  return parseResponse<{ status: string; filter_types?: string[], sync_mode?: string }>(response);
}

export function useScanStatusQuery() {
  return useQuery({
    queryKey: queryKeys.scanStatus,
    queryFn: fetchScanStatus,
    refetchInterval: (query) => {
      const data = query.state?.data;
      return data?.status === "scanning" ? 1000 : false;
    },
  });
}

export function useStartScanMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (filterTypes?: string[]) => startScan(filterTypes),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.scanStatus });
    },
  });
}

export function useStartWorkerMutation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ filterTypes, syncMode }: { filterTypes?: string[], syncMode?: "new" | "full" | "filename" } = {}) => startWorker(filterTypes, syncMode),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.scanStatus });
    },
  });
}

export function useStopScanMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: stopScan,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.scanStatus });
    },
  });
}
