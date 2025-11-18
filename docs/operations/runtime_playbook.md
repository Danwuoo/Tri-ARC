# Runtime Playbook

Centralizes environment setup, pipeline scheduling, and deployment procedures so runbooks stay synchronized.

## Environment Setup & Tooling

Tri-ARC runs fully offline on Kaggle notebooks and local workstations that mirror the competition constraints. Follow the steps below to configure both environments.

## Common Requirements
- **Python**: 3.11.x
- **CUDA**: 12.1 (driver >= 535) or matching version supported by Kaggle runtime.
- **PyTorch**: 2.3 with CUDA support.
- **Z3**: 4.12 CLI and Python bindings.
- **Auxiliary tools**: `torchvision`, `numpy`, `scipy`, `networkx`, `hydra-core`, `pyyaml`, `rg` (ripgrep), `nsys`, `ncu`.
- **LLM runtime**: `transformers>=4.38`, `accelerate>=0.24`, and `bitsandbytes>=0.43` (CUDA build) are required to load the Qwen-2.5 Coder 7B checkpoint; fallback to the stub backend if these wheels are unavailable.
- Dependency manifests live in `requirements.txt`, `environments/conda/environment.yml`, and `environments/docker/Dockerfile`.
- Use `scripts/build/build_wheel_cache.sh` to pre-download wheels into `vendor/wheels/` and refresh `vendor/wheels/manifest.sha256` for offline installs. Override `PIP_PYTHON_VERSION`, `PIP_PLATFORM`, or `PIP_NO_BINARY` when targeting non-default environments.
- Verify GPU availability with `python scripts/check_gpu.py`.
- Capture the environment snapshot with `python scripts/self_test.py --output reports/setup_verification_<date>.md`.

## Kaggle Notebook Setup
1. **Enable GPUs**: In the notebook settings, choose four GPUs (A100 or L4 when available).
2. **Offline data**: Upload dataset archives produced by `scripts/package_data.py`. Place them under `/kaggle/input/tri-arc-data/`.
3. **Repository**: Upload the code bundle as a Kaggle dataset or copy from the competition data tab. Extract to `/kaggle/working/Tri-ARC/`.
4. **Environment bootstrap**: run the following notebook cell (Python, not Bash) at the top of your Kaggle notebook to install dependencies directly inside the runtime:
   ```python
   import os
   import subprocess
   import sys
   from pathlib import Path

   project_root = Path("/kaggle/working/Tri-ARC")
   wheel_root = project_root / "vendor" / "wheels"
   requirements = project_root / "requirements.txt"

   allow_pypi = os.environ.get("TRI_ARC_ALLOW_PYPI", "0") == "1"
   extra_index = os.environ.get(
       "TRI_ARC_PIP_EXTRA_INDEX_URL",
       "https://download.pytorch.org/whl/cu121",
   )

   def run(cmd):
       print(f"[Tri-ARC] {' '.join(cmd)}")
       subprocess.check_call(cmd)

   try:
       run(
           [
               sys.executable,
               "-m",
               "pip",
               "install",
               "--no-index",
               "--find-links",
               str(wheel_root),
               "-r",
               str(requirements),
           ]
       )
   except subprocess.CalledProcessError:
       if not allow_pypi:
           raise
       print("[Tri-ARC] Offline install failed; falling back to PyPI.")
       run(
           [
               sys.executable,
               "-m",
               "pip",
               "install",
               "--extra-index-url",
               extra_index,
               "-r",
               str(requirements),
           ]
       )

   run([sys.executable, "--version"])
   run([sys.executable, "-m", "pip", "--version"])
   ```
   (Upload `vendor/wheels/` as a Kaggle dataset so the offline install succeeds. Set `TRI_ARC_ALLOW_PYPI=1` only when the competition rules allow hitting PyPI.)
