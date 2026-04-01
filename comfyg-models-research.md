# Comfyg-Models — Research & Discovery

> Documento de pesquisa e planejamento para um gerenciador de modelos robusto integrado ao CivitAI.  
> Autor: Gabriel | Data: Março 2026  
> Plugin: **comfyg-models** — repo separado, complementar ao comfyg-switch

---

## 1. Panorama: O que já existe

### 1.1 ComfyUI-Lora-Manager (willmiao) — O principal concorrente

**Repo:** `https://github.com/willmiao/ComfyUI-Lora-Manager`  
**Acesso:** `http://localhost:8188/loras`

O projeto mais completo que existe hoje. Começou focado em LoRAs mas evoluiu para cobrir checkpoints também. Opera como uma **tela separada** — o mesmo modelo que vamos adoptar.

#### O que ele já faz bem:
- Interface web própria, desacoplada do canvas do ComfyUI
- Scan local de modelos + metadados via CivitAI API (por hash SHA256/Blake3)
- Preview de imagens e vídeos dos modelos
- Gestão de **receitas** (combinações favoritas de LoRAs + parâmetros)
- Download direto do CivitAI dentro da própria tela
- Send checkpoint → injeta no node do workflow atual
- Extensão Chrome para integração com o site do CivitAI
- Suporte a **CivArchive** como fallback (modelos deletados do CivitAI)
- Lazy hash computation (não trava na inicialização)
- Modo standalone (roda sem o ComfyUI completo)
- Pause/resume de downloads com persistência entre reinicializações

#### Stack interna (via CLAUDE.md deles):
- **SPA principal:** Vanilla JS + CSS — sem framework, sem build step
- **Widgets do canvas:** Vanilla JS ES modules em `web/comfyui/*.js`
- **Widgets avançados (migração posterior):** Vue 3 + TypeScript + PrimeVue + Vite
- **Backend:** Python + aiohttp, SQLite para cache

> Começaram em Vanilla JS e estão a migrar para Vue à medida que a complexidade cresce. É exactamente o caminho que queremos evitar — começar já com React.

#### Limitações e fraquezas identificadas:
- PRs externos fechados temporariamente
- Checkpoint management é secundário; LoRA é o foco principal
- Sem notas pessoais, tags locais, imagens de referência próprias, prompts favoritos
- Sem histórico de uso por modelo
- Sem filtros cruzando todos os tipos em simultâneo
- Sem integração com qualquer conceito de "preset de workflow"
- Funcionalidades atrás de paywall

---

### 1.2 ComfyUI-LoRA-Sidebar (Kinglord)

Interface visual dentro do sidebar do ComfyUI. Battle-tested com 9000+ modelos, mas limitado a LoRAs e sem gestão completa. Referência útil para UX de descoberta rápida.

---

### 1.3 ComfyUI-EasyCivitai-XTNodes (X-T-E-R)

Nodes dentro do ComfyUI com preview inline e lookup automático por hash. Complementar — foco em *loading* com preview, não em *gestão* de coleção.

---

## 2. Análise Competitiva

| Feature | Lora Manager | LoRA Sidebar | **Comfyg-Models** |
|---|---|---|---|
| Interface separada (SPA) | ✅ | ❌ (sidebar) | ✅ |
| Todos os tipos de modelo | Parcial | ❌ | ✅ |
| CivitAI integration | ✅ | ✅ | ✅ |
| Notas pessoais por modelo | ❌ | ❌ | ✅ |
| Tags customizadas locais | Parcial | ❌ | ✅ |
| Imagens de referência próprias | ❌ | ❌ | ✅ |
| Prompts favoritos por modelo | ❌ | ❌ | ✅ |
| Histórico de uso | ❌ | ❌ | ✅ |
| Integração com workflow switch | ❌ | ❌ | ✅ (comfyg-switch) |
| Comparação de versões side-by-side | ❌ | ❌ | ✅ |
| Cross-filter todos os tipos | ❌ | ❌ | ✅ |
| Open source + open contribution | Fechado | ✅ | ✅ |

**O diferencial central:** o comfyg-models é uma ferramenta de *conhecimento pessoal* sobre os modelos, não apenas de *listagem*. Nenhuma outra ferramenta tem esta camada.

---

## 3. CivitAI API — O que está disponível

