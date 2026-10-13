# Tri-ARC

Tri-ARC 是探索 ARC 格網推理的 Python 研究原型。它將 symbolic program synthesis、test-time training（TTT）與 LLM 候選程式接到共用 scheduler／arbitrator，研究模組介面、搜尋預算、候選驗證與回退流程。

Repository 保留原碼、測試、外部資料快照及歷史執行產物。目前應分開理解**流程是否完成**、**候選是否符合示範例題**與**測試答案是否正確**。

## 系統與原碼

```text
ARC task → module registry / scheduler
           ├─ symbolic search
           ├─ TTT backend
           └─ LLM backend
         → candidates → verification / arbitration → prediction / fallback
```

| 閱讀順序 | 入口 | 內容 |
| --- | --- | --- |
| 1 | [Module contract](arc/core/module_base.py)、[context](arc/core/context.py)、[results](arc/core/results.py)、[registry](arc/core/registry.py) | 模組生命週期、候選與結果型別。 |
| 2 | [Search types](arc/symbolic/search/types.py)、[budget](arc/symbolic/search/budget.py)、[enumerators](arc/symbolic/search/enumerators.py) | 搜尋策略、時間限制與 telemetry。 |
| 3 | [Symbolic solver](arc/symbolic/solver.py)、[EGraph](arc/symbolic/egraph/engine.py)、[CEGIS](arc/symbolic/verification/cegis.py) | 候選程式、簡化重寫結構與驗證。 |
| 4 | [Scheduler](arc/scheduler/core.py)、[arbitrator](arc/arbitration/module.py)、[verifier](arc/arbitration/verification.py) | 模組協調、候選選取與 fallback。 |
| 5 | [Evaluation harness](arc/evaluation/harness.py)、[reporting](arc/evaluation/reporting.py)、[regression tests](tests/symbolic/test_regression.py) | 執行狀態與結果的計算方式。 |

TTT 的 [實作](arc/ttt/__init__.py)／[mock](arc/ttt/mocks.py)，以及 LLM 的 [backend](arc/llm/engine.py)／[mock](arc/llm/mocks.py) 必須分開。現有 [smoke preset](configs/eval/smoke.yaml) 關閉 TTT、停用 neural heuristic，並使用 LLM stub；smoke 不是完整模型能力測試。

## 歷史結果應如何閱讀

[執行 manifest](reports/eval_manifest_20251110_ablation-no-opt.md) 與 [run artifacts](reports/eval_runs/ablations/ablation-no-opt/) 保存 commit、seed、configuration fingerprint 與逐題輸出。[Evaluation summary](reports/eval_summary.md) 的 `Pass rate: 100%` 實際計算為：

```text
tasks_completed / (tasks_completed + tasks_failed)
```

同次 120 題全部啟用 fallback。因此這是流程完成率，不是 ARC exact-match accuracy 或正式競賽成績。現有仲裁流程也會將 fallback 標成 `VerificationStatus.PASSED`；這個狀態不能當成測試答案正確的證明。

[架構文件](docs/handbook/architecture.md) 的 `>85% pass@2` 與效能目標，以及 [歷史 completion summary](reports/PROJECT_COMPLETION_SUMMARY.md) 的 production-ready／coverage 敘述，應視為目標或歷史自述，不能單獨作為已達成結果。要判定解題能力，需另以同版本 target 對逐題 prediction 做 exact-match 評估。

## 文件檢查

從 repository 根目錄執行，僅需 Python 標準函式庫：

```sh
python -X utf8 scripts/check_doc_links.py README.md
python -X utf8 scripts/check_doc_links.py
```

此工具只檢查 `docs/*.md` 形式的參照，不驗證所有 Markdown links、anchors 或程式行為。既有 `docs/` 仍有指向缺失 `changelog.md` 與 `policies/release_governance.md` 的歷史參照；不要把全目錄檢查預設為通過。

## 執行程式前的環境條件

[Conda 定義](environments/conda/environment.yml) 使用 Python 3.11／torch 2.3／torchvision 0.18，而 [requirements.txt](requirements.txt) 固定 torch 2.9.0／torchvision 0.24.0。兩者尚未統一，不能混裝成同一個已驗證環境。[vendor/wheels](vendor/wheels/) 主要保留 manifest，並未隨 clone 提供完整離線 wheels。

選定並核實環境後，可在隔離環境中安裝 requirements，先執行介面測試：

```sh
python -m pip install -r requirements.txt
python -m pytest -p no:cacheprovider tests/core/test_module_base.py tests/core/test_registry.py
```

這組測試只涵蓋介面與 registry。完整 evaluation 入口見 [scripts/run_eval.py](scripts/run_eval.py) 與 [配置](docs/CONFIG_DEFAULTS.yaml)。CLI 即使指定 `--run-root`，仍可能更新共享 summary、history 與 archives；需要重跑時使用額外的乾淨 clone，以免覆蓋歷史產物。預設 device／模型 assets 與資料條件也需另外確認。

## 資料與來源

[data/arcagi2](data/arcagi2/) 是外部 ARC 資料，不是本專案自行產生的題庫。[授權紀錄](docs/compliance/LICENCE_LOG.md) 保留歷史来源，但套件版本未必與現行 requirements 一致。Repository 目前未附根目錄 LICENSE；第三方資料、依賴與 AI 協作需保持來源區分，不以 Git 提交身分推定所有演算法均為獨立原創。