5. **GPU pinning**: Use `CUDA_VISIBLE_DEVICES=0,1,2,3 python scripts/run_eval.py ...` to align with the device map in `docs/CONFIG_DEFAULTS.yaml`.
6. **Logging**: Redirect logs to `/kaggle/temp/` to avoid quota issues on `/kaggle/working/`.

## Local Offline Setup
1. **Hardware**: Workstation with >=4 GPUs (A100, L40, or similar), 64 CPU cores, 128 GB RAM.
2. **Clone repository**: `git clone git@.../Tri-ARC.git` (offline mirror). Verify submodules if used.
3. **Conda environment**:
   ```
   bash scripts/setup_local_env.sh
   ```
4. **GPU assignment**: Export `CUDA_VISIBLE_DEVICES=0,1,2,3`. For split deployments (e.g., limited GPUs), edit `docs/CONFIG_DEFAULTS.yaml` to reflect available devices.
5. **Data staging**: Place datasets under `data/arcagi2/` and ARC-Forge outputs in `data/arc_forge/`. Ensure paths match config.
6. **Licences**: Confirm third-party licences are compatible with offline redistribution.

## Version Pinning
- Capture dependency hashes using `pip freeze > reports/pip_freeze.txt`.
- Record `nvidia-smi` output in `reports/gpu_info.txt`.
- Tag repository with `env-<date>` when environment changes and update `CHANGELOG.md`.

## Verification
1. Run `python scripts/self_test.py --output reports/setup_verification_<date>.md` to confirm module imports, CUDA kernels, and Z3 availability.
2. Generate the asset manifest with `python scripts/inventory_assets.py --json reports/offline_inventory_<date>.json`.
3. Execute `python scripts/run_eval.py --split smoke --max_tasks 5` to validate end-to-end operation within 15 minutes (Stage 2 onwards).
4. Log outputs in `reports/smoke_logs/`.
5. Update `docs/compliance/LICENCE_LOG.md` with new bundles before publishing artifacts.

## Symbolic Heuristic Weights
- Build deterministic TorchScript weights for the neural heuristic with `python scripts/build/build_symbolic_heuristic.py`. The script emits `models/symbolic/heuristic.pt` and a checksum manifest `models/symbolic/heuristic.sha256`.
- The checksum manifest records the SHA256 hash and metadata (seed, layer layout). Upload both files with the offline bundle so `docs/MODULES/SYMBOLIC.md` requirements are satisfied.
- Package the weights plus checksum into a distributable archive with `python scripts/build/package_symbolic_heuristic_bundle.py --output dist/heuristics/symbolic_heuristic_bundle.zip`.
- After a smoke run, compare rule-based versus neural contributions using `python scripts/analysis/compare_heuristics.py --tasks-dir reports/eval_runs/smoke/<run>/tasks` and attach the summary to Phase 2 reports.
- Use `python tools/compare_heuristics.py --mode neural_only --mode rule_only --input-dir data/arcagi2/smoke` when you need an end-to-end runtime comparison between heuristic modes.

## Pipeline Operations

This playbook captures the day-to-day procedures requested for Stage 1: feeding data through `DatasetLoader`, managing logging, and supervising the fallback strategy inside the arbitrator. Each section is actionable so it can be followed directly from a terminal session.

## DatasetLoader 操作手冊

1. **快速健康檢查**：確認資料根目錄（預設 `data/arcagi2`）存在後，執行：

   ```bash
   python - <<'PY'
   from pathlib import Path
   from arc.data.loader import DatasetLoader

   loader = DatasetLoader(Path("data/arcagi2"), enable_checksums=True)
   record = next(loader.iter_split("smoke", limit=1))
   print(record.task_id, record.path, record.payload["metadata"])
   PY
   ```

   這會驗證 JSON 可讀性、補上 `task_id`/`split`/`checksum`，並確保 smoke split 至少有一筆可處理的任務。