**Base URL:** `https://civitai.com/api/v1/`  
**Auth:** `Authorization: Bearer TOKEN` no header, ou `?token=` na query string

### Endpoints relevantes:

```
GET /api/v1/models                         → lista/busca modelos
GET /api/v1/models/:modelId                → detalhes completos
GET /api/v1/model-versions/:modelVersionId → detalhes de uma versão
GET /api/v1/model-versions/by-hash/:hash   → lookup por hash ← o mais importante
GET /api/v1/images                         → imagens geradas com o modelo
GET /api/v1/tags                           → tags disponíveis
GET /api/download/models/:modelVersionId   → download direto com redirect
GET /api/v1/me                             → dados do utilizador autenticado
```

### Campos mais úteis de `/api/v1/models/:id`:
- `type` — Checkpoint, LORA, TextualInversion, Hypernetwork, VAE, ControlNet, Poses, Upscaler, ESRGAN, LoCon, DoRA...
- `stats` — downloadCount, favoriteCount, ratingCount, rating
- `modelVersions[].trainedWords[]` — trigger words
- `modelVersions[].baseModel` — SD 1.5, SDXL, Flux.1 D, Flux.1 S, Pony, Illustrious...
- `modelVersions[].files[].hashes` — SHA256 + Blake3 do ficheiro
- `modelVersions[].images[]` — URLs de preview + metadata de geração completa (prompt, negative, sampler, steps, cfg, seed)

### O endpoint mais poderoso para uso local:

```
GET /api/v1/model-versions/by-hash/[sha256_ou_blake3]
```

Dado qualquer `.safetensors` local, identifica automaticamente o modelo no CivitAI sem o utilizador informar nada. É a base de toda a integração automática.

### Boas práticas:
- ~100 req/min considerado seguro pela comunidade
- Cache local obrigatório — nunca fazer lookup repetido para o mesmo ficheiro
- CivArchive como fallback para modelos deletados do CivitAI

---

## 4. Decisões de Arquitetura (Resolvidas)

### 4.1 Nome
**`comfyg-models`** — mantém o prefixo `comfyg-` para consistência com o comfyg-switch.

---

### 4.2 Localização dos dados de runtime

**`ComfyUI/user/comfyg-models/`**

A pasta `user/` do ComfyUI é o local canónico para dados persistentes de plugins. Sobrevive a updates e reinstalações do plugin. Estrutura:

```
ComfyUI/user/comfyg-models/
  cache.db         ← SQLite: metadados CivitAI, notas, tags, histórico
  previews/        ← imagens de preview do CivitAI em cache local
  user-images/     ← imagens de referência uploaded pelo utilizador
  settings.json    ← API key, preferências
```

---

### 4.3 Distribuição do frontend (dist/)

**Bundle commitado no repo** — o `web/dist/` vai versionado no repositório.

O utilizador instala via ComfyUI Manager ou git clone e funciona imediatamente, sem `npm install`, sem build step. O Python serve os ficheiros estáticos do `dist/` directamente. O build step (`npm run build`) existe só no workflow de desenvolvimento, antes de cada release.

---

### 4.4 Hashing: Blake3 com fallback gracioso para SHA256

**Decisão:** tentar blake3, cair silenciosamente para SHA256 se a instalação falhar.

#### Análise de impacto do blake3:

O package `blake3` (PyPI) são bindings Python para a implementação oficial em Rust via PyO3. Publica wheels pré-compilados para:
- Windows x64 (todas as versões Python suportadas)
- macOS x64 + arm64 (Apple Silicon)
- Linux x64 + arm64

O risco de instalação falhar existe em plataformas exóticas (Linux arm32, BSD, setups sem compilador Rust). Para esses casos, o fallback para SHA256 é transparente — o CivitAI aceita ambos os hashes no endpoint `by-hash`.

**Impacto de performance** (onde blake3 está disponível):

| Cenário | SHA256 (hashlib) | Blake3 (mmap + multi-thread) |
|---|---|---|
| Ficheiro de 2GB | ~15s | ~1.5s |
| Ficheiro de 6GB | ~45s | ~4s |
| Coleção de 200 modelos (média 3GB) | ~2.5h | ~13min |

A diferença é muito visível no primeiro scan de uma coleção grande. Vale a pena.

**Implementação:**

