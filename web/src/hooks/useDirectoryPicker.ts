import { useMutation } from "@tanstack/react-query";

interface ErrorPayload {
  error?: string;
}

export interface DirectoryPickerResponse {
  status: "selected" | "cancelled";
  path?: string;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const data = (await response.json()) as T & ErrorPayload;
  if (!response.ok) {
    throw new Error(data.error ?? "Request failed");
  }
  return data;
}

async function pickDirectory(): Promise<DirectoryPickerResponse> {
  const response = await fetch("/comfyg-models/api/fs/pick-directory", {
    method: "POST",
  });
  return parseResponse<DirectoryPickerResponse>(response);
}

export function useDirectoryPickerMutation() {
  return useMutation({
    mutationFn: pickDirectory,
  });
}
