import { FormEvent, useDeferredValue, useEffect, useState } from "react";
import {
  Eye,
  EyeOff,
  Filter,
  ImagePlus,
  Link2,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import { useModelDetailQuery, useModelImageUploadMutation, useModelsQuery } from "./hooks/useModels";
import { useScanStatusQuery, useStartScanMutation } from "./hooks/useScan";
import { useSaveSettingsMutation, useSettingsQuery } from "./hooks/useSettings";
import type { CivitaiModelImage } from "./types/civitai";
import type { Model } from "./types/model";

type ModalView = "none" | "status" | "settings" | "model";

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

export default function App() {
  const settingsQuery = useSettingsQuery();
  const saveSettings = useSaveSettingsMutation();
  const scanStatusQuery = useScanStatusQuery();
  const startScan = useStartScanMutation();
  const modelsQuery = useModelsQuery();

  const [modalView, setModalView] = useState<ModalView>("none");
  const [selectedModelId, setSelectedModelId] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [previewCacheEnabled, setPreviewCacheEnabled] = useState(true);
  const [showNsfwPreviews, setShowNsfwPreviews] = useState(false);
  const [uploadCaption, setUploadCaption] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const deferredSearch = useDeferredValue(search);

  const selectedModel =
    modelsQuery.data?.items.find((item) => item.id === selectedModelId) ?? null;
  const modelDetailQuery = useModelDetailQuery(selectedModelId);
  const imageUpload = useModelImageUploadMutation(selectedModelId);

  useEffect(() => {
    if (!settingsQuery.data) {
      return;
    }

    setPreviewCacheEnabled(settingsQuery.data.preview_cache_enabled);
    setShowNsfwPreviews(settingsQuery.data.show_nsfw_previews);
  }, [settingsQuery.data]);

  const models = modelsQuery.data?.items ?? [];
  const availableTypes = Array.from(new Set(models.map((model) => model.type))).sort();
  const filteredModels = models.filter((model) => {
    const matchesType = typeFilter === "all" || model.type === typeFilter;
    const baseModel = getBaseModel(model) ?? "";
    const matchesSearch =
      deferredSearch.trim() === "" ||
      model.filename.toLowerCase().includes(deferredSearch.toLowerCase()) ||
      (model.civitai_data?.name ?? "").toLowerCase().includes(deferredSearch.toLowerCase()) ||
      baseModel.toLowerCase().includes(deferredSearch.toLowerCase());

    return matchesType && matchesSearch;
  });

  const handleSettingsSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    await saveSettings.mutateAsync({
      ...(apiKey.trim() ? { civitai_api_key: apiKey.trim() } : {}),
      preview_cache_enabled: previewCacheEnabled,
      show_nsfw_previews: showNsfwPreviews,
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

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(236,122,49,0.10),_transparent_24%),radial-gradient(circle_at_85%_10%,_rgba(56,189,149,0.08),_transparent_22%),linear-gradient(180deg,_#09090b_0%,_#111215_42%,_#17181d_100%)] text-stone-100">
      <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col gap-6 px-5 py-6 lg:px-8">
        <header className="flex flex-col gap-5 rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-[0_24px_80px_rgba(0,0,0,0.28)] backdrop-blur">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-3">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/8 px-4 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-stone-300">
                <Sparkles className="h-4 w-4" />
                ComfyUI Plugin
              </span>
              <div>
                <h1 className="text-4xl font-semibold tracking-tight text-white md:text-5xl">comfyg-models</h1>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-stone-400 md:text-base">
                  Browse local models as a visual library, not as a backoffice table.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => setModalView("status")}
                className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/8 px-4 py-2 text-sm font-semibold text-stone-200 transition hover:bg-white/12"
              >
                <ShieldCheck className="h-4 w-4" />
                Status
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

          <section className="grid gap-4 lg:grid-cols-[1.4fr_1fr_auto]">
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

            <button
              type="button"
              onClick={() => startScan.mutate()}
              disabled={startScan.isPending || scanStatus?.status === "scanning"}
              className="inline-flex items-center justify-center rounded-[1.4rem] bg-white px-5 py-3 text-sm font-semibold text-stone-950 transition hover:bg-stone-200 disabled:cursor-not-allowed disabled:bg-stone-500"
            >
              {scanStatus?.status === "scanning" ? "Scanning..." : startScan.isPending ? "Starting..." : "Run scan"}
            </button>
          </section>
        </header>

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
            const matched = model.civitai_model_id !== null && model.civitai_model_id !== -1;
            const notFound = model.civitai_model_id === -1;
            const baseModel = getBaseModel(model);

            return (
              <button
                key={model.id}
                type="button"
                onClick={() => {
                  setSelectedModelId(model.id);
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
                      <span
                        className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] ${
                          matched
                            ? "bg-emerald-400/20 text-emerald-200"
                            : notFound
                              ? "bg-stone-300/15 text-stone-200"
                              : "bg-amber-400/20 text-amber-200"
                        }`}
                      >
                        {matched ? "identified" : notFound ? "not found" : "pending"}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="space-y-3 p-4">
                  <div className="flex items-center justify-between gap-3 text-sm text-stone-400">
                    <span>{baseModel ?? "Local only"}</span>
                    <span>{formatFileSize(model.file_size)}</span>
                  </div>
                </div>
              </button>
            );
          })}
        </section>
      </div>

      {modalView !== "none" ? (
        <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 px-4 py-10 backdrop-blur-sm">
          <div className="w-full max-w-5xl rounded-[2rem] border border-white/10 bg-[#101114] shadow-[0_30px_100px_rgba(0,0,0,0.45)]">
            <div className="flex items-center justify-between border-b border-white/10 px-6 py-5">
              <div>
                <h2 className="text-xl font-semibold text-white">
                  {modalView === "status" ? "Session Status" : modalView === "settings" ? "Settings" : selectedModel?.filename}
                </h2>
                <p className="mt-1 text-sm text-stone-400">
                  {modalView === "status"
                    ? "Scan pipeline progress and quick health snapshot."
                    : modalView === "settings"
                      ? "Plugin preferences and preview safety."
                      : selectedModel?.civitai_data?.name ?? "Model details"}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setModalView("none")}
                className="rounded-full border border-white/10 bg-white/5 p-2 text-stone-300 transition hover:bg-white/10"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {modalView === "status" ? (
              <div className="grid gap-5 p-6 lg:grid-cols-2">
                <div className="space-y-4 rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                  <div className="flex items-center justify-between text-sm text-stone-300">
                    <span>Models in library</span>
                    <span>{modelsQuery.data?.count ?? 0}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm text-stone-300">
                    <span>API key</span>
                    <span>{configured ? "configured" : "missing"}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm text-stone-300">
                    <span>Safe previews</span>
                    <span>{showNsfwPreviews ? "disabled" : "enabled"}</span>
                  </div>
                  <div className="flex items-center justify-between text-sm text-stone-300">
                    <span>Last verification</span>
                    <span>{username ?? "pending"}</span>
                  </div>
                </div>

                <div className="space-y-4">
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
              <div className="grid gap-6 p-6 lg:grid-cols-[1fr_0.9fr]">
                <div className="space-y-5">
                  <div className="overflow-hidden rounded-[1.6rem] border border-white/10 bg-white/[0.03]">
                    <div className="grid gap-4 p-4 md:grid-cols-2">
                      {(modelDetailQuery.data?.user_images ?? []).map((image) => (
                        <div key={image.id} className="overflow-hidden rounded-[1.2rem] border border-white/10 bg-black/20">
                          <img
                            src={`/comfyg-models/api/user-images/${image.filename}`}
                            alt={image.caption ?? selectedModel.filename}
                            className="aspect-[4/3] w-full object-cover"
                          />
                          <div className="p-3 text-sm text-stone-300">{image.caption ?? "Your image"}</div>
                        </div>
                      ))}

                      {(modelDetailQuery.data?.user_images ?? []).length === 0 ? (
                        <div className="flex min-h-[220px] items-center justify-center rounded-[1.2rem] border border-dashed border-white/10 bg-black/20 px-6 text-center text-sm text-stone-500">
                          No personal images yet for this model.
                        </div>
                      ) : null}
                    </div>
                  </div>

                  <form onSubmit={handleUploadSubmit} className="space-y-4 rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                    <div className="flex items-center gap-2 text-sm font-semibold text-white">
                      <ImagePlus className="h-4 w-4" />
                      Upload your own thumb
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
                      placeholder="Caption for this image"
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
                    <button
                      type="submit"
                      disabled={!uploadFile || imageUpload.isPending}
                      className="inline-flex items-center justify-center rounded-full bg-white px-5 py-3 text-sm font-semibold text-stone-950 transition hover:bg-stone-200 disabled:cursor-not-allowed disabled:bg-stone-500"
                    >
                      {imageUpload.isPending ? "Uploading..." : "Upload image"}
                    </button>
                  </form>
                </div>

                <div className="space-y-5">
                  <div className="rounded-[1.5rem] border border-white/10 bg-white/[0.03] p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-stone-500">{selectedModel.type}</p>
                        <h3 className="mt-2 text-2xl font-semibold text-white">{selectedModel.filename}</h3>
                        <p className="mt-2 text-sm text-stone-400">{selectedModel.civitai_data?.name ?? "Local-only model"}</p>
                      </div>
                      {getCivitaiUrl(selectedModel) ? (
                        <a
                          href={getCivitaiUrl(selectedModel)!}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/8 px-4 py-2 text-sm font-semibold text-stone-200 transition hover:bg-white/12"
                        >
                          <Link2 className="h-4 w-4" />
                          Open on CivitAI
                        </a>
                      ) : null}
                    </div>
                  </div>

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
                      <dt className="text-stone-500">CivitAI ID</dt>
                      <dd className="text-right text-stone-200">
                        {selectedModel.civitai_model_id && selectedModel.civitai_model_id !== -1
                          ? `${selectedModel.civitai_model_id}${selectedModel.civitai_version_id ? ` · v${selectedModel.civitai_version_id}` : ""}`
                          : "-"}
                      </dd>
                    </div>
                  </dl>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </main>
  );
}
