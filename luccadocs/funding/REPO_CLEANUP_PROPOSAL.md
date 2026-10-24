# Repository Hygiene & Asset Cleanup Proposal

**Document Version:** 1.0.0  
**Date:** 2026-10-21  
**Context:** Preparation for Public Open-Sourcing & Grant Applications (Corrigibility, Manifund, Mercor)  
**Status:** PROPOSED ACTIONS (Zero destructive commands executed per Ground Rule 5)

---

## 1. Executive Summary & Audit Findings

A thorough hygiene scan of the Project Lucca repository working tree and complete Git commit history was performed as part of the Grant Preparation Brief (Question A9). 

### Key Findings:
1. **Secrets & Keys:** **CLEAN.** No cryptographic master keys (`data/keys/master.key`), `.env` files, or production API tokens are tracked in git history or the current working tree.
2. **Third-Party Copyrighted Assets:** **ACTION REQUIRED.**
   - **Chrono Trigger Sprites:** 16 sprite frames from Square Enix's *Chrono Trigger* (1995) exist in `assets/sprites/lucca/*.png`, tracked in git history since commit `066dad3` (2026-10-06).
   - **Asuka RVC & Tiffany Grant Audio:** Voice samples and RVC voice conversion models for character Asuka Langley Soryu / voice actor Tiffany Grant were committed to history in commits `fc9639f` and `8826f35` (2026-10-06). Harvested audio clips also reside in `models/tts/references/asuka/harvested/` (currently ignored by `.gitignore`).
3. **Hard-Coded Environment Paths:** **ACTION REQUIRED.** 131 files across docs, scripts, and source contain absolute local paths (e.g. `c:\Projects\ProjectLucca`, `C:\ProjectLucca`, or `file:///c:/...`).
4. **Third-Party Model Credits:** **MINOR FIX REQUIRED.** The main `README.md` credits Kokoro, Faster-Whisper, Gemma 4, and OpenVINO, but omits attribution for ModernBERT (Apache 2.0).

---

## 2. Identified Assets for Removal & CC0/Open Replacements

| Path / Asset | Type / Origin | Commit Introduced | Risk Severity | Recommended Replacement |
| :--- | :--- | :--- | :--- | :--- |
| `assets/sprites/lucca/*.png` (16 frames) | Chrono Trigger (Square Enix 1995) 2D character sprites | `066dad3` | **HIGH** (Copyright infringement in public repo) | Procedural geometric SVG avatar or CC0 character sprite set (e.g. Kenney.nl Character Assets) |
| `models/tts/references/asuka/` | Tiffany Grant voice samples & RVC models | `fc9639f`, `8826f35` | **HIGH** (Voice rights & trademark infringement) | Standard Kokoro-82M default reference voices (`af_heart`, `am_adam`) under Apache 2.0 |
| `models/tts/references/asuka/harvested/*.wav` | Local harvested voice clips | Uncommitted (local tree) | **MEDIUM** (Local IP exposure) | Delete directory from working tree; retain `.gitignore` entry |

---

## 3. Repository Strategy: Clean Snapshot vs. History Rewrite

We evaluated two approaches for publishing the repository:

### Option A: Complete Git History Rewrite (`git filter-repo`)
- **Procedure:** Run `git-filter-repo` to purge `assets/sprites/lucca/` and `models/tts/` from the entire commit history.
- **Risks & Drawbacks:**
  - **Hash Invalidation:** Rewriting history changes every commit SHA-256 hash in the project.
  - **Academic & Benchmark Corruption:** All benchmark artifacts, `RESULTS.md`, `MANIFEST.yaml`, research papers (TR-01 through TR-05, Papers 03 and 06), and audit trails cite specific commit hashes (e.g. `84f2447`, `defadae`, `d9ac70f`). Invalidating these hashes destroys external verification and reproducibility.
  - **Collaborator Desynchronization:** Any existing clone or mirror will experience merge conflicts and divergence.