```python
# hasher.py
import hashlib
from pathlib import Path

try:
    import blake3 as _blake3
    _HAS_BLAKE3 = True
except ImportError:
    _HAS_BLAKE3 = False

CHUNK_SIZE = 8 * 1024 * 1024  # 8MB

def hash_file(path: Path) -> dict[str, str]:
    """Calcula SHA256 sempre; Blake3 se disponível. Retorna dict com os hashes."""
    sha256 = hashlib.sha256()
    result = {"sha256": None, "blake3": None}

    if _HAS_BLAKE3:
        b3 = _blake3.blake3(max_threads=_blake3.AUTO)
        with open(path, "rb") as f:
            b3.update_mmap(str(path))
        result["blake3"] = b3.hexdigest()
        # SHA256 ainda necessário como fallback
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
                sha256.update(chunk)
    else:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
                sha256.update(chunk)

    result["sha256"] = sha256.hexdigest()
    return result

def preferred_hash(hashes: dict) -> tuple[str, str]:
    """Retorna (algoritmo, valor) para usar no lookup do CivitAI."""
    if hashes.get("blake3"):
        return "blake3", hashes["blake3"]
    return "sha256", hashes["sha256"]
```

---

### 4.5 Preview images: cache local com CDN como fallback

**Estratégia:** ao abrir o detalhe de um modelo, verificar se a preview já existe em `ComfyUI/user/comfyg-models/previews/`. Se sim, servir local. Se não, servir URL do CivitAI e iniciar download em background para cache futura.

O download para cache é lazy e opcional — o utilizador pode desactivar nas settings se o espaço em disco for uma preocupação. Numa coleção de 500 modelos com 3 previews cada (~300KB por preview), o cache total seria ~450MB — aceitável para a maioria dos utilizadores.

---

### 4.6 "Send to workflow" — Adiado

A funcionalidade de injectar o checkpoint num node activo do workflow fica fora do MVP. Será implementada na Fase 3, com escopo limitado a checkpoints (não LoRAs nem outros tipos).

---

## 5. Stack Técnica Final

### Como o frontend funciona num custom node ComfyUI

O ComfyUI usa `aiohttp` como servidor web. Custom nodes registam rotas adicionais via `PromptServer.instance.routes`. A SPA é uma web app normal servida em `http://localhost:8188/comfyg-models`.

```python
from server import PromptServer
from aiohttp import web
from pathlib import Path

WEB_DIR = Path(__file__).parent / 'web' / 'dist'
routes = PromptServer.instance.routes

@routes.get('/comfyg-models')
async def serve_spa(request):
    return web.FileResponse(WEB_DIR / 'index.html')

@routes.get('/comfyg-models/assets/{filename}')
async def serve_assets(request):
    return web.FileResponse(WEB_DIR / 'assets' / request.match_info['filename'])
```

O Python serve ficheiros estáticos. Qualquer stack que produza ficheiros estáticos funciona. A escolha é puramente de developer experience.

### Stack seleccionada

| Camada | Tecnologia | Justificação |
|---|---|---|
| Backend | Python 3.10+ + aiohttp | Nativo do ComfyUI |
| Storage | SQLite via `aiosqlite` | File-based, zero configuração |
| Hashing | `hashlib` SHA256 + `blake3` (optional) | Graceful fallback |
| File watching | `watchdog` | Detectar novos modelos |
| SPA framework | React 19 + TypeScript | Componentes, tipagem, ecossistema |
| Build tool | Vite 6 | Fast, tree-shaking |
| Data fetching | TanStack Query v5 | Cache automático, loading states |
| Virtualização | TanStack Virtual v3 | Grid de 10k+ modelos sem lag |
| Styling | Tailwind CSS v4 | Utility-first |
| Icons | Lucide React | Tree-shakeable |
| Estado global | Zustand | Simples, sem boilerplate |

---

## 6. Arquitetura Completa

### 6.1 Estrutura de ficheiros do plugin

