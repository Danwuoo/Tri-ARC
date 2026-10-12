# Tri-ARC Professor-facing Repository Audit

Tri-ARC 可作為模組化 ARC 研究原型展示，公開前須優先釐清評估指標、環境版本與個人貢獻。現有程式與執行紀錄足以帶讀工程設計，尚不足以宣稱正式 ARC 正確率、完整離線部署或 production readiness。

審查日期：2026-10-11。來源版本：`7a07691f57b277682378770b07fc3a0185538197`（2025-11-19）。範圍為本地 clone 的文件、代表性程式、既有 artifacts 與 Git history；本次 README 與審查文件由 AI 協助整理，修改僅涉及這兩份文件。

## 評分

採 1–5 分：1 為入口或證據缺失；2 為部分具備但有重要限制；3 為可沿文件核查但仍有公開前缺口；4 為容易審閱且具備範圍內的重現條件；5 為獨立重現與個人歸屬完整。以下是審查判斷，不是研究成績，也不是五項總分排名。

| 面向 | 分數 | 依據與限制 |
| --- | --- | --- |
| Readiness | 2 | [README](README.md) 已提供入口，但 [Conda](environments/conda/environment.yml) 與 [requirements](requirements.txt) 的 PyTorch 宣告不同；[completion summary](reports/PROJECT_COMPLETION_SUMMARY.md) 的部署完成宣稱沒有在本次獨立重現。 |
| Readability | 3 | [module contract](arc/core/module_base.py)、[registry](arc/core/registry.py) 與 [搜尋策略](arc/symbolic/search/enumerators.py) 有可沿讀的邊界；大型 [solver](arc/symbolic/solver.py) 與過度概括的 [架構說明](docs/handbook/architecture.md) 增加核查負擔。README 已補閱讀順序。 |
| Verifiability | 2 | [manifest](reports/eval_manifest_20251110_ablation-no-opt.md) 與 [run artifacts](reports/eval_runs/ablations/ablation-no-opt/) 保留 commit、seed、fingerprint；[summary](reports/eval_summary.md) 的 pass rate 由 [reporting](arc/evaluation/reporting.py) 計算流程完成率，不能作為答案正確率。 |
| Technical Depth | 4 | 可檢視 [搜尋預算](arc/symbolic/search/budget.py)、[簡化 EGraph](arc/symbolic/egraph/engine.py)、[CEGIS](arc/symbolic/verification/cegis.py)、[驗證器](arc/arbitration/verification.py) 與 [回歸測試](tests/symbolic/test_regression.py)。這分數評估可討論的技術內容，沒有認證演算法新穎性或 benchmark 效果。 |
| Individual Contribution | 2 | Git history 有 `Danwuoo` 與 `google-labs-jules[bot]` 提交；[completion summary](reports/PROJECT_COMPLETION_SUMMARY.md) 只泛稱 development team，[授權紀錄](docs/compliance/LICENCE_LOG.md) 另含第三方資料與套件。尚缺作者確認的本人、AI 與外部工作分界。 |

## 可宣稱的成果

- Repo 實作了 shared module lifecycle、registry、scheduler、symbolic candidate generation 與 arbitrator 的工程骨架，可沿 [registry](arc/core/registry.py)、[scheduler](arc/scheduler/core.py)、[harness](arc/evaluation/harness.py) 核查。
- Symbolic 搜尋具有明確的預算與策略抽象，並保留 [regression tests](tests/symbolic/test_regression.py)。測試檔存在不等於本次已執行通過。
- 歷史 `ablation-no-opt` 的 [manifest](reports/eval_manifest_20251110_ablation-no-opt.md) 記錄 120 題流程完成；[summary](reports/eval_summary.md) 同時記錄 120 次 fallback，展示時必須一起說明。

不能宣稱此 repo 已解對 100% ARC 題目、達成 >85% pass@2、驗證所有架構文件的效能提升，或整個系統皆為本人獨立原創。[reporting.py](arc/evaluation/reporting.py) 的完成率與 [harness](arc/evaluation/harness.py) 的 arbitrator success 狀態不足以建立這些結論。[smoke 配置](configs/eval/smoke.yaml) 也明確使用 stub，不可展示成完整本地 LLM 推理。

## 重現邊界

| 層級 | 目前可做的核查 | 條件與限制 |
| --- | --- | --- |
| 文件入口 | `python -X utf8 scripts/check_doc_links.py README.md PROFESSOR_AUDIT.md` | 只需 Python 標準函式庫；只掃描 `docs/*.md` 形式的參照。 |
| 既有紀錄 | 讀 [manifest](reports/eval_manifest_20251110_ablation-no-opt.md)、[run artifacts](reports/eval_runs/ablations/ablation-no-opt/) 與 [指標計算](arc/evaluation/reporting.py) | 這是核閱保留紀錄，不是重新執行的實驗。 |
| 介面測試 | 安裝 [requirements](requirements.txt) 後執行 README 的 core tests | 尚未核實可安裝的統一環境；測試只支持介面行為。 |
| 完整 evaluation | 讀 [CLI](scripts/run_eval.py)、[配置](docs/CONFIG_DEFAULTS.yaml) 與 [資料載入](arc/data/loader.py) | 預設 device map 包含 CUDA，smoke 含 stub，環境與 assets 須先確認。CLI 會更新共享 summary/history，應使用額外 clone。 |