2. **子集執行**：透過 `iter_split(..., task_ids=[...])` 或 `exclude_task_ids=[...]` 可以鎖定/排除特定任務，常見於 incident replay。`limit` 參數（或 `--max-tasks`）能在 E2E 測試時縮短回饋週期。

3. **Metadata 約定**：`DatasetLoader` 會在 payload 中加入
   - `metadata.relative_path`, `source_split`, `checksum`
   - `train_example_shapes`/`eval_example_shapes`
   這些欄位 downstream（Scheduler、Symbolic、Arbitrator）都會記錄到報表與決策檔，因此不要手動刪除；若要新增欄位請在 `loader._extract_metadata` 補齊，並更新對應文件。

## Logging 操作手冊

1. **統一入口**：所有 CLI（含 `scripts/run_eval.py`）都呼叫 `arc.logging_utils.configure_logging`，並依 `logging.*` 配置決定
   - `level`
   - 旋轉檔案大小（`log_max_bytes_mb`）與保留份數（`log_backup_count`）
   - 是否壓縮（`compress_rotated_logs`）

2. **自訂範例**：在 preset（如 `configs/eval/smoke.yaml`）中覆寫：

   ```yaml
   logging:
     level: DEBUG
     log_max_bytes_mb: 2
     log_backup_count: 2
   ```

   重新執行 `python scripts/run_eval.py --preset smoke --split smoke` 即會把 runtime log 寫到 `<run_dir>/logs/runtime.log`，同時保留 console streaming，方便 CI 與終端同步追蹤。

3. **檢視與清理**：`logs/runtime.log`、`logs/scheduler/*.log`、`logs/arbitrator/verification/*.json` 都支援 gzip 旋轉；如需重置僅刪除對應檔案即可，切勿 `git clean` 以免誤刪 run 產物。

## Fallback 策略操作手冊

1. **觸發條件**：Stage 1 後，fallback 僅在「沒有任何模組提供通過驗證的候選」時啟動。低置信度不再強迫 fallback，因此報表上的 fallback 代表真正沒有可用解。

2. **檢視決策**：
   - `reports/arbitration_summary_<DATE>.md`：摘要每個任務的 `Fallback used`、理由與被拒絕候選。
   - `logs/arbitrator/decisions/<task>.json`：包含逐候選分數、SMT 驗證狀態與觸發原因。
   - `tools/inspect_arbitrator.py --task <id> --show-traces`：可交叉連結 verification trace 與 `outputs/pass2.json`。

3. **策略調整**：若想停用 fallback，直接在 `arbitrator` 設定中新增 `enable_fallback: false`（需同步更新此文件）；若要新增策略，請在 `arc/arbitration/fallbacks.py` 實作並於此處記錄用途與驗證方式。完成後，務必重新跑 `scripts/run_eval.py --preset smoke --split smoke` 以確保 `pass2.json` 與報表一致。

4. **健康檢查**：每次評測後執行 `rg "missing_smt_token" reports/arbitration_summary_*.md` 應無結果，`outputs/pass2.json` 必須覆蓋並包含所有 smoke 任務；若 fallback 使用率異常升高，優先檢查 Symbolic/LLM/TTT 的候選是否因 metadata/SR 失敗被拒絕。

這份操作手冊應與 `DEVELOPMENT_PHASES.md` 搭配使用，確保 Stage 1 的核心管線（DatasetLoader → Scheduler/Modules → Arbitrator）能穩定重現 smoke split。若流程有任何新增參數或 CLI，請同步回填此檔。

## Deployment Runbook

## Quick Start

### Pre-Deployment Checklist

```bash
# 1. Verify environment
python scripts/check_gpu.py
python scripts/self_test.py

# 2. Create deployment package
python scripts/create_deployment_package.py --root . --output-dir dist/deployment --include-data

# 3. Run validation
python scripts/deploy.py --root . --output-dir dist/deployment

# 4. Final evaluation
python scripts/run_eval.py --preset evaluation --split evaluation --run-id final

# 5. Create submission
python tools/make_submission.py --pass2 outputs/pass2.json --output submission.json
```

