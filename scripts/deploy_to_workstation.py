"""
Project Lucca — Deployment & Workstation Sync Utility
Promotes validated skills, templates, configs, and builds from the development
repository (C:\\Projects\\ProjectLucca) to the production deployment target (C:\\ProjectLucca).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def sync_directory(src: Path, dst: Path, clean_dst: bool = False) -> tuple[int, int]:
    """
    Copies files from src to dst. Returns (copied_count, unchanged_count).
    If clean_dst is True, removes extra files in dst not present in src.
    """
    copied = 0
    unchanged = 0

    if not src.exists():
        print(f"  [WARN] Source directory does not exist: {src}")
        return (0, 0)

    dst.mkdir(parents=True, exist_ok=True)

    # 1. Copy files
    for item in src.rglob("*"):
        if item.is_file() and not any(part.startswith(".") for part in item.parts):
            rel = item.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)

            if not target.exists() or item.read_bytes() != target.read_bytes():
                shutil.copy2(item, target)
                copied += 1
            else:
                unchanged += 1

    # 2. Clean extra files in dst if requested
    if clean_dst:
        for item in list(dst.rglob("*")):
            if item.is_file() and not any(part.startswith(".") for part in item.parts):
                rel = item.relative_to(dst)
                src_item = src / rel
                if not src_item.exists():
                    item.unlink()
                    print(f"  [PRUNE] Removed stale file: {rel}")

    return (copied, unchanged)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy software assets from C:\\Projects\\ProjectLucca to C:\\ProjectLucca"
    )
    parser.add_argument(
        "--build-exe",
        action="store_true",
        help="Compile Lucca.exe using PyInstaller and deploy binary into C:\\ProjectLucca",
    )
    parser.add_argument(
        "--pull-persona",
        action="store_true",
        help="Copy user persona from workstation (C:\\ProjectLucca) into dev repo",
    )
    parser.add_argument(
        "--push-persona",
        action="store_true",
        help="Overwrite workstation persona with repo config/persona.toml",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    workstation_root = Path(r"C:\ProjectLucca")

    if not workstation_root.exists():
        print(f"[ERROR] Workstation target does not exist at {workstation_root}")
        return 1

    print("=" * 65)
    print("  PROJECT LUCCA — DEPLOYMENT & WORKSTATION SYNC")
    print(f"  Source: {repo_root}")
    print(f"  Target: {workstation_root}")
    print("=" * 65)

    # 1. Sync Skills
    print("\n1. Synchronizing MicroScheme Skills (config/skills/)...")
    src_skills = repo_root / "config" / "skills"
    dst_skills = workstation_root / "config" / "skills"
    copied_skills, unchanged_skills = sync_directory(src_skills, dst_skills, clean_dst=True)
    print(f"   Done: {copied_skills} updated, {unchanged_skills} verified up-to-date.")

    # 2. Sync Templates
    print("\n2. Synchronizing Jinja Templates (templates/)...")
    src_templates = repo_root / "templates"
    dst_templates = workstation_root / "templates"
    copied_tmpl, unchanged_tmpl = sync_directory(src_templates, dst_templates)
    print(f"   Done: {copied_tmpl} updated, {unchanged_tmpl} verified up-to-date.")

    # 3. Sync Model Manifest
    print("\n3. Synchronizing Model Manifest (models/MANIFEST.json)...")
    src_manifest = repo_root / "models" / "MANIFEST.json"
    dst_manifest = workstation_root / "models" / "MANIFEST.json"
    if src_manifest.exists():
        if not dst_manifest.exists() or src_manifest.read_bytes() != dst_manifest.read_bytes():
            dst_manifest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_manifest, dst_manifest)
            print("   Updated models/MANIFEST.json on workstation.")
        else:
            print("   models/MANIFEST.json is identical.")

    # 4. Handle Persona
    print("\n4. Checking Persona Configuration (config/persona.toml)...")
    src_persona = repo_root / "config" / "persona.toml"
    dst_persona = workstation_root / "config" / "persona.toml"
    if args.pull_persona:
        if dst_persona.exists():
            shutil.copy2(dst_persona, src_persona)
            print("   Pulled live workstation persona.toml into dev repo.")
    elif args.push_persona:
        if src_persona.exists():
            shutil.copy2(src_persona, dst_persona)
            print("   Pushed dev repo persona.toml to workstation.")
    else:
        if dst_persona.exists() and src_persona.exists():
            differs = dst_persona.read_bytes() != src_persona.read_bytes()
            if differs:
                print("   [INFO] persona.toml differs between repo and workstation.")
                print("          Run with --pull-persona to update repo, or --push-persona to deploy.")
            else:
                print("   persona.toml is in perfect sync.")
        elif src_persona.exists() and not dst_persona.exists():
            shutil.copy2(src_persona, dst_persona)
            print("   Seeded workstation config/persona.toml from dev repo.")

    # 5. Build & Deploy Executable if requested
    if args.build_exe:
        print("\n5. Compiling Desktop Executable (Lucca.exe)...")
        from packaging.build_exe import build  # noqa: PLC0415

        res = build()
        if res != 0:
            print("[ERROR] Build failed.")
            return res
        dist_exe_dir = repo_root / "dist" / "Lucca"
        dst_bin_dir = workstation_root / "bin"
        dst_bin_dir.mkdir(parents=True, exist_ok=True)
        for f in dist_exe_dir.glob("*"):
            if f.is_file():
                shutil.copy2(f, dst_bin_dir / f.name)
        print(f"   Deployed standalone build into {dst_bin_dir}")

    print("\n" + "=" * 65)
    print("  DEPLOYMENT SYNC COMPLETE")
    print("=" * 65)
    return 0


if __name__ == "__main__":
    sys.exit(main())
