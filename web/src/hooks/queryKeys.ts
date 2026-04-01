export const queryKeys = {
  settings: ["settings"] as const,
  models: ["models"] as const,
  modelDetail: (modelId: string) => ["models", modelId] as const,
  scanStatus: ["scan-status"] as const,
};
