# Pipeline Operations (Stage 1)

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