### Option B: Clean Snapshot Public Repository (RECOMMENDED)
- **Procedure:** Keep the current `ProjectLucca` repository as the private development and provenance archive. Create a clean public repository (e.g. `ProjectLucca-Public` or `lucca-runtime`) initialized from a sanitized HEAD snapshot with:
  1. Chrono Trigger sprites replaced by CC0 SVG avatars.
  2. Proprietary voice references removed; Kokoro default voices configured.
  3. Hardcoded paths refactored to standard environment variables (`LUCCA_HOME`).
  4. Complete license attribution table in `README.md`.
- **Advantages:**
  - Preserves 100% of historical commit hashes, benchmarks, and research citations.
  - Zero risk of residual copyrighted blob leaks.
  - Clean, professional first public commit.

---

## 4. Proposed Execution Commands (For Owner Execution Only)

*Note: Per Ground Rule 5, the agent has NOT executed any of these commands.*

### Path 1: Commands to Prepare Clean Public Snapshot (Recommended)

```bash
# 1. Create a temporary export directory
mkdir /tmp/lucca-public-export
cd c:\Projects\ProjectLucca

# 2. Export clean working tree (excluding git history and ignored files)
git archive HEAD | tar -x -C /tmp/lucca-public-export

# 3. Clean up copyrighted assets in the export
cd /tmp/lucca-public-export
rm -rf assets/sprites/lucca/
rm -rf models/tts/references/asuka/

# 4. Copy CC0 placeholder assets
# (Copy kenney sprites or SVG placeholder into assets/sprites/default/)

# 5. Initialize clean public repository
git init -b main
git add .
git commit -m "feat: initial public release of Project Lucca runtime (v1.46.5)"

# 6. Verify no copyrighted assets or secrets remain
git status
```

### Path 2: Commands to Rewrite In-Place History (If Purging Private History)

```bash
# PREREQUISITE: Back up the entire repository folder before running!
cp -r c:\Projects\ProjectLucca c:\Projects\ProjectLucca_BACKUP

cd c:\Projects\ProjectLucca

# Use git-filter-repo (recommended over BFG)
uv tool run git-filter-repo --path assets/sprites/lucca --invert-paths --force
uv tool run git-filter-repo --path models/tts/references/asuka --invert-paths --force

# Force garbage collection to prune loose objects
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

---

## 5. Hardcoded Path Normalization Plan

131 files currently reference `c:\Projects\ProjectLucca` or `C:\ProjectLucca`. We propose replacing these with standard environment-backed paths:

```python
# Proposed standard path resolution helper
import os
from pathlib import Path

LUCCA_ROOT = Path(os.environ.get("LUCCA_HOME", Path.home() / ".lucca"))
LUCCA_MODELS = Path(os.environ.get("LUCCA_MODELS", LUCCA_ROOT / "models"))
LUCCA_DATA = Path(os.environ.get("LUCCA_DATA", LUCCA_ROOT / "data"))
```

### Affected Categories to Batch-Replace:
1. **Source Code (`src/lucca/`):** Replace default path strings in `config.py`, `verifier.py`, and `ports.py`.
2. **Benchmark Scripts (`scripts/`):** Use `argparse` with defaults resolving relative to repository root (`Path(__file__).resolve().parents[1]`).
3. **Documentation (`luccadocs/`):** Update markdown links to use repo-relative paths (`./luccadocs/...`) rather than Windows URI schemes (`file:///c:/...`).

---

## 6. License Attribution Updates (`README.md`)

Add the following missing attributions to `README.md`:

```markdown
### Model & Library Attributions
- **ModernBERT**: Answer.AI / LightOn (Apache 2.0) — Semantic NLI consistency verifier.
- **Kokoro-82M**: Hexgrad (Apache 2.0) — Lightweight neural text-to-speech.
- **Faster-Whisper**: SYSTRAN / OpenAI (MIT) — GPU/CPU speech transcription.
- **all-MiniLM-L6-v2**: Sentence-Transformers / Microsoft (Apache 2.0) — Vector embeddings.
- **Gemma 4 (26B-A4B, 12B, E4B, E2B)**: Google (Gemma Open Model License).
```