```
comfyg-models/
  __init__.py                     ← entry point ComfyUI (regista rotas + node)
  requirements.txt                ← blake3, aiosqlite, watchdog

  py/
    server.py                     ← registo de rotas aiohttp
    scanner.py                    ← scan de diretórios (lê extra_model_paths.yaml)
    hasher.py                     ← SHA256 + Blake3 lazy, graceful fallback
    civitai.py                    ← cliente CivitAI API com rate limiting
    database.py                   ← aiosqlite: cache, notas, tags, histórico
    watcher.py                    ← watchdog para novos ficheiros
    settings.py                   ← leitura/escrita de settings.json

  web/
    src/
      components/
        ModelGrid/                 ← grid virtualizado (TanStack Virtual)
        ModelDetail/               ← detalhe com gallery, notas, triggers
        FilterPanel/               ← filtros por tipo, base model, tags
        NoteEditor/                ← editor markdown
        CivitaiGallery/            ← galeria de previews do CivitAI
        DownloadManager/           ← progresso de downloads (fase 3)
        UserImageUpload/           ← drag & drop de imagens de referência
      hooks/
        useModels.ts
        useCivitai.ts
        useSettings.ts
      store/
        filters.ts                 ← Zustand: estado dos filtros activos
        ui.ts                      ← Zustand: estado da UI (modal aberto, etc.)
      types/
        model.ts
        civitai.ts
      App.tsx
    dist/                         ← commitado no repo após npm run build
    package.json
    vite.config.ts
    tsconfig.json
```

### 6.2 API REST interna

```
# SPA
GET  /comfyg-models                          → serve index.html
GET  /comfyg-models/assets/*                 → serve bundle assets

# Modelos
GET  /comfyg-models/api/models               → lista com filtros (?type=lora&base=flux...)
GET  /comfyg-models/api/models/:id           → detalhes + metadados completos
GET  /comfyg-models/api/models/:id/hash      → estado do hash (pending|done|error)

# Conhecimento pessoal
PUT  /comfyg-models/api/models/:id/note      → salva nota markdown
PUT  /comfyg-models/api/models/:id/tags      → define tags locais (array)
PUT  /comfyg-models/api/models/:id/rating    → rating pessoal 1-5
POST /comfyg-models/api/models/:id/images    → upload imagem de referência
DELETE /comfyg-models/api/models/:id/images/:imgId

# Prompts favoritos
GET  /comfyg-models/api/models/:id/prompts
POST /comfyg-models/api/models/:id/prompts
PUT  /comfyg-models/api/models/:id/prompts/:promptId
DELETE /comfyg-models/api/models/:id/prompts/:promptId

# Sistema
POST /comfyg-models/api/scan                 → re-scan manual de diretórios
GET  /comfyg-models/api/scan/status          → progresso do scan/hash em curso
GET  /comfyg-models/api/civitai/proxy/*      → proxy CivitAI (evita CORS)
GET  /comfyg-models/api/settings
PUT  /comfyg-models/api/settings
```

### 6.3 Esquema SQLite

```sql
CREATE TABLE models (
    id TEXT PRIMARY KEY,                    -- path relativo: "checkpoints/v1-5-pruned.safetensors"
    filename TEXT NOT NULL,
    directory TEXT NOT NULL,               -- "checkpoints", "loras", etc.
    type TEXT NOT NULL,
    file_size INTEGER,
    sha256 TEXT,
    blake3 TEXT,
    civitai_model_id INTEGER,
    civitai_version_id INTEGER,
    civitai_data JSON,                     -- resposta completa da API em cache
    last_hash_at TIMESTAMP,
    last_civitai_sync TIMESTAMP,
    last_used_at TIMESTAMP,
    use_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE model_notes (
    model_id TEXT PRIMARY KEY REFERENCES models(id),
    note TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE model_tags (
    model_id TEXT REFERENCES models(id),
    tag TEXT NOT NULL,
    PRIMARY KEY (model_id, tag)
);

CREATE TABLE model_ratings (
    model_id TEXT PRIMARY KEY REFERENCES models(id),
    rating INTEGER CHECK (rating BETWEEN 1 AND 5)
);

CREATE TABLE model_user_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT REFERENCES models(id),
    filename TEXT NOT NULL,
    caption TEXT,
    prompt TEXT,
    negative_prompt TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE model_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id TEXT REFERENCES models(id),
    title TEXT,
    prompt TEXT NOT NULL,
    negative_prompt TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE civitai_previews (
    model_id TEXT REFERENCES models(id),
    url TEXT NOT NULL,
    local_filename TEXT,                   -- em ComfyUI/user/comfyg-models/previews/
    PRIMARY KEY (model_id, url)
);

CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value JSON
);

-- Índices para performance
CREATE INDEX idx_models_type ON models(type);
CREATE INDEX idx_models_civitai ON models(civitai_model_id);
CREATE INDEX idx_model_tags_tag ON model_tags(tag);
```

