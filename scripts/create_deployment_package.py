#!/usr/bin/env python3
"""
Create deployment package for Tri-ARC symbolic synthesis enhancements.

Packages all model weights, DSL library, configuration files, and creates
an offline bundle suitable for Kaggle submission.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def compute_checksum(path: Path) -> str:
    """Compute SHA256 checksum of a file."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_model_weights(root: Path) -> List[Path]:
    """Collect all model weight files."""
    models_dir = root / "models"
    if not models_dir.exists():
        return []
    
    weight_files = []
    for pattern in ["*.pt", "*.pth", "*.ckpt", "*.safetensors", "*.bin"]:
        weight_files.extend(models_dir.rglob(pattern))
    
    return sorted(weight_files)


def collect_dsl_library(root: Path) -> List[Path]:
    """Collect DSL library files."""
    dsl_files = []
    
    # Core DSL files
    dsl_dir = root / "arc" / "symbolic" / "dsl"
    if dsl_dir.exists():
        dsl_files.extend(dsl_dir.rglob("*.py"))
    
    # Library state files
    library_dir = root / "arc" / "symbolic" / "library"
    if library_dir.exists():
        dsl_files.extend(library_dir.rglob("*.py"))
        dsl_files.extend(library_dir.rglob("*.json"))
        dsl_files.extend(library_dir.rglob("*.yaml"))
    
    # Fixtures and test data
    fixtures_dir = root / "fixtures" / "dsl"
    if fixtures_dir.exists():
        dsl_files.extend(fixtures_dir.rglob("*"))
    
    return sorted(dsl_files)


def collect_config_files(root: Path) -> List[Path]:
    """Collect configuration files."""
    config_files = []
    
    # Main configs
    configs_dir = root / "configs"
    if configs_dir.exists():
        config_files.extend(configs_dir.rglob("*.yaml"))
        config_files.extend(configs_dir.rglob("*.json"))
    
    # Documentation configs
    docs_dir = root / "docs"
    if docs_dir.exists():
        config_files.append(docs_dir / "CONFIG_DEFAULTS.yaml")
    
    # Root config
    if (root / "config.py").exists():
        config_files.append(root / "config.py")
    
    return sorted([f for f in config_files if f.exists()])


def collect_deployment_scripts(root: Path) -> List[Path]:
    """Collect deployment and setup scripts."""
    scripts = []
    scripts_dir = root / "scripts"
    
    if scripts_dir.exists():
        # Setup scripts
        scripts.extend(scripts_dir.glob("setup_*.sh"))
        scripts.extend(scripts_dir.glob("setup_*.py"))
        
        # Evaluation scripts
        for script_name in [
            "run_eval.py",
            "run_symbolic_evaluation.py",
            "validate_success_metrics.py",
            "check_gpu.py",
        ]:
            script_path = scripts_dir / script_name
            if script_path.exists():
                scripts.append(script_path)
    
    # Tools
    tools_dir = root / "tools"
    if tools_dir.exists():
        if (tools_dir / "make_submission.py").exists():
            scripts.append(tools_dir / "make_submission.py")
    
    return sorted(scripts)


def collect_symbolic_enhancements(root: Path) -> List[Path]:
    """Collect all symbolic enhancement modules."""
    symbolic_dir = root / "arc" / "symbolic"
    if not symbolic_dir.exists():
        return []
    
    enhancement_files = []
    
    # All Python files in symbolic module
    enhancement_files.extend(symbolic_dir.rglob("*.py"))
    
    # Enhancement-specific data files
    for subdir in [
        "ir",
        "library",
        "egraph",
        "verification",
        "smt",
        "symmetry",
        "search",
        "decomposition",
        "coordination",
        "engineering",
        "evaluation",
    ]:
        subdir_path = symbolic_dir / subdir
        if subdir_path.exists():
            enhancement_files.extend(subdir_path.rglob("*.json"))
            enhancement_files.extend(subdir_path.rglob("*.yaml"))
    
    return sorted(enhancement_files)


