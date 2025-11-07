# 階段一：核心管線整備
- **工作內容**：鎖定 Symbolic/Scheduler/Arbitrator 既有工作流，完成 heuristics 權重校準、SMT 關聯設定（先行禁用或以虛擬 token 迴避）與 `scripts/run_eval.py --split smoke` 的端到端驗證，同步補齊 `DatasetLoader`、logging、fallback 策略的操作手冊。
- **完成條件**：在 smoke split 上能穩定產出 `outputs/pass2.json`，Symbolic 候選附帶有效 metadata/smt_token，Scheduler 報表與 `reports/arbitration_summary_*.md` 無錯誤，且 fallback 僅在無候選時啟用。

# 階段二：DSL 與 Symbolic 精進
- **工作內容**：依未解題型態擴增 DSL primitives、補強靜態 lint/型別檢查、完成 `models/symbolic/heuristic.pt` 打包與 rule-based/neural heuristic 權重比較、擴寫 E-Graph rewrite 規則並更新 `CONFIG_DEFAULTS.yaml` 參數，再調整 `max_depth`、`beam_width`、`max_nodes` 等探索上限。
- **完成條件**：DSL_SPEC 與 primitives registry 更新且通過 `DSLInterpreter` 測試；SymbolicSolver 可載入新的神經 heuristic（或在配置中可切換），E-Graph rewrite 規則集生效，並於 smoke 任務實測較舊版本至少提升成功題數或縮短平均探索時間。

# 階段三：TTT 模組實裝
- **工作內容**：依計畫完成卷積/淺層 self-attention Backbone、資料增強（對稱變換、調色、雜訊）、復數損失（重建＋顏色守恆＋物件數＋平滑度）與 16 步 AdamW 微調流程，實作 `TTTModule` 候選包裝、信心估計與失敗回退策略，並與 `VerificationRunner` 對接。
- **完成條件**：`arc/ttt` 能在 smoke split 上完成自適應訓練、所有候選通過訓練 I/O 驗證，metadata 標註 `strategy="ttt_model"` 且 confidence 依驗證損失調整；當 loss 未收斂時會自動降權或放棄候選。

# 階段四：LLM 程式生成整合
- **工作內容**：在本地/Kaggle 以 4-bit 方式載入 Qwen-2.5 Coder 7B，設計 DSL 專用 prompt + 多版 chain-of-thought 變體，完成溫度/Top-p 抽樣（預設 8 筆）與 `DSLInterpreter` 驗證流程，並封裝通過驗證的程式候選（含 prompt 版本、confidence、token 使用量等 metadata）。
- **完成條件**：LLMModule 可成功啟動模型、於 smoke 任務至少產出 1 個通過驗證的 DSL 候選；失敗候選會被過濾或標示 `note="failed_verification"`，且整個流程遵守 GPU/記憶體限制無 OOM。
- **進度更新**：`arc/llm` 已切換至 Qwen-2.5 Coder 7B 4-bit pipeline，PromptBuilder/DSLInterpreter 驗證與 metadata 打包皆完成，smoke 設定預設啟用 stub backend 驗證流程。

# 階段五：Kaggle Notebook 首跑與交付
- **工作內容**：依 `docs/ENV_SETUP.md` 打包 wheels、在 Kaggle GPU Notebook 套用 `scripts/setup_kaggle_env.sh`，調整 `CONFIG_DEFAULTS.yaml`（GPU 映射、SMT 關閉、記憶體保護），執行 `python scripts/run_eval.py --split evaluation`、收集 `logs/runtime.log`／`reports/metrics.jsonl`，並整理 `outputs/pass2.json` 為最終提交流程。
- **完成條件**：Kaggle Notebook 成功跑完整個 evaluation split，三個求解模組皆產生候選並由 Arbitrator 統合；`pass2.json` 可直接上傳評分，附帶一次完整的日誌與資源使用記錄以供後續迭代分析。
