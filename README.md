# Tri-ARC

Tri-ARC 是探索 ARC 格網推理的研究原型，將 symbolic program synthesis、test-time training（TTT）與 LLM 候選程式串接到 scheduler 與 arbitrator。本 repo 保留 Python 實作、測試、資料快照與歷史執行紀錄，適合展示模組介面、搜尋預算與驗證流程的設計。

目前應以**研究原型與工程流程**介紹。歷史 [evaluation summary](reports/eval_summary.md) 的 `Pass rate: 100%` 是流程完成率：計算式是 `tasks_completed / (tasks_completed + tasks_failed)`，見 [reporting.py](arc/evaluation/reporting.py)。同次 120 題全部啟用 fallback；這個數字不能代表 ARC 測試答案正確率或正式競賽成績。[教授視角審查](PROFESSOR_AUDIT.md) 列出公開前缺口與宣稱範圍。

## 教授閱讀入口

| 閱讀順序 | 入口 | 可核查的內容 |
| --- | --- | --- |
| 1 | [教授視角審查](PROFESSOR_AUDIT.md) | 五項評分、成果邊界與公開前問題 |
| 2 | [Module contract](arc/core/module_base.py)、[registry](arc/core/registry.py) | 模組生命週期、建構與替換方式 |
| 3 | [Symbolic solver](arc/symbolic/solver.py)、[search strategies](arc/symbolic/search/enumerators.py)、[search budget](arc/symbolic/search/budget.py) | 搜尋、時間限制、候選程式與 telemetry |
| 4 | [EGraph](arc/symbolic/egraph/engine.py)、[verifier](arc/arbitration/verification.py) | 簡化的重寫結構與例題一致性檢查；不要把例題通過擴大為泛化保證 |
| 5 | [歷史 manifest](reports/eval_manifest_20251110_ablation-no-opt.md)、[run artifacts](reports/eval_runs/ablations/ablation-no-opt/) | 執行時的 commit、seed、configuration fingerprint 與結果 |

閱讀大型 `solver.py` 前，先看 [結果型別](arc/core/results.py) 與 [搜尋型別](arc/symbolic/search/types.py)，再對照 [regression tests](tests/symbolic/test_regression.py)。這條路線呈現核心邏輯，無須為展示而改動核心程式。

## 實作與展示範圍

- Symbolic lane 有具體搜尋、DSL、重寫與 verification 程式；[模組說明](docs/MODULES/SYMBOLIC.md) 可作導覽，細節仍以實作與對應測試為準。
- TTT 有 [實作](arc/ttt/__init__.py) 與 [mock](arc/ttt/mocks.py)；LLM 有 [backend](arc/llm/engine.py) 與 [mock](arc/llm/mocks.py)。展示時須說明使用哪個 backend。
- [smoke preset](configs/eval/smoke.yaml) 關閉 TTT、停用 neural heuristic，並使用 LLM stub。Smoke 通過只核查該配置的流程。
- [架構說明](docs/handbook/architecture.md) 的 >85% pass@2 目標與效能提升敘述，以及 [completion summary](reports/PROJECT_COMPLETION_SUMMARY.md) 的 production-ready、coverage 宣稱，均不能單憑這些文字作為已達成的證據。

## 重現與檢查

所有命令從 repo 根目錄執行。最小文件檢查只使用 Python 標準函式庫，不需模型、GPU 或第三方套件：

```powershell
python -X utf8 scripts/check_doc_links.py README.md PROFESSOR_AUDIT.md
python -X utf8 scripts/check_doc_links.py
```

第一個命令檢查這兩份文件內的 `docs/*.md` 參照；第二個檢查整個 `docs/`。此工具不驗證所有 Markdown 連結、anchors 或程式正確性。2026-10-11 的全目錄檢查找到 5 處舊文件參照，缺少的目標是 docs 目錄內的 `changelog.md` 與 `policies/release_governance.md`；未補造這些治理文件。

執行研究程式前，須先解決環境宣告差異：[Conda 定義](environments/conda/environment.yml) 使用 Python 3.11、PyTorch 2.3 與 torchvision 0.18，[requirements.txt](requirements.txt) 則固定 torch 2.9.0 與 torchvision 0.24.0。這些設定不能當成已核實的同一環境。選定環境後，可依 requirements 建立隔離環境；安裝與完整 solver 尚未在本次整理中獨立重現。

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest -p no:cacheprovider tests/core/test_module_base.py tests/core/test_registry.py
```

這組測試只核查介面與 registry，不能代替 benchmark。[既有 evaluation CLI](scripts/run_eval.py) 另有 `--preset smoke --split smoke --max-tasks 5`，但它會更新共享的 `reports/eval_summary.md`、history、archives 等檔案，即使指定 `--run-root` 也不能隔離全部輸出。需要執行時，請在額外的乾淨 clone 中操作，避免覆蓋保留的歷史紀錄。

## 資料與貢獻

[資料目錄](data/arcagi2/) 是外部 ARC 資料，不是本人產出的題庫。[授權紀錄](docs/compliance/LICENCE_LOG.md) 保留了歷史來源說明，但其中套件版本與目前 requirements 不一致；公開前仍須由作者確認適用的來源與授權。本 repo 尚無根目錄 LICENSE。

Git history 同時包含 `Danwuoo` 與 `google-labs-jules[bot]` 的 commit。提交帳號不能證明每個演算法的個人原創性；本人完成、AI 協作與第三方內容的範圍仍待作者確認，詳見審查文件。
