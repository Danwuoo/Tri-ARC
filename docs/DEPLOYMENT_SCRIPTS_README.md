# Deployment Scripts Reference

## Overview

This directory contains automated deployment scripts for the Tri-ARC Symbolic Synthesis Enhancement system. These scripts handle packaging, validation, and submission preparation.

## Main Scripts

### 1. `deploy.py` - Main Deployment Orchestrator

**Purpose**: Coordinates the complete deployment process.

**Usage**:
```bash
# Full deployment with validation
python scripts/deploy.py --root . --output-dir dist/deployment

# Quick deployment (skip validation)
python scripts/deploy.py --root . --output-dir dist/deployment --skip-validation
```

**What it does**:
1. Creates deployment package
2. Validates deterministic execution
3. Validates resource constraints
4. Runs final validation
5. Prepares submission artifacts
6. Generates deployment report

### 2. `create_deployment_package.py` - Package Creator

**Purpose**: Creates offline deployment package with all assets.

**Usage**:
```bash
python scripts/create_deployment_package.py \
    --root . \
    --output-dir dist/deployment \
    --include-data
```

**Collects**:
- Model weights
- DSL library files
- Configuration files
- Deployment scripts
- Symbolic enhancement modules
- Optional: ARC-AGI-2 dataset

**Outputs**:
- `symbolic-deployment-YYYYMMDD-HHMMSS.tar.gz`
- `symbolic-deployment-YYYYMMDD-HHMMSS_manifest.json`
- `symbolic-deployment-YYYYMMDD-HHMMSS_summary.json`

### 3. `validate_deterministic_execution.py` - Determinism Validator

**Purpose**: Verifies deterministic execution and reproducibility.

**Usage**:
```bash
python scripts/validate_deterministic_execution.py \
    --root . \
    --output reports/deterministic_validation.json

# Skip reproducibility test (faster)
python scripts/validate_deterministic_execution.py \
    --root . \
    --output reports/deterministic_validation.json \
    --skip-reproducibility
```

**Validates**:
- Seed usage across codebase
- Configuration determinism
- Checkpoint functionality
- Reproducibility (3 runs with same seed)

### 4. `validate_resource_constraints.py` - Resource Validator

**Purpose**: Validates resource usage and constraints.

**Usage**:
```bash
python scripts/validate_resource_constraints.py \
    --root . \
    --output reports/resource_validation.json
```

**Checks**:
- GPU memory usage (80% warning, 95% error)
- CPU and RAM usage
- 12-hour time constraint
- Circuit breaker functionality
- Timeout protection

### 5. `run_final_validation.py` - Final Validator

**Purpose**: Conducts comprehensive final validation.

**Usage**:
```bash
# Full validation (includes evaluation)
python scripts/run_final_validation.py \
    --root . \
    --output-dir dist/final_validation

# Skip evaluation (for testing)
python scripts/run_final_validation.py \
    --root . \
    --output-dir dist/final_validation \
    --skip-evaluation
```

**Performs**:
1. Full evaluation on validation set
2. Success metrics verification
3. Code review checks
4. Changelog update

### 6. `prepare_submission_artifacts.py` - Artifact Preparer

**Purpose**: Prepares all submission artifacts.

**Usage**:
```bash
python scripts/prepare_submission_artifacts.py \
    --root . \
    --output-dir dist/submission
```

**Generates**:
1. Evaluation reports (consolidated)
2. Performance charts (JSON + markdown)
3. Code and documentation package
4. Presentation materials

## Quick Start

### Complete Deployment

```bash
# One-command deployment
python scripts/deploy.py --root . --output-dir dist/deployment
```

### Step-by-Step Deployment

```bash
# Step 1: Create package
python scripts/create_deployment_package.py \
    --root . \
    --output-dir dist/deployment \
    --include-data

# Step 2: Validate determinism
python scripts/validate_deterministic_execution.py \
    --root . \
    --output reports/deterministic.json

# Step 3: Validate resources
python scripts/validate_resource_constraints.py \
    --root . \
    --output reports/resources.json

# Step 4: Final validation
python scripts/run_final_validation.py \
    --root . \
    --output-dir dist/validation

# Step 5: Prepare artifacts
python scripts/prepare_submission_artifacts.py \
    --root . \
    --output-dir dist/submission
```

## Output Structure

```
dist/
├── deployment/
│   ├── symbolic-deployment-YYYYMMDD-HHMMSS.tar.gz
│   ├── symbolic-deployment-YYYYMMDD-HHMMSS_manifest.json
│   ├── symbolic-deployment-YYYYMMDD-HHMMSS_summary.json
│   ├── requirements.txt
│   ├── wheels/
│   ├── deterministic_validation.json
│   ├── resource_validation.json
│   └── deployment_report.json
│
├── final_validation/
│   ├── final_validation_report.json
│   └── success_metrics.json
│
└── submission/
    ├── reports/
    │   ├── eval_summary.md
    │   ├── eval_history.md
    │   ├── consolidated_report.md
    │   └── latest_run/
    ├── charts/
    │   ├── performance_data.json
    │   └── performance_charts.md
    ├── package/
    │   ├── arc/symbolic/
    │   ├── docs/
    │   ├── configs/
    │   └── README.md
    ├── presentation/
    │   ├── presentation_outline.md
    │   ├── executive_summary.md
    │   └── technical_highlights.md
    └── artifact_manifest.json
```

## Common Workflows

### Pre-Deployment Validation

```bash
# Quick validation
python scripts/validate_deterministic_execution.py --root . --skip-reproducibility
python scripts/validate_resource_constraints.py --root .
```

### Create Deployment Package Only

```bash
python scripts/create_deployment_package.py \
    --root . \
    --output-dir dist/package \
    --include-data
```

### Prepare Submission Only

```bash
python scripts/prepare_submission_artifacts.py \
    --root . \
    --output-dir dist/submission
```

## Troubleshooting

### Script Fails

1. Check Python version (3.11+ required)
2. Verify all dependencies installed
3. Check file permissions
4. Review error messages in output

### Validation Fails

1. Review validation report JSON files
2. Check logs in `logs/` directory
3. Verify GPU availability (if needed)
4. Ensure dataset is present

### Package Creation Fails

1. Verify all source files exist
2. Check disk space
3. Ensure write permissions
4. Review manifest for missing files

## Environment Variables

```bash
# Optional environment variables
export TRI_ARC_ROOT=/path/to/tri-arc
export TRI_ARC_DATA_ROOT=/path/to/data
export TRI_ARC_LOG_LEVEL=INFO
```

## Exit Codes

- `0`: Success
- `1`: Failure (check output for details)

## Dependencies

All scripts require:
- Python 3.11+
- Dependencies from `requirements.txt`
- Optional: GPU for full validation

## Documentation

For detailed information, see:
- [Deployment Guide](../docs/DEPLOYMENT_GUIDE.md)
- [Deployment Runbook](../docs/DEPLOYMENT_RUNBOOK.md)
- [Troubleshooting Guide](symbolic/troubleshooting.md)

## Support

For issues:
1. Check documentation
2. Review log files
3. Verify environment setup
4. Contact development team
