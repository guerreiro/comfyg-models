import { FormEvent, useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Eye,
  EyeOff,
  Filter,
  FolderOpen,
  GalleryHorizontal,
  Grip,
  ImagePlus,
  Images,
  Link2,
  ScanSearch,
  Search,
  Settings2,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";
import { useDirectoryPickerMutation } from "./hooks/useDirectoryPicker";
import {
  useModelDetailQuery,
  useModelImageDeleteMutation,
  useModelImageUploadMutation,
  useModelPrimaryImageMutation,
  useModelsQuery,
} from "./hooks/useModels";
import {
  useImageDetailQuery,
  useImagesQuery,
  useResultsImageUploadMutation,
  useRevealImageMutation,
} from "./hooks/useImages";
import { useResultsScanStatusQuery, useStartResultsScanMutation } from "./hooks/useResultsScan";
import { useScanStatusQuery, useStartScanMutation } from "./hooks/useScan";
import { useSaveSettingsMutation, useSettingsQuery } from "./hooks/useSettings";
import type { CivitaiModelImage } from "./types/civitai";
import type { GalleryImageFilters, Model, ModelFilters } from "./types/model";

type ModalView = "none" | "scan-models" | "scan-results" | "settings" | "model" | "image";
type ModelModalTab = "gallery" | "overview" | "civitai";
type PrimaryView = "library" | "results";

function getCivitaiUrl(model: Model): string | null {
  if (model.civitai_model_id === null || model.civitai_model_id === -1) {
    return null;
  }

  return `https://civitai.com/models/${model.civitai_model_id}${
    model.civitai_version_id ? `?modelVersionId=${model.civitai_version_id}` : ""
  }`;
}

function isImageSafe(image: CivitaiModelImage): boolean {
  const flag = (image.nsfw ?? "").toLowerCase();
  return flag === "" || flag === "none";
}

function getModelPreview(model: Model, showNsfwPreviews: boolean): { kind: "user" | "civitai"; url: string } | null {
  if (model.primary_user_image) {
    return {
      kind: "user",
      url: `/comfyg-models/api/user-images/${model.primary_user_image}`,
    };
  }

  const images = model.civitai_data?.images ?? model.civitai_data?.modelVersion?.images ?? [];
  const selected = showNsfwPreviews ? images[0] : images.find(isImageSafe);
  if (!selected?.url) {
    return null;
  }

  return {
    kind: "civitai",
    url: selected.url,
  };
}

function formatFileSize(size: number | null): string {
  if (size === null) {
    return "-";
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function getBaseModel(model: Model): string | null {
  return (
    model.civitai_data?.baseModel ??
    model.civitai_data?.model?.baseModel ??
    model.civitai_data?.modelVersion?.baseModel ??
    null
  );
}

function addUniquePath(paths: string[], value: string): string[] {
  const normalized = value.trim();
  if (!normalized) {
    return paths;
  }
  return Array.from(new Set([...paths, normalized]));
}

export default function App() {
  const settingsQuery = useSettingsQuery();
  const saveSettings = useSaveSettingsMutation();
  const scanStatusQuery = useScanStatusQuery();
  const startScan = useStartScanMutation();
  const resultsScanStatusQuery = useResultsScanStatusQuery();
  const startResultsScan = useStartResultsScanMutation();
  const directoryPicker = useDirectoryPickerMutation();

  const [primaryView, setPrimaryView] = useState<PrimaryView>("library");
  const [modalView, setModalView] = useState<ModalView>("none");
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [selectedImageId, setSelectedImageId] = useState<number | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [previewCacheEnabled, setPreviewCacheEnabled] = useState(true);
  const [showNsfwPreviews, setShowNsfwPreviews] = useState(false);
  const [generatedImageScanPaths, setGeneratedImageScanPaths] = useState<string[]>([]);
  const [newGeneratedPath, setNewGeneratedPath] = useState("");
  const [uploadCaption, setUploadCaption] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [baseModelFilter, setBaseModelFilter] = useState<string>("all");
  const [sort, setSort] = useState<ModelFilters["sort"]>("name");
  const [sortDir, setSortDir] = useState<ModelFilters["sort_dir"]>("asc");
  const [modelModalTab, setModelModalTab] = useState<ModelModalTab>("gallery");
  const [showUploadForm, setShowUploadForm] = useState(false);
  const [imagePendingDelete, setImagePendingDelete] = useState<number | null>(null);
  const [resultsSearch, setResultsSearch] = useState("");
  const [scanPathsSavedAt, setScanPathsSavedAt] = useState<number | null>(null);
  const [resultsDropActive, setResultsDropActive] = useState(false);
  const [resultsUploadNotice, setResultsUploadNotice] = useState<string | null>(null);
  const [showImageMetadata, setShowImageMetadata] = useState(false);
  const [imagePreviewFailed, setImagePreviewFailed] = useState(false);
  const [modelPage, setModelPage] = useState(1);
  const [modelLimit, setModelLimit] = useState(50);
  const [imagePage, setImagePage] = useState(1);
  const [imageLimit, setImageLimit] = useState(50);
  const deferredSearch = useDeferredValue(search);
  const deferredResultsSearch = useDeferredValue(resultsSearch);
  const queryFilters = useMemo<ModelFilters>(
    () => ({
      search: deferredSearch.trim() || undefined,
      type: typeFilter === "all" ? undefined : [typeFilter as Model["type"]],
      base_model: baseModelFilter === "all" ? undefined : [baseModelFilter],
      sort,
      sort_dir: sortDir,
      page: modelPage,
      limit: modelLimit,
    }),
    [deferredSearch, typeFilter, baseModelFilter, sort, sortDir, modelPage, modelLimit],
  );
  const modelsQuery = useModelsQuery(queryFilters);
  const imageFilters = useMemo<GalleryImageFilters>(
    () => ({
      search: deferredResultsSearch.trim() || undefined,
      page: imagePage,
      limit: imageLimit,
    }),
    [deferredResultsSearch, imagePage, imageLimit],
  );
  const imagesQuery = useImagesQuery(imageFilters);

  const selectedModel =
    modelsQuery.data?.items.find((item) => item.id === selectedModelId) ?? null;
  const modelDetailQuery = useModelDetailQuery(selectedModelId);
  const imageDetailQuery = useImageDetailQuery(selectedImageId);
  const imageUpload = useModelImageUploadMutation(selectedModelId);
  const primaryImageMutation = useModelPrimaryImageMutation(selectedModelId);
  const deleteImageMutation = useModelImageDeleteMutation(selectedModelId);
  const resultsImageUpload = useResultsImageUploadMutation();
  const revealImage = useRevealImageMutation();

  useEffect(() => {
    if (!settingsQuery.data) {
      return;
    }

    setPreviewCacheEnabled(settingsQuery.data.preview_cache_enabled);
    setShowNsfwPreviews(settingsQuery.data.show_nsfw_previews);
    setGeneratedImageScanPaths(settingsQuery.data.generated_image_scan_paths ?? []);
  }, [settingsQuery.data]);

  useEffect(() => {
    if (scanPathsSavedAt === null) {
      return;
    }
    const timer = window.setTimeout(() => setScanPathsSavedAt(null), 2400);
    return () => window.clearTimeout(timer);
  }, [scanPathsSavedAt]);

  useEffect(() => {
    if (!resultsUploadNotice) {
      return;
    }
    const timer = window.setTimeout(() => setResultsUploadNotice(null), 3000);
    return () => window.clearTimeout(timer);
  }, [resultsUploadNotice]);

  useEffect(() => {
    setShowImageMetadata(false);
    setImagePreviewFailed(false);
  }, [selectedImageId]);

  const allModelsQuery = useModelsQuery({ sort: "name", sort_dir: "asc" });
  const allModels = allModelsQuery.data?.items ?? [];
  const filteredModels = modelsQuery.data?.items ?? [];
  const availableTypes = Array.from(new Set(allModels.map((model) => model.type))).sort();
  const availableBaseModels = Array.from(
    new Set(allModels.map((model) => getBaseModel(model)).filter((value): value is string => Boolean(value))),
  ).sort((a, b) => a.localeCompare(b));

  const persistGeneratedScanPaths = async (paths: string[]) => {
    setScanPathsSavedAt(null);
    setGeneratedImageScanPaths(paths);
    await saveSettings.mutateAsync({
      preview_cache_enabled: settingsQuery.data?.preview_cache_enabled ?? previewCacheEnabled,
      show_nsfw_previews: settingsQuery.data?.show_nsfw_previews ?? showNsfwPreviews,
      generated_image_scan_paths: paths,
    });
    setScanPathsSavedAt(Date.now());
  };

  const handleSettingsSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    await saveSettings.mutateAsync({
      ...(apiKey.trim() ? { civitai_api_key: apiKey.trim() } : {}),
      preview_cache_enabled: previewCacheEnabled,
      show_nsfw_previews: showNsfwPreviews,
      generated_image_scan_paths: generatedImageScanPaths,
    });

    setApiKey("");
  };

  const handleUploadSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!uploadFile) {
      return;
    }

    await imageUpload.mutateAsync({
      file: uploadFile,
      caption: uploadCaption,
    });

    setUploadCaption("");
    setUploadFile(null);
  };

  const username = saveSettings.data?.civitai_username;
  const configured = settingsQuery.data?.civitai_api_key_configured ?? false;
  const scanStatus = scanStatusQuery.data;
  const resultsScanStatus = resultsScanStatusQuery.data;
  const scanProgress =
    scanStatus && scanStatus.total > 0 ? Math.round((scanStatus.done / scanStatus.total) * 100) : 0;
  const hashingProgress =
    scanStatus && scanStatus.hashing_progress.total > 0
      ? Math.round((scanStatus.hashing_progress.done / scanStatus.hashing_progress.total) * 100)
      : 0;
  const civitaiProgress =
    scanStatus && scanStatus.civitai_progress.total > 0
      ? Math.round((scanStatus.civitai_progress.done / scanStatus.civitai_progress.total) * 100)
      : 0;
  const resultsScanProgress =
    resultsScanStatus && resultsScanStatus.total > 0
      ? Math.round((resultsScanStatus.done / resultsScanStatus.total) * 100)
      : 0;

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(236,122,49,0.10),_transparent_24%),radial-gradient(circle_at_85%_10%,_rgba(56,189,149,0.08),_transparent_22%),linear-gradient(180deg,_#09090b_0%,_#111215_42%,_#17181d_100%)] text-stone-100">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-5 py-6 lg:px-8">
        <header className="flex flex-col gap-5 rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-[0_24px_80px_rgba(0,0,0,0.28)] backdrop-blur">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-4">
              <h1 className="text-4xl font-semibold tracking-tight text-white md:text-5xl">Comfyg Models</h1>
              <div className="flex flex-wrap gap-2">
                {[
                  { id: "library", label: "Library", icon: Sparkles },
                  { id: "results", label: "Results", icon: Images },
                ].map((item) => {
                  const Icon = item.icon;
                  const isActive = primaryView === item.id;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setPrimaryView(item.id as PrimaryView)}
                      className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition ${
                        isActive
                          ? "bg-white text-stone-950"
                          : "border border-white/10 bg-white/8 text-stone-200 hover:bg-white/12"
                      }`}
                    >
                      <Icon className="h-4 w-4" />
                      {item.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => setModalView("scan-models")}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/8 px-4 py-2 text-sm font-semibold text-stone-200 transition hover:bg-white/12"
              >
                <ScanSearch className="h-4 w-4" />
                Scan Models
              </button>
              <button
                type="button"
                onClick={() => setModalView("scan-results")}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/8 px-4 py-2 text-sm font-semibold text-stone-200 transition hover:bg-white/12"
              >
                <Images className="h-4 w-4" />
                Scan Results
              </button>
              <button
                type="button"
                onClick={() => setModalView("settings")}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/8 px-4 py-2 text-sm font-semibold text-stone-200 transition hover:bg-white/12"
              >
                <Settings2 className="h-4 w-4" />
                Settings
              </button>
            </div>
          </div>

          {primaryView === "library" ? (
            <section className="grid gap-4 lg:grid-cols-[1.25fr_0.8fr_0.8fr]">
              <label className="flex items-center gap-3 rounded-[1.4rem] border border-white/10 bg-black/20 px-4 py-3">
                <Search className="h-4 w-4 text-stone-500" />
                <input
                  type="text"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search by filename, CivitAI title or base model"
                  className="w-full bg-transparent text-sm text-white outline-none placeholder:text-stone-500"
                />
              </label>

              <label className="flex items-center gap-3 rounded-[1.4rem] border border-white/10 bg-black/20 px-4 py-3">
                <Filter className="h-4 w-4 text-stone-500" />
                <select
                  value={typeFilter}
                  onChange={(event) => setTypeFilter(event.target.value)}
                  className="w-full appearance-none bg-transparent text-sm text-white outline-none"
                >
                  <option value="all" className="bg-stone-950">
                    All model types
                  </option>
                  {availableTypes.map((type) => (
                    <option key={type} value={type} className="bg-stone-950">
                      {type}
                    </option>
                  ))}
                </select>
              </label>

              <label className="flex items-center gap-3 rounded-[1.4rem] border border-white/10 bg-black/20 px-4 py-3">
                <Sparkles className="h-4 w-4 text-stone-500" />
                <select
                  value={sort}
                  onChange={(event) => setSort(event.target.value as NonNullable<ModelFilters["sort"]>)}
                  className="w-full appearance-none bg-transparent text-sm text-white outline-none"
                >
                  <option value="name" className="bg-stone-950">
                    Sort by name
                  </option>
                  <option value="size" className="bg-stone-950">
                    Sort by size
                  </option>
                  <option value="date" className="bg-stone-950">
                    Sort by date
                  </option>
                  <option value="civitai_rating" className="bg-stone-950">
                    Sort by CivitAI rating
                  </option>
                </select>
                <button
                  type="button"
                  onClick={() => setSortDir((current) => (current === "asc" ? "desc" : "asc"))}
                  className="rounded-full border border-white/10 px-3 py-1 text-xs font-semibold text-stone-300 transition hover:bg-white/10"
                >
                  {sortDir === "asc" ? "ASC" : "DESC"}
                </button>
              </label>
            </section>
          ) : null}

          {primaryView === "results" ? (
            <label className="flex items-center gap-3 rounded-[1.4rem] border border-white/10 bg-black/20 px-4 py-3">
              <Search className="h-4 w-4 text-stone-500" />
              <input
                type="text"
                value={resultsSearch}
                onChange={(event) => setResultsSearch(event.target.value)}
                placeholder="Search by prompt, filename or tags..."
                className="w-full bg-transparent text-sm text-white outline-none placeholder:text-stone-500"
              />
            </label>
          ) : null}
        </header>

        {primaryView === "library" ? (
        <section className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setBaseModelFilter("all")}
            className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
              baseModelFilter === "all"
                ? "bg-white text-stone-950"
                : "border border-white/10 bg-white/5 text-stone-300 hover:bg-white/10"
            }`}
          >
            All base models
          </button>
          {availableBaseModels.map((baseModel) => (
            <button
              key={baseModel}
              type="button"
              onClick={() => setBaseModelFilter(baseModel)}
              className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                baseModelFilter === baseModel
                  ? "bg-emerald-300 text-stone-950"
                  : "border border-white/10 bg-white/5 text-stone-300 hover:bg-white/10"
              }`}
            >
              {baseModel}
            </button>
          ))}
        </section>
        ) : null}

        {primaryView === "library" ? (
        <section className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {modelsQuery.isLoading ? (
            <div className="col-span-full rounded-[1.8rem] border border-white/10 bg-white/5 p-8 text-sm text-stone-400">
              Loading models...
            </div>
          ) : null}

          {modelsQuery.isError ? (
            <div className="col-span-full rounded-[1.8rem] border border-rose-500/20 bg-rose-500/10 p-8 text-sm text-rose-200">
              {modelsQuery.error.message}
            </div>
          ) : null}

          {!modelsQuery.isLoading && filteredModels.length === 0 ? (
            <div className="col-span-full rounded-[1.8rem] border border-white/10 bg-white/5 p-8 text-sm text-stone-400">
              No models matched the current filters.
            </div>
          ) : null}

          {filteredModels.map((model) => {
            const preview = getModelPreview(model, showNsfwPreviews);
            const baseModel = getBaseModel(model);

            return (
              <button
                key={model.id}
                type="button"
                onClick={() => {
                  setSelectedModelId(model.id);
                  setModelModalTab("gallery");
                  setShowUploadForm(false);
                  setImagePendingDelete(null);
                  setModalView("model");
                }}
                className="group overflow-hidden rounded-[1.7rem] border border-white/10 bg-white/5 text-left shadow-[0_18px_50px_rgba(0,0,0,0.20)] transition hover:-translate-y-1 hover:border-white/20 hover:bg-white/[0.08]"
              >
                <div className="relative aspect-[4/3] overflow-hidden bg-[linear-gradient(135deg,_#1c1d22,_#282a31_50%,_#1b1c20)]">
                  {preview ? (
                    <img
                      src={preview.url}
                      alt={model.filename}
                      className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center px-6 text-center text-sm text-stone-500">
                      No preview available
                    </div>
                  )}

                  <div className="absolute inset-x-0 bottom-0 bg-[linear-gradient(180deg,_transparent,_rgba(0,0,0,0.82))] p-4">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <h2 className="truncate text-base font-semibold text-white">{model.filename}</h2>
                        <p className="mt-1 truncate text-xs uppercase tracking-[0.18em] text-stone-300">{model.type}</p>
                      </div>
                      {preview?.kind === "user" ? (
                        <span className="rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-200">
                          custom thumb
                        </span>
                      ) : null}
                    </div>
                  </div>
                </div>

                <div className="space-y-3 p-4">
                  <div className="flex items-center justify-between gap-3 text-sm text-stone-400">
                    <span className="truncate">{baseModel ?? "Local only"}</span>
                    <span>{model.civitai_data?.stats?.rating ? `${model.civitai_data.stats.rating.toFixed(1)}★` : formatFileSize(model.file_size)}</span>
                  </div>
                </div>
              </button>
            );
          })}

          {modelsQuery.data && modelsQuery.data.total > 0 ? (
            <div className="col-span-full mt-6 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-white/10 bg-black/20 p-4">
              <span className="text-sm text-stone-400">
                Showing {Math.min(filteredModels.length, modelLimit)} of {modelsQuery.data.total} models
              </span>
              <div className="flex items-center gap-2">
                 <button disabled={modelPage <= 1} onClick={() => setModelPage(p => p - 1)} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-stone-300 hover:bg-white/10 disabled:opacity-50">Prev</button>
                 <span className="text-sm text-stone-400">Page {modelPage}</span>
                 <button disabled={filteredModels.length < modelLimit} onClick={() => setModelPage(p => p + 1)} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-stone-300 hover:bg-white/10 disabled:opacity-50">Next</button>
              </div>
              <select value={modelLimit} onChange={(e) => { setModelLimit(Number(e.target.value)); setModelPage(1); }} className="rounded-full border border-white/10 bg-transparent px-3 py-1 text-sm text-white">
                <option value={20} className="bg-stone-900">20 per page</option>
                <option value={50} className="bg-stone-900">50 per page</option>
                <option value={100} className="bg-stone-900">100 per page</option>
              </select>
            </div>
          ) : null}

        </section>
        ) : (
        <section
          className="relative rounded-[1.8rem]"
          onDragOver={(event) => {
            event.preventDefault();
            setResultsDropActive(true);
          }}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
              setResultsDropActive(false);
            }
          }}
          onDrop={async (event) => {
            event.preventDefault();
            setResultsDropActive(false);
            const files = Array.from(event.dataTransfer.files).filter((file) => file.type.startsWith("image/"));
            if (files.length === 0) {
              return;
            }
            setResultsUploadNotice(null);
            let imported = 0;
            for (const file of files) {
              await resultsImageUpload.mutateAsync(file);
              imported += 1;
            }
            setResultsUploadNotice(
              imported === 1 ? "1 image added to Results." : `${imported} images added to Results.`,
            );
          }}
        >
          {resultsDropActive ? (
            <div className="absolute inset-0 z-20 flex items-center justify-center rounded-[1.8rem] border border-dashed border-emerald-300/50 bg-emerald-300/10 backdrop-blur-sm">
              <div className="rounded-[1.4rem] border border-emerald-300/30 bg-black/55 px-6 py-5 text-center">
                <p className="text-sm font-semibold text-emerald-100">Drop images to add them to Results</p>
                <p className="mt-1 text-xs text-emerald-200/80">PNG metadata will be indexed automatically when available.</p>
              </div>
            </div>
          ) : null}

          {resultsUploadNotice ? (
            <div className="mb-5 rounded-[1.3rem] border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
              {resultsUploadNotice}
            </div>
          ) : null}

          {resultsImageUpload.isError ? (
            <div className="mb-5 rounded-[1.3rem] border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
              {resultsImageUpload.error.message}
            </div>
          ) : null}

          <div className="columns-1 gap-5 sm:columns-2 xl:columns-3 2xl:columns-4">
            {imagesQuery.isLoading ? (
              <div className="mb-5 break-inside-avoid rounded-[1.8rem] border border-white/10 bg-white/5 p-8 text-sm text-stone-400">
                Loading images...
              </div>
            ) : null}
            {imagesQuery.isError ? (
              <div className="mb-5 break-inside-avoid rounded-[1.8rem] border border-rose-500/20 bg-rose-500/10 p-8 text-sm text-rose-200">
                {imagesQuery.error.message}
              </div>
            ) : null}
            {!imagesQuery.isLoading && (imagesQuery.data?.items.length ?? 0) === 0 ? (
              <div className="mb-5 break-inside-avoid rounded-[1.8rem] border border-white/10 bg-white/5 p-8 text-sm text-stone-400">
                No images matched the current filters.
              </div>
            ) : null}
            {(imagesQuery.data?.items ?? []).map((image) => (
              <button
                key={image.id}
                type="button"
                onClick={() => {
                  setSelectedImageId(image.id);
                  setModalView("image");
                }}
                className="group mb-5 block w-full break-inside-avoid overflow-hidden rounded-[1.7rem] border border-white/10 bg-white/5 text-left shadow-[0_18px_50px_rgba(0,0,0,0.20)] transition hover:-translate-y-1 hover:border-white/20 hover:bg-white/[0.08]"
              >
                <div className="relative overflow-hidden bg-[linear-gradient(135deg,_#1c1d22,_#282a31_50%,_#1b1c20)]">
                  <img src={`${image.preview_url}?_t=${image.updated_at}`} alt={image.sha256} className="h-auto w-full transition duration-500 group-hover:scale-[1.01]" />
                  <div className="absolute left-3 top-3 flex gap-2">
                    {(image.sources ?? []).slice(0, 2).map((source) => (
                      <span key={source.id} className="rounded-full border border-white/10 bg-black/55 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-white backdrop-blur">
                        {source.source_type === "upload" ? "Upload" : "Generated"}
                      </span>
                    ))}
                  </div>
                </div>
              </button>
            ))}
          </div>

            {imagesQuery.data && imagesQuery.data.total > 0 ? (
              <div className="mt-8 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-white/10 bg-black/20 p-4 break-inside-avoid">
                <span className="text-sm text-stone-400">
                  Showing {Math.min(imagesQuery.data.items.length, imageLimit)} of {imagesQuery.data.total} images
                </span>
                <div className="flex items-center gap-2">
                   <button disabled={imagePage <= 1} onClick={() => setImagePage(p => p - 1)} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-stone-300 hover:bg-white/10 disabled:opacity-50">Prev</button>
                   <span className="text-sm text-stone-400">Page {imagePage}</span>
                   <button disabled={imagesQuery.data.items.length < imageLimit} onClick={() => setImagePage(p => p + 1)} className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-stone-300 hover:bg-white/10 disabled:opacity-50">Next</button>
                </div>
                <select value={imageLimit} onChange={(e) => { setImageLimit(Number(e.target.value)); setImagePage(1); }} className="rounded-full border border-white/10 bg-transparent px-3 py-1 text-sm text-white">
                  <option value={20} className="bg-stone-900">20 per page</option>
                  <option value={50} className="bg-stone-900">50 per page</option>
                  <option value={100} className="bg-stone-900">100 per page</option>
                </select>
              </div>
            ) : null}
        </section>
        )}
      </div>

      {modalView !== "none" ? (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-10 backdrop-blur-sm">
          <div className="w-full max-w-5xl rounded-[2rem] border border-white/10 bg-[#101114] shadow-[0_30px_100px_rgba(0,0,0,0.45)]">
            <div className="flex items-center justify-between border-b border-white/10 px-6 py-5">
              {modalView === "model" && selectedModel ? (
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-300">
                      {selectedModel.type}
                    </span>
                    {getBaseModel(selectedModel) ? (
                      <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-200">
                        {getBaseModel(selectedModel)}
                      </span>
                    ) : null}
                  </div>
                  <h2 className="mt-3 truncate text-xl font-semibold text-white">
                    {selectedModel.civitai_data?.name ?? selectedModel.filename}
                  </h2>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-stone-400">
                    <span className="truncate">{selectedModel.filename}</span>
                    {getCivitaiUrl(selectedModel) ? (
                      <a
                        href={getCivitaiUrl(selectedModel)!}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-stone-200 underline decoration-stone-600 underline-offset-4 transition hover:text-white"
                      >
                        <Link2 className="h-3.5 w-3.5" />
                        CivitAI
                      </a>
                    ) : null}
                  </div>
                </div>
              ) : modalView === "image" && imageDetailQuery.data ? (
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    {(imageDetailQuery.data.sources ?? []).slice(0, 2).map((source) => (
                      <span
                        key={source.id}
                        className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-300"
                      >
                        {source.source_type === "upload" ? "Upload" : "Generated"}
                      </span>
                    ))}
                  </div>
                  <h2 className="mt-3 truncate text-xl font-semibold text-white">Image #{imageDetailQuery.data.id}</h2>
                  <div className="mt-1 text-sm text-stone-400">
                    {imageDetailQuery.data.sources?.[0]?.filename ?? imageDetailQuery.data.sha256}
                  </div>
                </div>
              ) : (
                <div>
                  <h2 className="text-xl font-semibold text-white">
                    {modalView === "scan-models"
                      ? "Scan Models"
                      : modalView === "scan-results"
                        ? "Scan Results"
                        : "Settings"}
                  </h2>
                  <p className="mt-1 text-sm text-stone-400">
                    {modalView === "scan-models"
                      ? "Run and monitor the local model scan pipeline."
                      : modalView === "scan-results"
                        ? "Scan configured folders for generated PNG images with ComfyUI metadata."
                        : "Plugin preferences and preview safety."}
                  </p>
                </div>
              )}
              <button
                type="button"
                onClick={() => {
                  setModalView("none");
                  setImagePendingDelete(null);
                }}
                className="rounded-full border border-white/10 bg-white/5 p-2 text-stone-300 transition hover:bg-white/10"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {modalView === "scan-models" ? (
              <div className="space-y-4 p-6">
                <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-white">Model library scan</p>
                      <p className="mt-1 text-sm text-stone-400">
                        Re-scan only when you add, remove or rename model files.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => startScan.mutate()}
                      disabled={startScan.isPending || scanStatus?.status === "scanning"}
                      className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-stone-950 transition hover:bg-stone-200 disabled:cursor-not-allowed disabled:bg-stone-500"
                    >
                      <ScanSearch className="h-4 w-4" />
                      {scanStatus?.status === "scanning" ? "Scanning..." : "Run scan"}
                    </button>
                  </div>
                </div>

                {[
                  {
                    title: "Directory scan",
                    progress: scanProgress,
                    label:
                      scanStatus?.status === "scanning"
                        ? `${scanStatus.done} of ${scanStatus.total || "?"}`
                        : "Idle",
                  },
                  {
                    title: "Hashing",
                    progress: hashingProgress,
                    label: scanStatus?.hashing_progress.total
                      ? `${scanStatus.hashing_progress.done} of ${scanStatus.hashing_progress.total}`
                      : "No pending hashes",
                  },
                  {
                    title: "CivitAI sync",
                    progress: civitaiProgress,
                    label: scanStatus?.civitai_progress.total
                      ? `${scanStatus.civitai_progress.done} of ${scanStatus.civitai_progress.total}`
                      : "No pending sync",
                  },
                ].map((item) => (
                  <div key={item.title} className="rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                    <div className="flex items-center justify-between text-sm text-stone-300">
                      <span className="font-semibold text-white">{item.title}</span>
                      <span>{item.label}</span>
                    </div>
                    <div className="mt-3 h-3 overflow-hidden rounded-full bg-white/10">
                      <div className="h-full rounded-full bg-white transition-all" style={{ width: `${item.progress}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            {modalView === "scan-results" ? (
              <div className="space-y-5 p-6">
                <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-white">Generated image scan</p>
                      <p className="mt-1 text-sm text-stone-400">
                        Scan configured folders for generated PNG images with ComfyUI metadata.
                      </p>
                    </div>
                      <button
                        type="button"
                        onClick={() => startResultsScan.mutate()}
                        disabled={startResultsScan.isPending || saveSettings.isPending || resultsScanStatus?.status === "scanning"}
                        className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-stone-950 transition hover:bg-stone-200 disabled:cursor-not-allowed disabled:bg-stone-500"
                      >
                        <Images className="h-4 w-4" />
                      {resultsScanStatus?.status === "scanning" ? "Scanning..." : "Run scan"}
                    </button>
                  </div>
                </div>

                <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                  <div className="flex items-center justify-between text-sm text-stone-300">
                    <span className="font-semibold text-white">Results scan progress</span>
                    <span>{resultsScanStatus?.status === "scanning" ? `${resultsScanStatus.done} of ${resultsScanStatus.total || "?"}` : "Idle"}</span>
                  </div>
                  <div className="mt-3 h-3 overflow-hidden rounded-full bg-white/10">
                    <div className="h-full rounded-full bg-emerald-300 transition-all" style={{ width: `${resultsScanProgress}%` }} />
                  </div>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-stone-400">
                    <span>{resultsScanStatus ? `${resultsScanStatus.linked} linked` : "0 linked"}</span>
                    <span>{resultsScanStatus ? `${resultsScanStatus.unresolved_models} unresolved` : "0 unresolved"}</span>
                    {resultsScanStatus?.current_file ? <span className="truncate">{resultsScanStatus.current_file}</span> : null}
                  </div>
                </div>

                <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                  <div>
                    <span className="block text-sm font-medium text-stone-100">Generated image scan paths</span>
                    <span className="mt-1 block text-xs text-stone-400">
                      Absolute folders scanned by the Results library.
                    </span>
                  </div>
                  <div className="mt-4 flex gap-3">
                      <input
                        type="text"
                        value={newGeneratedPath}
                        onChange={(event) => {
                          setScanPathsSavedAt(null);
                          setNewGeneratedPath(event.target.value);
                        }}
                        placeholder="/absolute/path/to/outputs"
                        className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-white/25"
                      />
                      <button
                        type="button"
                        onClick={async () => {
                          const result = await directoryPicker.mutateAsync();
                          if (result.status === "selected" && result.path) {
                            const nextPaths = addUniquePath(generatedImageScanPaths, result.path);
                            await persistGeneratedScanPaths(nextPaths);
                            setNewGeneratedPath("");
                          }
                        }}
                        disabled={directoryPicker.isPending || saveSettings.isPending}
                        className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-stone-200 transition hover:bg-white/10"
                      >
                        {directoryPicker.isPending ? "Selecting..." : "Select folder"}
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          const value = newGeneratedPath.trim();
                          if (!value) {
                            return;
                          }
                          const nextPaths = addUniquePath(generatedImageScanPaths, value);
                          await persistGeneratedScanPaths(nextPaths);
                          setNewGeneratedPath("");
                        }}
                        disabled={saveSettings.isPending}
                        className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-stone-200 transition hover:bg-white/10"
                      >
                      Add
                    </button>
                  </div>
                  <div className="mt-4 flex flex-col gap-2">
                    {generatedImageScanPaths.length === 0 ? (
                      <p className="text-sm text-stone-500">No results scan paths configured.</p>
                    ) : (
                      generatedImageScanPaths.map((pathValue) => (
                        <div key={pathValue} className="flex items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-stone-200">
                          <span className="truncate">{pathValue}</span>
                          <button
                            type="button"
                            onClick={async () => {
                              const nextPaths = generatedImageScanPaths.filter((item) => item !== pathValue);
                              await persistGeneratedScanPaths(nextPaths);
                            }}
                            disabled={saveSettings.isPending}
                            className="rounded-full border border-white/10 bg-black/20 px-3 py-1 text-xs font-semibold text-stone-300 transition hover:bg-white/10"
                          >
                            Remove
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                  {directoryPicker.isError ? (
                    <p className="mt-4 rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                      {directoryPicker.error.message}
                    </p>
                  ) : null}
                  {saveSettings.isPending ? (
                    <p className="mt-4 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-stone-300">
                      Saving scan paths...
                    </p>
                  ) : null}
                  {saveSettings.isError ? (
                    <p className="mt-4 rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                      {saveSettings.error.message}
                    </p>
                  ) : null}
                  {!saveSettings.isPending && !saveSettings.isError && scanPathsSavedAt !== null ? (
                    <p className="mt-4 rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
                      Scan paths saved.
                    </p>
                  ) : null}
                </div>
              </div>
            ) : null}

            {modalView === "settings" ? (
              <form onSubmit={handleSettingsSubmit} className="space-y-5 p-6">
                <div className="grid gap-5 lg:grid-cols-2">
                  <div className="space-y-5 rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                    <label className="block space-y-2">
                      <span className="text-sm font-medium text-stone-200">CivitAI API key</span>
                      <input
                        type="password"
                        autoComplete="off"
                        value={apiKey}
                        onChange={(event) => setApiKey(event.target.value)}
                        placeholder={configured ? "Configured. Enter a new key to replace it." : "Enter your API key"}
                        className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-white/25"
                      />
                    </label>

                    <label className="flex items-center justify-between gap-4 rounded-2xl border border-white/10 bg-black/20 px-4 py-4">
                      <div>
                        <span className="block text-sm font-medium text-stone-100">Local preview cache</span>
                        <span className="mt-1 block text-xs text-stone-400">Store downloaded previews in the user folder.</span>
                      </div>
                      <input
                        type="checkbox"
                        checked={previewCacheEnabled}
                        onChange={(event) => setPreviewCacheEnabled(event.target.checked)}
                        className="h-5 w-5 rounded border-stone-500 bg-transparent text-white focus:ring-white"
                      />
                    </label>
                  </div>

                  <div className="space-y-5 rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                    <label className="flex items-center justify-between gap-4 rounded-2xl border border-white/10 bg-black/20 px-4 py-4">
                      <div>
                        <span className="flex items-center gap-2 text-sm font-medium text-stone-100">
                          {showNsfwPreviews ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                          Allow NSFW CivitAI previews
                        </span>
                        <span className="mt-1 block text-xs text-stone-400">
                          Disabled by default so the library opens in safe mode.
                        </span>
                      </div>
                      <input
                        type="checkbox"
                        checked={showNsfwPreviews}
                        onChange={(event) => setShowNsfwPreviews(event.target.checked)}
                        className="h-5 w-5 rounded border-stone-500 bg-transparent text-white focus:ring-white"
                      />
                    </label>
                  </div>
                </div>

                {saveSettings.isError ? (
                  <p className="rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                    {saveSettings.error.message}
                  </p>
                ) : null}

                {saveSettings.isSuccess ? (
                  <p className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
                    Settings saved successfully{username ? ` for ${username}` : ""}.
                  </p>
                ) : null}

                <div className="flex items-center gap-3">
                  <button
                    type="submit"
                    disabled={saveSettings.isPending}
                    className="inline-flex items-center justify-center rounded-full bg-white px-5 py-3 text-sm font-semibold text-stone-950 transition hover:bg-stone-200 disabled:cursor-not-allowed disabled:bg-stone-500"
                  >
                    {saveSettings.isPending ? "Saving..." : "Save settings"}
                  </button>
                  <a
                    href="https://civitai.com/user/account"
                    target="_blank"
                    rel="noreferrer"
                    className="text-sm font-medium text-stone-300 underline decoration-stone-600 underline-offset-4 transition hover:text-white"
                  >
                    Open CivitAI account
                  </a>
                </div>
              </form>
            ) : null}

            {modalView === "model" && selectedModel ? (
              <div className="space-y-6 p-6">
                <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div className="flex flex-wrap gap-2">
                      {selectedModel.civitai_data?.stats?.rating ? (
                        <span className="inline-flex rounded-full border border-amber-300/20 bg-amber-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-amber-100">
                          {selectedModel.civitai_data.stats.rating.toFixed(1)} rating
                        </span>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        type="button"
                        onClick={() => setShowUploadForm((current) => !current)}
                        className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-stone-200 transition hover:bg-white/10"
                      >
                        {showUploadForm ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                        {showUploadForm ? "Hide uploader" : "Add images"}
                      </button>
                    </div>
                  </div>

                  {showUploadForm ? (
                    <form onSubmit={handleUploadSubmit} className="mt-5 space-y-4 rounded-[1.2rem] border border-white/10 bg-black/20 p-4">
                      <div className="flex items-center gap-2 text-sm font-semibold text-white">
                        <ImagePlus className="h-4 w-4" />
                        Add images to your gallery
                      </div>
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                        className="block w-full text-sm text-stone-300 file:mr-4 file:rounded-full file:border-0 file:bg-white file:px-4 file:py-2 file:text-sm file:font-semibold file:text-stone-950"
                      />
                      <input
                        type="text"
                        value={uploadCaption}
                        onChange={(event) => setUploadCaption(event.target.value)}
                        placeholder="Optional label for your reference"
                        className="w-full rounded-2xl border border-white/10 bg-black/20 px-4 py-3 text-sm text-white outline-none transition focus:border-white/25"
                      />
                      {imageUpload.isError ? (
                        <p className="rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                          {imageUpload.error.message}
                        </p>
                      ) : null}
                      {imageUpload.isSuccess ? (
                        <p className="rounded-2xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200">
                          Image uploaded successfully.
                        </p>
                      ) : null}
                      {primaryImageMutation.isError ? (
                        <p className="rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                          {primaryImageMutation.error.message}
                        </p>
                      ) : null}
                      {deleteImageMutation.isError ? (
                        <p className="rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                          {deleteImageMutation.error.message}
                        </p>
                      ) : null}
                      <button
                        type="submit"
                        disabled={!uploadFile || imageUpload.isPending}
                        className="inline-flex items-center justify-center rounded-full bg-white px-5 py-3 text-sm font-semibold text-stone-950 transition hover:bg-stone-200 disabled:cursor-not-allowed disabled:bg-stone-500"
                      >
                        {imageUpload.isPending ? "Uploading..." : "Upload image"}
                      </button>
                    </form>
                  ) : null}
                </div>

                <div className="flex flex-wrap gap-2">
                  {[
                    { id: "gallery", label: "Gallery", icon: GalleryHorizontal },
                    { id: "overview", label: "Overview", icon: Grip },
                    { id: "civitai", label: "CivitAI", icon: Sparkles },
                  ].map((tab) => {
                    const Icon = tab.icon;
                    const isActive = modelModalTab === tab.id;
                    return (
                      <button
                        key={tab.id}
                        type="button"
                        onClick={() => setModelModalTab(tab.id as ModelModalTab)}
                        className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition ${
                          isActive
                            ? "bg-white text-stone-950"
                            : "border border-white/10 bg-white/5 text-stone-300 hover:bg-white/10"
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                        {tab.label}
                      </button>
                    );
                  })}
                </div>

                {modelModalTab === "gallery" ? (
                  <div className="space-y-5">
                    <div className="overflow-hidden rounded-[1.6rem] border border-white/10 bg-white/[0.03] p-4">
                      {(modelDetailQuery.data?.user_images ?? []).length > 0 ? (
                        <div className="columns-1 gap-4 md:columns-2 xl:columns-3">
                          {(modelDetailQuery.data?.user_images ?? []).map((image) => (
                            <div
                              key={image.id}
                              className="group relative mb-4 break-inside-avoid overflow-hidden rounded-[1.2rem] border border-white/10 bg-black/20"
                            >
                              {image.is_primary === 1 ? (
                                <span className="absolute left-3 top-3 z-10 rounded-full bg-emerald-400/90 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-stone-950">
                                  Thumb
                                </span>
                              ) : null}
                              <div className="absolute right-3 top-3 z-10 flex gap-2">
                                {image.is_primary !== 1 ? (
                                  <button
                                    type="button"
                                    onClick={() => primaryImageMutation.mutate(image.id)}
                                    disabled={primaryImageMutation.isPending}
                                    className="rounded-full border border-white/10 bg-black/55 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-white backdrop-blur transition hover:bg-black/70 disabled:opacity-60"
                                  >
                                    Thumb
                                  </button>
                                ) : null}
                                <button
                                  type="button"
                                  onClick={() => setImagePendingDelete(image.id)}
                                  className="rounded-full border border-rose-500/30 bg-black/55 p-2 text-rose-200 backdrop-blur transition hover:bg-rose-500/20"
                                  aria-label="Delete image"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              </div>
                              <img
                                src={`/comfyg-models/api/user-images/${image.filename}`}
                                alt={image.caption ?? selectedModel.filename}
                                className="h-auto w-full transition duration-500 group-hover:scale-[1.01]"
                              />
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="flex min-h-[320px] items-center justify-center rounded-[1.2rem] border border-dashed border-white/10 bg-black/20 px-6 text-center text-sm text-stone-500">
                          No personal images yet for this model.
                        </div>
                      )}
                    </div>
                  </div>
                ) : null}

                {modelModalTab === "overview" ? (
                  <div className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
                    <dl className="space-y-3 rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5 text-sm">
                      <div className="flex items-start justify-between gap-4">
                        <dt className="text-stone-500">Base model</dt>
                        <dd className="text-right text-stone-200">{getBaseModel(selectedModel) ?? "-"}</dd>
                      </div>
                      <div className="flex items-start justify-between gap-4">
                        <dt className="text-stone-500">Local path</dt>
                        <dd className="max-w-[65%] break-all text-right text-stone-200">{selectedModel.directory}</dd>
                      </div>
                      <div className="flex items-start justify-between gap-4">
                        <dt className="text-stone-500">File size</dt>
                        <dd className="text-right text-stone-200">{formatFileSize(selectedModel.file_size)}</dd>
                      </div>
                      <div className="flex items-start justify-between gap-4">
                        <dt className="text-stone-500">Hash mode</dt>
                        <dd className="text-right text-stone-200">{selectedModel.blake3 ? "blake3" : selectedModel.sha256 ? "sha256" : "-"}</dd>
                      </div>
                      <div className="flex items-start justify-between gap-4">
                        <dt className="text-stone-500">Created</dt>
                        <dd className="text-right text-stone-200">{selectedModel.created_at ?? "-"}</dd>
                      </div>
                    </dl>

                    <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                      <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-400">Quick notes</h4>
                      <div className="mt-4 space-y-4 text-sm text-stone-300">
                        <p>{selectedModel.note ?? "No personal notes yet for this model."}</p>
                        <div className="flex flex-wrap gap-2">
                          {(selectedModel.tags ?? []).length > 0 ? (
                            selectedModel.tags!.map((tag) => (
                              <span
                                key={tag}
                                className="rounded-full border border-white/10 bg-black/20 px-3 py-1 text-xs font-medium text-stone-200"
                              >
                                {tag}
                              </span>
                            ))
                          ) : (
                            <span className="text-stone-500">No tags yet.</span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                ) : null}

                {modelModalTab === "civitai" ? (
                  <div className="space-y-5">
                    <dl className="space-y-3 rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5 text-sm">
                      <div className="flex items-start justify-between gap-4">
                        <dt className="text-stone-500">CivitAI ID</dt>
                        <dd className="text-right text-stone-200">
                          {selectedModel.civitai_model_id && selectedModel.civitai_model_id !== -1
                            ? `${selectedModel.civitai_model_id}${selectedModel.civitai_version_id ? ` · v${selectedModel.civitai_version_id}` : ""}`
                            : "No CivitAI match"}
                        </dd>
                      </div>
                      <div className="flex items-start justify-between gap-4">
                        <dt className="text-stone-500">Last sync</dt>
                        <dd className="text-right text-stone-200">{selectedModel.last_civitai_sync ?? "-"}</dd>
                      </div>
                    </dl>

                    {(selectedModel.civitai_data?.stats || selectedModel.civitai_data?.modelVersions?.[0]?.trainedWords?.length) ? (
                      <div className="space-y-4 rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                        {selectedModel.civitai_data?.stats ? (
                          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                              <p className="text-xs uppercase tracking-[0.18em] text-stone-500">Rating</p>
                              <p className="mt-2 text-lg font-semibold text-white">
                                {selectedModel.civitai_data.stats.rating?.toFixed(2) ?? "-"}
                              </p>
                            </div>
                            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                              <p className="text-xs uppercase tracking-[0.18em] text-stone-500">Downloads</p>
                              <p className="mt-2 text-lg font-semibold text-white">
                                {selectedModel.civitai_data.stats.downloadCount?.toLocaleString() ?? "-"}
                              </p>
                            </div>
                            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                              <p className="text-xs uppercase tracking-[0.18em] text-stone-500">Favorites</p>
                              <p className="mt-2 text-lg font-semibold text-white">
                                {selectedModel.civitai_data.stats.favoriteCount?.toLocaleString() ?? "-"}
                              </p>
                            </div>
                            <div className="rounded-2xl border border-white/10 bg-black/20 p-4">
                              <p className="text-xs uppercase tracking-[0.18em] text-stone-500">Ratings</p>
                              <p className="mt-2 text-lg font-semibold text-white">
                                {selectedModel.civitai_data.stats.ratingCount?.toLocaleString() ?? "-"}
                              </p>
                            </div>
                          </div>
                        ) : null}

                        {selectedModel.civitai_data?.modelVersions?.[0]?.trainedWords?.length ? (
                          <div className="space-y-2">
                            <p className="text-xs uppercase tracking-[0.18em] text-stone-500">Trigger words</p>
                            <div className="flex flex-wrap gap-2">
                              {selectedModel.civitai_data.modelVersions[0].trainedWords!.slice(0, 16).map((word) => (
                                <span
                                  key={word}
                                  className="rounded-full border border-white/10 bg-black/20 px-3 py-1 text-xs font-medium text-stone-200"
                                >
                                  {word}
                                </span>
                              ))}
                            </div>
                          </div>
                        ) : null}
                      </div>
                    ) : (
                      <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5 text-sm text-stone-400">
                        No additional CivitAI metadata available for this model.
                      </div>
                    )}
                  </div>
                ) : null}
              </div>
            ) : null}

            {modalView === "image" && imageDetailQuery.data ? (
              <div className="grid gap-6 p-6 lg:grid-cols-[1.15fr_0.85fr]">
                <div className="overflow-hidden rounded-[1.6rem] border border-white/10 bg-white/[0.03] p-4">
                  <div className="flex min-h-[26rem] items-center justify-center rounded-[1.2rem] border border-white/10 bg-black/25 p-4">
                    {(imageDetailQuery.data.sources ?? []).some((source) => source.is_present) && !imagePreviewFailed ? (
                      <img
                        key={`${imageDetailQuery.data.preview_url}_${imageDetailQuery.data.updated_at}`}
                        src={`${imageDetailQuery.data.preview_url}?_t=${imageDetailQuery.data.updated_at}`}
                        alt={imageDetailQuery.data.sha256}
                        onError={() => setImagePreviewFailed(true)}
                        className="max-h-[72vh] w-full rounded-[1rem] object-contain"
                      />
                    ) : (
                      <div className="max-w-sm text-center text-sm text-stone-500">
                        No preview source is currently available for this image.
                      </div>
                    )}
                  </div>
                </div>
                <div className="space-y-5">
                  <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                    <div className="flex items-center justify-between gap-3">
                      <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-400">Sources</h3>
                      <button
                        type="button"
                        onClick={() => revealImage.mutate(imageDetailQuery.data.id)}
                        disabled={revealImage.isPending}
                        className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold text-stone-200 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <FolderOpen className="h-3.5 w-3.5" />
                        {revealImage.isPending ? "Opening..." : "Reveal in folder"}
                      </button>
                    </div>
                    <div className="mt-4 space-y-3">
                      {(imageDetailQuery.data.sources ?? []).map((source) => (
                        <div key={source.id} className="rounded-2xl border border-white/10 bg-black/20 p-4 text-sm text-stone-300">
                          <div className="font-medium text-white">{source.filename}</div>
                          <div className="mt-1 text-xs uppercase tracking-[0.18em] text-stone-500">
                            {source.source_type === "upload" ? "Upload" : "Generated scan"}
                          </div>
                          {source.path ? <div className="mt-2 break-all text-xs text-stone-500">{source.path}</div> : null}
                        </div>
                      ))}
                    </div>
                    {revealImage.isError ? (
                      <p className="mt-4 rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
                        {revealImage.error.message}
                      </p>
                    ) : null}
                  </div>

                  <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                    <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-400">Linked models</h3>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {(imageDetailQuery.data.models ?? []).length > 0 ? (
                        imageDetailQuery.data.models!.map((modelLink) => (
                          <button
                            key={`${modelLink.model_id}:${modelLink.relation_type}`}
                            type="button"
                            onClick={() => {
                              setSelectedModelId(modelLink.model_id);
                              setModelModalTab("gallery");
                              setModalView("model");
                            }}
                            className="rounded-full border border-white/10 bg-black/20 px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-200 transition hover:bg-white/10"
                          >
                            {modelLink.filename ?? modelLink.model_id}
                          </button>
                        ))
                      ) : (
                        <span className="text-sm text-stone-500">No linked local models.</span>
                      )}
                    </div>
                  </div>

                  <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                    <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-stone-400">Tags</h3>
                    <div className="mt-4 flex flex-wrap gap-2">
                      {(imageDetailQuery.data.tags ?? []).filter((tag) => tag.tag_type !== "prompt_term").map((tag) => (
                        <span key={`${tag.tag_type}:${tag.tag}`} className="rounded-full border border-white/10 bg-black/20 px-3 py-1 text-xs text-stone-200">
                          {tag.tag}
                        </span>
                      ))}
                    </div>
                    <div className="mt-5 space-y-3">
                      <button
                        type="button"
                        onClick={() => setShowImageMetadata((current) => !current)}
                        className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-black/20 px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-stone-300 transition hover:bg-white/10"
                      >
                        {showImageMetadata ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                        {showImageMetadata ? "Hide metadata" : "Show metadata"}
                      </button>
                      {showImageMetadata ? (
                        <div className="max-h-80 overflow-y-auto overflow-x-hidden rounded-2xl border border-white/10 bg-black/20 p-4">
                          <pre className="whitespace-pre-wrap break-words text-xs leading-6 text-stone-300">
                            {imageDetailQuery.data.prompt_text ??
                              JSON.stringify(imageDetailQuery.data.metadata_json ?? {}, null, 2)}
                          </pre>
                        </div>
                      ) : (
                        <p className="text-sm text-stone-500">
                          Prompt and raw metadata stay collapsed by default to keep the dialog readable.
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

          </div>
        </div>
      ) : null}

      {modalView === "model" && imagePendingDelete !== null ? (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 px-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-[1.6rem] border border-white/10 bg-[#141519] p-6 shadow-[0_24px_80px_rgba(0,0,0,0.45)]">
            <h3 className="text-lg font-semibold text-white">Delete image?</h3>
            <p className="mt-2 text-sm leading-6 text-stone-400">
              This removes the image from this model gallery and deletes the stored file from the plugin data folder.
            </p>
            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setImagePendingDelete(null)}
                className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold text-stone-200 transition hover:bg-white/10"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={async () => {
                  await deleteImageMutation.mutateAsync(imagePendingDelete);
                  setImagePendingDelete(null);
                }}
                disabled={deleteImageMutation.isPending}
                className="rounded-full bg-rose-500 px-4 py-2 text-sm font-semibold text-white transition hover:bg-rose-400 disabled:cursor-not-allowed disabled:bg-rose-800"
              >
                {deleteImageMutation.isPending ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  );
}