def create_manifest(
    root: Path,
    files: List[Path],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    """Create deployment manifest with file checksums."""
    manifest = {
        "metadata": metadata,
        "files": [],
    }
    
    for file_path in files:
        if not file_path.exists() or not file_path.is_file():
            continue
        
        rel_path = file_path.relative_to(root)
        checksum = compute_checksum(file_path)
        
        manifest["files"].append({
            "path": str(rel_path).replace("\\", "/"),
            "size_bytes": file_path.stat().st_size,
            "sha256": checksum,
        })
    
    return manifest


def create_tarball(
    root: Path,
    files: List[Path],
    output_path: Path,
) -> None:
    """Create compressed tarball of deployment files."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with tarfile.open(output_path, "w:gz") as tar:
        for file_path in files:
            if not file_path.exists() or not file_path.is_file():
                continue
            arcname = file_path.relative_to(root)
            tar.add(file_path, arcname=arcname)


def create_requirements_bundle(root: Path, output_dir: Path) -> Path:
    """Bundle requirements.txt and wheel cache."""
    requirements_file = root / "requirements.txt"
    if not requirements_file.exists():
        raise FileNotFoundError(f"requirements.txt not found at {requirements_file}")
    
    # Copy requirements.txt
    output_requirements = output_dir / "requirements.txt"
    shutil.copy2(requirements_file, output_requirements)
    
    # Copy wheel cache if exists
    wheel_dir = root / "vendor" / "wheels"
    if wheel_dir.exists():
        output_wheels = output_dir / "wheels"
        if output_wheels.exists():
            shutil.rmtree(output_wheels)
        shutil.copytree(wheel_dir, output_wheels)
    
    return output_requirements


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create deployment package for symbolic synthesis enhancements"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Project root directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist/deployment"),
        help="Output directory for deployment package",
    )
    parser.add_argument(
        "--bundle-name",
        type=str,
        default=None,
        help="Name for the deployment bundle (default: symbolic-deployment-YYYYMMDD-HHMMSS)",
    )
    parser.add_argument(
        "--include-data",
        action="store_true",
        help="Include ARC-AGI-2 dataset in bundle",
    )
    args = parser.parse_args()
    
    root = args.root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate bundle name
    if args.bundle_name:
        bundle_name = args.bundle_name
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        bundle_name = f"symbolic-deployment-{timestamp}"
    
    print(f"[Deployment] Creating package: {bundle_name}")
    print(f"[Deployment] Root: {root}")
    print(f"[Deployment] Output: {output_dir}")
    
    # Collect all files
    print("[Deployment] Collecting files...")
    all_files = []
    
    model_weights = collect_model_weights(root)
    print(f"  - Model weights: {len(model_weights)} files")
    all_files.extend(model_weights)
    
    dsl_library = collect_dsl_library(root)
    print(f"  - DSL library: {len(dsl_library)} files")
    all_files.extend(dsl_library)
    
    config_files = collect_config_files(root)
    print(f"  - Configuration: {len(config_files)} files")
    all_files.extend(config_files)
    
    deployment_scripts = collect_deployment_scripts(root)
    print(f"  - Deployment scripts: {len(deployment_scripts)} files")
    all_files.extend(deployment_scripts)
    
    symbolic_enhancements = collect_symbolic_enhancements(root)
    print(f"  - Symbolic enhancements: {len(symbolic_enhancements)} files")
    all_files.extend(symbolic_enhancements)
    
    # Include dataset if requested
    if args.include_data:
        data_dir = root / "data" / "arcagi2"
        if data_dir.exists():
            data_files = list(data_dir.rglob("*.json"))
            print(f"  - Dataset: {len(data_files)} files")
            all_files.extend(data_files)
    
    # Remove duplicates
    all_files = sorted(set(all_files))
    print(f"[Deployment] Total files: {len(all_files)}")
    
    # Create manifest
    print("[Deployment] Creating manifest...")
    metadata = {
        "bundle_name": bundle_name,
        "created_at": datetime.now().isoformat(),
        "project": "Tri-ARC Symbolic Synthesis Enhancements",
        "version": "1.0.0",
        "total_files": len(all_files),
    }
    
    manifest = create_manifest(root, all_files, metadata)
    manifest_path = output_dir / f"{bundle_name}_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"[Deployment] Manifest written to: {manifest_path}")
    
    # Create tarball
    print("[Deployment] Creating tarball...")
    tarball_path = output_dir / f"{bundle_name}.tar.gz"
    create_tarball(root, all_files, tarball_path)
    tarball_checksum = compute_checksum(tarball_path)
    print(f"[Deployment] Tarball created: {tarball_path}")
    print(f"[Deployment] Tarball SHA256: {tarball_checksum}")
    
    # Bundle requirements
    print("[Deployment] Bundling requirements...")
    requirements_path = create_requirements_bundle(root, output_dir)
    print(f"[Deployment] Requirements bundled to: {output_dir}")
    
    # Create deployment summary
    summary = {
        "bundle_name": bundle_name,
        "created_at": metadata["created_at"],
        "tarball": {
            "path": str(tarball_path.relative_to(output_dir)),
            "size_bytes": tarball_path.stat().st_size,
            "sha256": tarball_checksum,
        },
        "manifest": {
            "path": str(manifest_path.relative_to(output_dir)),
            "total_files": len(all_files),
        },
        "requirements": {
            "path": str(requirements_path.relative_to(output_dir)),
        },
    }
    
    summary_path = output_dir / f"{bundle_name}_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"[Deployment] Summary written to: {summary_path}")
    
    print(f"\n[Deployment] Package created successfully!")
    print(f"  Bundle: {tarball_path}")
    print(f"  Size: {tarball_path.stat().st_size / (1024**2):.2f} MB")
    print(f"  Files: {len(all_files)}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