目前 [vendor/wheels](vendor/wheels/) 僅追蹤 manifest，`.gitignore` 排除了 wheels；不能憑 manifest 宣稱 fresh clone 已具備所有離線套件。[Conda](environments/conda/environment.yml) 的 Python 3.11 / torch 2.3 與 [requirements](requirements.txt) 的 torch 2.9.0 / torchvision 0.24.0 須先選定一組實際環境。未在本次整理中修改這些設定。

## 關鍵程式閱讀路線

1. 先讀 [ModuleContext](arc/core/context.py)、[結果型別](arc/core/results.py)、[SolverModule](arc/core/module_base.py)，理解候選程式與成功狀態的意思。
2. 對照 [registry](arc/core/registry.py) 與 [defaults](docs/CONFIG_DEFAULTS.yaml)，確認具體載入的 module 和 device。
3. 讀 [search types](arc/symbolic/search/types.py)、[budget](arc/symbolic/search/budget.py)、[enumerators](arc/symbolic/search/enumerators.py)，再進入 [solver](arc/symbolic/solver.py)。
4. 讀 [arbitration verification](arc/arbitration/verification.py)、[harness](arc/evaluation/harness.py)、[reporting](arc/evaluation/reporting.py)，分辨例題一致性、候選選取與流程完成率。
5. 配對 [symbolic regression tests](tests/symbolic/test_regression.py) 與 [lane tests](tests/test_lane_stubs.py)，確認測試使用了哪些 stub/mock。

## 公開前必須修復的問題

| 優先序 | 問題與具體來源 | 最小處理方式 |
| --- | --- | --- |
| P0 | [eval summary](reports/eval_summary.md) 容易被誤讀為答案正確率；[reporting](arc/evaluation/reporting.py) 實際算流程完成率。 | 備審與展示只使用「流程完成」，保留 fallback 比率與 run 範圍。README 已加限定；不改歷史結果、不補造正確率。 |
| P0 | [架構](docs/handbook/architecture.md) 的 >85% 目標、效能提升，以及 [completion summary](reports/PROJECT_COMPLETION_SUMMARY.md) 的 coverage/production-ready 宣稱超出本次可核驗範圍。 | 在所有引用這些材料的展示中標為目標或歷史自述；未有對應可核查紀錄的量化宣稱不放入備審。 |
| P0 | [Conda](environments/conda/environment.yml)、[Docker](environments/docker/Dockerfile) 與 [requirements](requirements.txt) 尚未形成已驗證的統一環境；[wheel manifest](vendor/wheels/manifest.sha256) 沒有隨 clone 附實際 wheels。 | 公開前由作者確認使用哪組環境與可提供的 assets。現階段展示範圍限定為程式與保留紀錄；不承諾完整離線重現。 |
| P1 | [DOCUMENTATION_GUIDE](docs/DOCUMENTATION_GUIDE.md) 與 [DSL reference](docs/reference/dsl_reference.md) 共有 5 處指向 docs 目錄內不存在的 `changelog.md` 或 `policies/release_governance.md`。 | 刪除或改指已存在且用途相符的引用；若作者沒有治理內容，不補造缺失文件。README 已避開這些入口。 |
| P1 | 根目錄無 LICENSE；[LICENCE_LOG](docs/compliance/LICENCE_LOG.md) 的套件版本與目前 requirements 不同，資料來源描述也需要作者核對。 | 確認本人程式的公開授權及第三方素材的來源、版本與使用方式後再決定公開內容；本次不指定授權、不推定有權再散布。 |
| P1 | Git 提交與團隊概述不足以逐項證明個人貢獻。 | 由作者確認至少一個可講解模組的本人工作、AI 協作與外部來源，並指向既有 commit 或檔案；未確認前不填百分比。 |

P0 是阻止目前形式成果宣稱的問題；P1 是公開入口與歸屬仍需釐清的問題。核心程式、環境、歷史報告與資料均保留原貌，公開前缺口沒有因新增文件而自動解除。

## 本次驗證

已核讀代表性程式與歷史摘要；`python -X utf8 scripts/check_doc_links.py` 發現上述 5 處既有缺失參照。主機 `python` 為 3.14.7，沒有 pytest、NumPy、torch 與 z3，未執行 solver 或 benchmark。文件入口檢查與相對路徑核對由整理流程驗證；沒有新增測試、實驗成果、模型、截圖或個人貢獻敘述。