## Common Operations

### 1. Environment Setup

#### Fresh Installation

```bash
# Clone and setup
git clone <repo-url> tri-arc
cd tri-arc
bash scripts/setup_local_env.sh
source .venv/bin/activate
```

#### Update Dependencies

```bash
# Update requirements
pip install -r requirements.txt --upgrade

# Verify
python scripts/self_test.py
```

### 2. Configuration Management

#### View Current Configuration

```bash
# Default configuration
cat docs/CONFIG_DEFAULTS.yaml

# Symbolic configuration
cat configs/symbolic/enhanced.yaml
```

#### Modify Configuration

```bash
# Create custom config
cp configs/symbolic/enhanced.yaml configs/symbolic/custom.yaml

# Edit as needed
vim configs/symbolic/custom.yaml

# Use custom config
python scripts/run_eval.py --config-name custom
```

### 3. Running Evaluations

#### Smoke Test (Quick)

```bash
python scripts/run_eval.py --preset smoke --split smoke --max_tasks 5
```

#### Full Evaluation

```bash
python scripts/run_eval.py --preset evaluation --split evaluation --run-id eval-$(date +%Y%m%d)
```

#### Resume Interrupted Run

```bash
python scripts/run_eval.py --resume-from reports/eval_runs/<run-id>
```

### 4. Monitoring

#### Real-Time Monitoring

```bash
# Terminal 1: GPU monitoring
watch -n 1 nvidia-smi

# Terminal 2: Log monitoring
tail -f logs/symbolic/solve_progress.jsonl

# Terminal 3: System monitoring
htop
```

#### Check Progress

```bash
# Count completed tasks
grep -c '"status":"solved"' logs/symbolic/solve_progress.jsonl

# View recent errors
grep '"status":"error"' logs/symbolic/solve_progress.jsonl | tail -n 10
```

### 5. Troubleshooting

#### Check Logs

```bash
# Symbolic solver logs
tail -n 100 logs/symbolic/symbolic_frontier.log

# SMT verification logs
tail -n 100 logs/smt/verification.log

# Arbitrator logs
tail -n 100 logs/arbitrator/decisions.log
```

#### Debug Mode

```bash
# Enable debug logging
export TRI_ARC_LOG_LEVEL=DEBUG

# Run with debug output
python scripts/run_eval.py --preset smoke --split smoke 2>&1 | tee debug.log
```

#### Memory Issues

```bash
# Check memory usage
free -h

# Check GPU memory
nvidia-smi

# Clear cache
python -c "import torch; torch.cuda.empty_cache()"
```

### 6. Performance Analysis

#### Generate Reports

```bash
# Evaluation summary
cat reports/eval_summary.md

# Detailed metrics
python scripts/validate_success_metrics.py --output reports/metrics.json

# Dashboard data
python arc/symbolic/evaluation/dashboard.py \
    --run-dir reports/eval_runs/<run-id> \
    --output dist/dashboard.json
```

#### Compare Runs

```bash
python tools/compare_runs.py \
    reports/eval_runs/run-a \
    reports/eval_runs/run-b
```

#### Ablation Studies

```bash
python scripts/run_ablation_study.py --preset smoke --split smoke
```

## Emergency Procedures

### 1. Out of Memory (OOM)

#### Symptoms
- `RuntimeError: CUDA out of memory`
- Process killed by OOM killer
- System becomes unresponsive

#### Immediate Actions

```bash
# 1. Stop running processes
pkill -f run_eval.py

# 2. Clear GPU memory
python -c "import torch; torch.cuda.empty_cache()"

# 3. Reduce resource usage
# Edit configs/symbolic/enhanced.yaml
```

