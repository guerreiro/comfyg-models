import { RefreshCw, Settings2, ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useSaveSettingsMutation, useSettingsQuery } from "./hooks/useSettings";

export default function App() {
  const settingsQuery = useSettingsQuery();
  const saveSettings = useSaveSettingsMutation();
  const [apiKey, setApiKey] = useState("");
  const [previewCacheEnabled, setPreviewCacheEnabled] = useState(true);

  useEffect(() => {
    if (!settingsQuery.data) {
      return;
    }

    setPreviewCacheEnabled(settingsQuery.data.preview_cache_enabled);
  }, [settingsQuery.data]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    await saveSettings.mutateAsync({
      ...(apiKey.trim() ? { civitai_api_key: apiKey.trim() } : {}),
      preview_cache_enabled: previewCacheEnabled,
    });

    setApiKey("");
  };

  const username = saveSettings.data?.civitai_username;
  const configured = settingsQuery.data?.civitai_api_key_configured ?? false;

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(247,148,29,0.16),_transparent_32%),linear-gradient(180deg,_#f7f1e8_0%,_#f0e2cf_48%,_#e6d2bb_100%)] text-stone-900">
      <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-10 px-6 py-10 lg:px-10">
        <section className="grid gap-6 rounded-[2rem] border border-stone-900/10 bg-white/75 p-8 shadow-[0_20px_70px_rgba(70,44,18,0.12)] backdrop-blur md:grid-cols-[1.4fr_0.9fr]">
          <div className="space-y-5">
            <span className="inline-flex items-center gap-2 rounded-full border border-stone-900/10 bg-stone-950 px-4 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-stone-100">
              <ShieldCheck className="h-4 w-4" />
              Fase 0 bootstrap
            </span>
            <div className="space-y-3">
              <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-balance md:text-5xl">
                Comfyg Models começa como uma base sólida para gerir e entender a tua coleção local.
              </h1>
              <p className="max-w-2xl text-sm leading-6 text-stone-700 md:text-base">
                Este scaffold já prepara o plugin para servir a SPA em{" "}
                <code className="rounded bg-stone-900/6 px-1.5 py-0.5 text-xs">/comfyg-models</code>,
                guardar configurações seguras e evoluir para scan, hashing e CivitAI lookup sem retrabalho estrutural.
              </p>
            </div>
          </div>

          <div className="rounded-[1.5rem] border border-stone-900/10 bg-stone-950 p-6 text-stone-100 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Status do bootstrap</h2>
              <Settings2 className="h-5 w-5 text-amber-300" />
            </div>
            <dl className="mt-5 space-y-4 text-sm">
              <div className="flex items-start justify-between gap-4">
                <dt className="text-stone-300">Settings carregadas</dt>
                <dd>{settingsQuery.isSuccess ? "sim" : settingsQuery.isLoading ? "carregando" : "erro"}</dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-stone-300">CivitAI API key</dt>
                <dd>{configured ? "configurada" : "não configurada"}</dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-stone-300">Preview cache local</dt>
                <dd>{previewCacheEnabled ? "ativo" : "desativado"}</dd>
              </div>
              <div className="flex items-start justify-between gap-4">
                <dt className="text-stone-300">Última verificação</dt>
                <dd>{username ? `API validada para ${username}` : "pendente"}</dd>
              </div>
            </dl>
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <form
            onSubmit={handleSubmit}
            className="rounded-[1.75rem] border border-stone-900/10 bg-white/80 p-6 shadow-[0_16px_45px_rgba(70,44,18,0.10)]"
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold">Settings</h2>
                <p className="mt-1 text-sm text-stone-600">
                  A API key nunca volta para o frontend. Só o estado configurado é exibido.
                </p>
              </div>
              <button
                type="button"
                onClick={() => settingsQuery.refetch()}
                className="inline-flex items-center gap-2 rounded-full border border-stone-900/10 bg-stone-100 px-4 py-2 text-sm font-medium text-stone-700 transition hover:bg-stone-200"
              >
                <RefreshCw className={`h-4 w-4 ${settingsQuery.isFetching ? "animate-spin" : ""}`} />
                Atualizar
              </button>
            </div>

            <div className="mt-6 space-y-5">
              <label className="block space-y-2">
                <span className="text-sm font-medium text-stone-800">CivitAI API key</span>
                <input
                  type="password"
                  autoComplete="off"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder={configured ? "Configurada. Introduz uma nova key para substituir." : "Introduz a tua API key"}
                  className="w-full rounded-2xl border border-stone-900/10 bg-stone-50 px-4 py-3 text-sm outline-none transition focus:border-stone-950/30 focus:bg-white"
                />
              </label>

              <label className="flex items-center justify-between gap-4 rounded-2xl border border-stone-900/10 bg-stone-50 px-4 py-3">
                <div>
                  <span className="block text-sm font-medium text-stone-800">Cache local de previews</span>
                  <span className="mt-1 block text-xs text-stone-600">
                    Quando ativo, o backend pode guardar previews do CivitAI em disco para abrir mais rápido.
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={previewCacheEnabled}
                  onChange={(event) => setPreviewCacheEnabled(event.target.checked)}
                  className="h-5 w-5 rounded border-stone-300 text-stone-950 focus:ring-stone-900"
                />
              </label>

              {settingsQuery.isError ? (
                <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {settingsQuery.error.message}
                </p>
              ) : null}

              {saveSettings.isError ? (
                <p className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {saveSettings.error.message}
                </p>
              ) : null}

              {saveSettings.isSuccess ? (
                <p className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                  Settings guardadas com sucesso{username ? ` para ${username}` : ""}.
                </p>
              ) : null}

              <div className="flex items-center gap-3">
                <button
                  type="submit"
                  disabled={saveSettings.isPending}
                  className="inline-flex items-center justify-center rounded-full bg-stone-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-stone-800 disabled:cursor-not-allowed disabled:bg-stone-500"
                >
                  {saveSettings.isPending ? "Guardando..." : "Guardar e verificar"}
                </button>
                <a
                  href="https://civitai.com/user/account"
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm font-medium text-stone-700 underline decoration-stone-300 underline-offset-4 transition hover:text-stone-950"
                >
                  Abrir conta CivitAI
                </a>
              </div>
            </div>
          </form>

          <section className="rounded-[1.75rem] border border-stone-900/10 bg-[linear-gradient(180deg,_rgba(255,255,255,0.92),_rgba(244,233,217,0.92))] p-6 shadow-[0_16px_45px_rgba(70,44,18,0.10)]">
            <h2 className="text-xl font-semibold">Próximos blocos preparados</h2>
            <ul className="mt-5 space-y-3 text-sm leading-6 text-stone-700">
              <li>Base SQLite pronta para migrations com schema versão 1.</li>
              <li>Scanner, hasher, watcher e cliente CivitAI já existem como módulos reais com logs.</li>
              <li>Frontend pronto para crescer com TanStack Query, Zustand e tipagem compartilhada.</li>
              <li>Servidor preparado para devolver erros padronizados em JSON.</li>
            </ul>
          </section>
        </section>
      </div>
    </main>
  );
}
