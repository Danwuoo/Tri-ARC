# Deployment Runbook

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