```yaml
symbolic:
  search:
    max_expansions: 2000  # Reduce from 5000
    max_nodes: 20000      # Reduce from 50000
  engineering:
    cache:
      program_cache_size: 3000  # Reduce from 10000
```

```bash
# 4. Restart evaluation
python scripts/run_eval.py --resume-from <run-dir>
```

### 2. Timeout Issues

#### Symptoms
- Many tasks timing out
- Evaluation taking too long
- Soft/hard timeout exceeded

#### Immediate Actions

```bash
# 1. Check current timeouts
grep "timeout" configs/symbolic/enhanced.yaml

# 2. Increase timeouts
```

```yaml
symbolic:
  search:
    soft_timeout_s: 150.0  # Increase from 90.0
    hard_timeout_s: 200.0  # Increase from 150.0
```

```bash
# 3. Enable early pruning
```

```yaml
symbolic:
  search:
    enable_early_pruning: true
  egraph:
    enabled: true  # Helps reduce search space
```

### 3. Non-Deterministic Results

#### Symptoms
- Different results with same seed
- Reproducibility validation fails

#### Immediate Actions

```bash
# 1. Verify seed configuration
python scripts/validate_deterministic_execution.py --root .

# 2. Check for race conditions
# Review parallel code sections

# 3. Force deterministic mode
```

```python
# Add to solver initialization
import torch
torch.backends.cudnn.deterministic = True
torch.backends.cudnn.benchmark = False
```

### 4. SMT Solver Failures

#### Symptoms
- Z3 timeouts
- Verification failures
- Circuit breaker triggered

#### Immediate Actions

```bash
# 1. Check SMT logs
tail -n 100 logs/smt/verification.log

# 2. Increase timeout
```

```yaml
symbolic:
  smt:
    timeout_per_candidate: 5.0  # Increase from 2.0
```

```bash
# 3. Enable fallback
```

```yaml
symbolic:
  smt:
    circuit_breaker:
      enabled: true
      failure_threshold: 5
    fallback_verification: true
```

### 5. Evaluation Stuck

#### Symptoms
- No progress for extended period
- Process appears hung
- No log updates

#### Immediate Actions

```bash
# 1. Check if process is running
ps aux | grep run_eval

# 2. Check system resources
top
nvidia-smi

# 3. Send interrupt signal (graceful)
pkill -INT -f run_eval.py

# 4. If no response, force kill
pkill -KILL -f run_eval.py

# 5. Resume from checkpoint
python scripts/run_eval.py --resume-from <run-dir>
```

## Maintenance Operations

### 1. Clean Up

#### Remove Old Logs

```bash
# Archive old logs
tar -czf logs_archive_$(date +%Y%m%d).tar.gz logs/
mv logs_archive_*.tar.gz archives/

# Clean logs directory
find logs/ -type f -mtime +30 -delete
```

#### Clear Cache

```bash
# Clear symbolic cache
rm -rf cache/symbolic/*

# Clear temporary files
rm -rf cache/tmp_antl/*
```

### 2. Backup

#### Create Backup

```bash
# Backup critical files
tar -czf backup_$(date +%Y%m%d).tar.gz \
    configs/ \
    models/ \
    data/ \
    reports/eval_summary.md

# Move to backup location
mv backup_*.tar.gz /backup/location/
```

#### Restore from Backup

```bash
# Extract backup
tar -xzf backup_YYYYMMDD.tar.gz

# Verify integrity
python scripts/inventory_assets.py --root . --json verify.json
```

### 3. Updates

#### Update Code

```bash
# Pull latest changes
git pull origin main

# Update dependencies
pip install -r requirements.txt --upgrade

# Run tests
pytest tests/

# Verify
python scripts/self_test.py
```

#### Update Models

```bash
# Download new model weights
# Place in models/ directory

# Verify checksums
sha256sum models/symbolic/*.pt
```

## Deployment Scenarios

### Scenario 1: Local Development

