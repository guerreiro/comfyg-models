export const queryKeys = {
  settings: ["settings"] as const,
  models: ["models"] as const,
  modelDetail: (modelId: string) => ["models", modelId] as const,
  images: ["images"] as const,
  imageFilters: ["images", "filters"] as const,
  imageDetail: (imageId: number) => ["images", imageId] as const,
  scanStatus: ["scan-status"] as const,
  scanStart: ["scan-start"] as const,
  resultsScanStatus: ["results-scan-status"] as const,
  resultsScanStart: ["results-scan-start"] as const,
};