---

## 7. Features Prioritizadas

### Fase 1 — MVP

**Scan & Identificação:**
- [ ] Scan de todos os diretórios de modelos (checkpoints, loras, vae, controlnet, embeddings, upscale_models, clip, clip_vision)
- [ ] Suporte a `extra_model_paths.yaml`
- [ ] Hashing lazy em background com blake3 + fallback SHA256
- [ ] Lookup automático por hash na CivitAI API
- [ ] Cache local de metadados (SQLite)
- [ ] Watchdog para detectar novos ficheiros

**Interface:**
- [ ] Grid virtualizado com preview de cada modelo
- [ ] Filtros por tipo, base model, tags — com cross-filter entre todos os tipos
- [ ] Busca por nome (fuzzy)
- [ ] Ordenação por nome, data, tamanho, rating CivitAI, uso recente
- [ ] Detalhe: galeria de previews, descrição, trigger words, stats, ficheiros locais

**Configurações:**
- [ ] API key CivitAI
- [ ] Caminhos de modelos extra
- [ ] Activar/desactivar cache de previews locais

---

### Fase 2 — Conhecimento pessoal (o diferencial)

- [ ] **Notas pessoais** — editor markdown por modelo
- [ ] **Tags customizadas** — locais, independentes do CivitAI
- [ ] **Rating pessoal** — separado do rating do CivitAI
- [ ] **Imagens de referência próprias** — drag & drop de prints que gerou com o modelo
- [ ] **Prompts favoritos** — biblioteca de prompts por modelo (com título, prompt, negative, notas)
- [ ] **Histórico de uso** — timestamp e contagem de quando foi carregado

---

### Fase 3 — Integração e workflow

- [ ] **Download direto** do CivitAI com progress bar e pause/resume
- [ ] **Check for updates** — verificar versões mais novas disponíveis
- [ ] **Send to workflow** — enviar checkpoint ao node activo (só checkpoints)
- [ ] **Integração comfyg-switch** — ver/editar presets, histórico de uso cruzado
- [ ] **CivArchive fallback** — metadados de modelos deletados

---

### Fase 4 — Avançado

- [ ] **Comparação de versões** side-by-side
- [ ] **Estatísticas da coleção** — total por tipo/base model, tamanho em disco
- [ ] **Export/import** de notas e tags (JSON, para backup ou partilha)
- [ ] **Extensão de browser** — ver quais modelos já tens ao navegar no CivitAI
- [ ] **Entry no menu do ComfyUI** — "Open Model Manager" no top menu

---

## 8. Integração com comfyg-switch (Fase 3)

Os dois plugins comunicam via REST directa — cada um verifica se o outro está presente na inicialização e expõe endpoints de integração:

```
# comfyg-switch expõe (consumido pelo comfyg-models):
GET  /comfyg-switch/api/presets              → lista presets configurados
GET  /comfyg-switch/api/presets/:id          → detalhe de um preset (inclui checkpoint)
POST /comfyg-switch/api/presets/:id/checkpoint → actualiza o checkpoint de um preset

# comfyg-models notifica (via WebSocket do ComfyUI):
Evento: model_used { model_id, preset_id, timestamp }
```

Features resultantes desta integração:
- Detalhe do modelo mostra quais presets do switch o usam
- Ao trocar o checkpoint de um preset, o manager actualiza o histórico
- Histórico de uso enriquecido: "usado no preset 'SDXL Photorealism', 3 dias atrás"

---

## 9. Referências

- [ComfyUI-Lora-Manager](https://github.com/willmiao/ComfyUI-Lora-Manager) — principal referência de UX, arquitetura e stack
- [ComfyUI_LoRA_Sidebar](https://github.com/Kinglord/ComfyUI_LoRA_Sidebar) — referência de UX de sidebar
- [CivitAI REST API Reference](https://github.com/civitai/civitai/wiki/REST-API-Reference) — docs oficiais
- [CivArchive](https://civarchive.com) — fallback para modelos deletados
- [blake3-py](https://github.com/oconnor663/blake3-py) — bindings Python para blake3
- [comfyg-switch](https://github.com/guerreiro/comfyg-switch) — integração planeada na Fase 3
- [TanStack Query](https://tanstack.com/query) — data fetching
- [TanStack Virtual](https://tanstack.com/virtual) — virtualização de listas