```bash
# Setup
bash scripts/setup_local_env.sh
source .venv/bin/activate

# Quick test
python scripts/run_eval.py --preset smoke --split smoke

# Full evaluation
python scripts/run_eval.py --preset evaluation --split evaluation
```

### Scenario 2: Kaggle Submission

```bash
# Setup Kaggle environment
bash scripts/setup_kaggle_env.sh

# Create deployment package
python scripts/create_deployment_package.py \
    --root . \
    --output-dir dist/kaggle \
    --include-data

# Validate
python scripts/deploy.py --root . --output-dir dist/kaggle

# Create submission
python tools/make_submission.py \
    --pass2 outputs/pass2.json \
    --output submission.json
```

### Scenario 3: Production Deployment

```bash
# Full validation
python scripts/deploy.py --root . --output-dir dist/production

# Run final evaluation
python scripts/run_eval.py \
    --preset evaluation \
    --split evaluation \
    --run-id production-$(date +%Y%m%d)

# Verify metrics
python scripts/validate_success_metrics.py

# Create deployment package
python scripts/create_deployment_package.py \
    --root . \
    --output-dir dist/production \
    --include-data

# Archive
tar -czf production_deployment_$(date +%Y%m%d).tar.gz dist/production/
```

## Monitoring Dashboards

### System Health

```bash
# GPU utilization
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv -l 1

# CPU and memory
vmstat 1

# Disk I/O
iostat -x 1
```

### Application Metrics

```bash
# Task completion rate
watch -n 5 'grep -c "solved" logs/symbolic/solve_progress.jsonl'

# Average solve time
jq -r '.elapsed_s' logs/symbolic/solve_progress.jsonl | awk '{sum+=$1; count++} END {print sum/count}'

# Success rate
jq -r '.status' logs/symbolic/solve_progress.jsonl | sort | uniq -c
```

## Contact and Escalation

### Log Collection

```bash
# Collect logs for support
tar -czf support_logs_$(date +%Y%m%d_%H%M%S).tar.gz \
    logs/ \
    reports/ \
    configs/ \
    dist/deployment/deployment_report.json

# Include system info
nvidia-smi > system_info.txt
uname -a >> system_info.txt
pip freeze >> system_info.txt
```

### Issue Reporting

Include the following information:
1. System configuration (GPU, RAM, OS)
2. Error messages and stack traces
3. Relevant log files
4. Steps to reproduce
5. Expected vs actual behavior

## Appendix

### Useful Commands

```bash
# Quick status check
python scripts/check_gpu.py && \
python scripts/self_test.py && \
echo "System ready"

# Full validation
python scripts/deploy.py --root . --output-dir dist/validation

# Emergency stop
pkill -INT -f run_eval.py

# Resume evaluation
python scripts/run_eval.py --resume-from $(ls -td reports/eval_runs/* | head -1)
```

### Configuration Templates

#### Minimal Configuration

```yaml
symbolic:
  enabled: true
  device: "cuda:2"
  search:
    strategy: "dfs"
    max_depth: 8
    max_expansions: 1000
  egraph:
    enabled: false
  cegis:
    enabled: false
  smt:
    enabled: false
```

#### Maximum Performance

```yaml
symbolic:
  enabled: true
  device: "cuda:2"
  search:
    strategy: "beam"
    max_depth: 15
    max_expansions: 10000
    beam_width: 200
  egraph:
    enabled: true
    rewrite_limit: 10000
  cegis:
    enabled: true
    max_iterations: 15
  smt:
    enabled: true
    batch_size: 20
```

### Resource Limits

| Resource | Warning | Error | Action |
|----------|---------|-------|--------|
| GPU Memory | 80% | 95% | Reduce cache sizes |
| CPU Usage | 80% | 95% | Reduce parallelism |
| RAM Usage | 80% | 95% | Clear caches |
| Disk Space | 80% | 95% | Clean logs |
| Evaluation Time | 10h | 12h | Optimize config |
