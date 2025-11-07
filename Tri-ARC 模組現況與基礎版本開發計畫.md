# Tri-ARC 模組現況與基礎版本開發計畫

**Evaluation**

This competition evaluates submissions on the percentage of correct predictions. For each task, you should make 2 attempts to predict the exact outputs for every test input grid contained in the task. (Tasks can have more than one test input that needs a predicted output.) Each task test output has one ground truth. For a given task output, any of the 2 predicted outputs matches the ground truth exactly, you score `1` for that task test output, otherwise `0`. The final score is the sum averaged of the highest score per task output divided by the total number of task test outputs.

## **Submission File**

The submission file for this competition must be a json named `submission.json`.

For each task output in the evaluation set, you should make exactly 2 predictions (`attempt_1`, `attempt_2`). The structure of predictions is shown below. Many tasks have multiple outputs (a multiple dictionaries enclosed in a list), although some tasks have a single output that must be predicted. When a task has multiple test outputs that need to be predicted (e.g., task `12997ef3` below), they must be in the same order as the corresponding test inputs.

**IMPORTANT:** All the task_ids in the input challenges json file must also be present in the `submission.json` file. Both "attempt_1" and "attempt_2" must be present, even if your submission doesn't have 2 predictions.

```
{"00576224": [{"attempt_1": [[0, 0], [0, 0]], "attempt_2": [[0, 0], [0, 0]]}],
 "009d5c81": [{"attempt_1": [[0, 0], [0, 0]], "attempt_2": [[0, 0], [0, 0]]}],
 "12997ef3": [{"attempt_1": [[0, 0], [0, 0]], "attempt_2": [[0, 0], [0, 0]]},
              {"attempt_1": [[0, 0], [0, 0]], "attempt_2": [[0, 0], [0, 0]]}],
 ...
}
```

## **現有模組狀態總覽**

- **Symbolic Lane（符號程式搜索）** – **已實作完整工作流程**：包含模組包裝（**`SymbolicModule`**）、求解器（**`SymbolicSolver`**）、DSL 程式解析與執行皆已到位[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L80-L88)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/solver.py#L108-L116)。Symbolic 求解器能在給定任務下枚舉 DSL 程式、套用啟發式引導搜索並驗證訓練樣例，產生**符合所有例子的候選方案**（每個候選都附有程式序列與遙測資訊）[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L88-L95)。模組預設支援暫存中斷續跑與 Partial 解答等功能[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L36-L44)。
- **Scheduler（排程）與 Arbitrator（仲裁）** – **核心流程就緒**：Scheduler 已定義模組排程策略、資源配置和預算分配（**`SchedulerCore`** 管理各模組時間權重與佇列）[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/scheduler/core.py#L154-L163)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/scheduler/core.py#L114-L122)。Arbitrator 則彙集各模組提交的候選結果，對其進行形式驗證與評分，最後決策輸出答案[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L86-L94)。在仲裁階段，系統會從每個模組的共享快取中收集該任務的所有候選[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L163-L171)，使用 VerificationRunner 驗證每個候選是否通過所有訓練 I/O，計算信心分數與多樣性，然後按配置閾值選擇最佳方案作為最終解[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L86-L94)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L93-L101)。如無模組產生有效解，Arbitrator 會自動產生**後備候選**（例如輸出與輸入相同的平凡解）以確保每題有答案[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L99-L108)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L109-L112)。
- **資料載入與評測** – **I/O管道與評測腳本已就緒**：**`DatasetLoader`** 會讀取原始 ARC 任務資料並正規化為統一格式的 **`task_payload`**（包括訓練輸入輸出對和測試輸入）供求解模組使用[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L46-L49)。評測樞紐 **`EvaluationHarness`** 以及腳本 **`scripts/run_eval.py`** 可以將各模組串聯起來，對一組任務執行端到端求解並評估結果。專案已預置 **`smoke`** 和 **`evaluation`** 資料分割，方便開發時快速測試少量任務或進行全面評估[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L44-L49)。例如，可在本地或 Kaggle 上執行 **`python scripts/run_eval.py --split smoke --max_tasks 5`** 進行小規模端到端驗證，確保模組協同工作正常。
- **TTT & LLM Lane** – **目前僅為佔位實作**：Test-Time Training (TTT) 模組與 LLM Codegen 模組目前提供可呼叫的 **stub** 實現：它們遵循**`SolverModule`**介面，但沒有真正的模型邏輯，只是返回示範性輸出以測試流程通路。TTT 現階段的 **`_on_solve`** **直接將第一個訓練樣例的輸出當作候選解**（置信度0.4，標記策略為**`"train_echo"`**）[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/ttt/__init__.py#L50-L57)；LLM 模組則類似地回傳第一個訓練輸出作為候選（置信度0.35），並在摘要訊息中標註「LLM stub execution...」提醒這只是佔位結果[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/llm/__init__.py#L48-L56)。這兩個 stub 輸出均設定 **`status=PARTIAL`**，確保仲裁器識別它們為部分解決方案。目前 TTT/LLM 並未真正產出新的解題邏輯，但 stub 的存在驗證了**多解法管線**（符號+學習+LLM）在框架中的協作可行性。

## **DSL 語言解析與 Symbolic 求解器**

### **DSL 語言現況與改進方向**

Tri-ARC 使用專案自訂的 **S 表達式 DSL** 來描述 ARC 圖形轉換程序。DSL 的解析和執行系統已基本完善：

- **解析與驗證**：DSL 採用遞迴下降解析，句法類似 Lisp（以 **`(pipeline ... )`** 表示程序，**`(apply operator args...)`** 表示一步操作)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L13-L21)。已實作 **`parse_program`** 來將字串解析為 **`Program`** AST，以及靜態語義檢查函式 **`validate_program`**，會在執行前檢查每個階段的運算子是否合法、參數數目與型別匹配等[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L288-L296)。例如，若程序包含未知運算子或參數數量不符，**`validate_program`** 會回傳錯誤清單，執行器在 **`run()`** 前會攔截並拋出驗證失敗例外[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L54-L62)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L288-L296)。
- **執行語義**：執行器 **`DSLInterpreter`** 會將解析後的 Program 逐步執行。它內建**執行狀態**，包含當前 grid、物件堆疊、環境變數（例如 **`@last_value`**, **`@last_region`** 等）以供 DSL 程式訪問[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L60-L69)。每個 **`(apply op args...)`** 由解譯器從**primitive registry** 查找對應的原語操作實現並執行[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L138-L147)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L170-L178)。執行採用純函數/無副作用的方式：每步操作接受輸入 grid 狀態，輸出更新後的新 grid（或計算值），並更新環境中的相應欄位（比如 **`last_grid`**, **`last_region`**）供後續步驟引用[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L52-L59)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L64-L71)。執行過程中還實現了**結果快取**與**調試日誌**：Interpreter 可選擇性地快取過去執行結果避免重複計算[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L76-L85)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L96-L104)，並對每步執行記錄時間開銷等資訊。整體而言，DSL 層面已具備**解析-驗證-執行**完整環節，不依賴任何外部語言或轉譯器。
- **改進計畫**：目前 DSL 語言已涵蓋 ARC 常見的圖形操作（如旋轉**`rotate`**、翻轉**`reflect`**、顏色替換**`replace_colour`**、區域選取與繪製等[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L92-L100)）。後續**精進 DSL** 可以考慮：
    - **擴充原語庫**：根據對未解任務的分析，添加新的 DSL primitive。如某些任務需要特殊模式（例如鏡像拼接、圖形放縮等）現在DSL沒有支援，可在 **`arc.symbolic.dsl.runtime.primitives`** 中實作新的 primitive 並加入 registry。
    - **優化類型系統與驗證**：目前驗證強制 region 大小與當前 grid 尺寸一致、坐標參數不越界等規則[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L76-L84)。可以進一步嚴格化 DSL 規範，如引入更多**靜態 lint**（檢查未使用的結果、無效的堆疊操作等）提升程式品質，避免模組產生冗餘步驟。
    - **治理與版本管控**：DSL_SPEC 中提到可以透過 DreamCoder-style 機制從已解任務中萃取高頻片段加入 DSL[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L32-L40)。基礎版暫不實作此動態學習，但可預留 hooks（例如 **`dsl/library.json`**）讓未來方便納入新片段。同時確保對 DSL 的修改皆更新規格文件與版本標記（目前 DSL 版本為0.2.0[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L2-L5)）。

### **Symbolic 求解器現況與改進方向**

Symbolic 模組（符號搜尋解題）是 Tri-ARC 的精確求解後盾，負責在 DSL 空間中尋找能完美匹配所有訓練 I/O 的程式。當前 SymbolicSolver 結合了**多種強力技術**，整體已可運行，但仍有優化空間：

- **核心功能**：SymbolicSolver 初始化時會載入設定並建構以下組件：
    - **程式枚舉器**：預設使用 Beam Search，在有限深度內擴展候選程式樹[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L12-L16)。程式枚舉由 **`ProgramEnumerator`** 控制，可視配置選擇 DFS、逐層加深 (IDDFS) 或 Beam 等策略[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L12-L19)。枚舉過程中對每個部分程式都即時執行 DSL，驗證目前已能解出的訓練例數。
    - **啟發式評分**：內建**規則型**與**神經網路**兩類啟發式，用以評估部分程式的潛力[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L14-L19)。規則型涵蓋 heuristic 規則如覆蓋度、一致性、進度貢獻等，並可透過配置調整權重[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L76-L84)；神經啟發則預期載入一個輕量模型（policy net）評估節點分數[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L18-L22)。目前預設兩者都啟用、等權融合[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L88-L96)。**注意**：神經模型預設路徑為 **`models/symbolic/heuristic.pt`**[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L74-L82)，但倉庫中尚未提供該檔案，需要透過離線腳本生成。後續工作應執行 **`scripts/build/build_symbolic_heuristic.py`** 產生對應的 TorchScript 權重並將其打包至離線環境[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L52-L56)。如短期無法取得，可在配置中暫時將 **`symbolic.heuristics.neural.enabled`** 設為 false 以避免載入失敗。
    - **等價圖（E-Graph）優化**：引入 E-Graph 技術進行等價程式合併與剪枝[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L8-L16)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L24-L31)。SymbolicSolver 執行過程中，可將已找到的程式加入等價圖，利用內建 rewrite 規則消除等價的重複探索[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L24-L31)。這降低搜索空間的冗餘，提升效率。E-Graph 功能已預設啟用[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L94-L101)。之後可考慮添加更多規則（**`arc/symbolic/egraph/rules.py`**）或實作從求解結果自動萃取新規則（DreamCoder 壓縮）以強化等價簡化能力。
    - **遙測與檢查點**：SymbolicSolver 會將搜索過程記錄日志與報告：如 frontier 的節點擴展歷程、每輪擴展花費時間、剪枝情況等[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L12-L20)。結果程式會包含 summary，列出探索擴展次數、總生成節點等指標[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L134-L143)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L146-L154)。另外，Solver 能定期將搜索進度序列化至檔案（checkpoint），允許在時間用盡前保存部分結果並在允許時恢復[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L40-L48)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L80-L88)。這部分已在配置中開啟（如 **`warm_start: true`**）並透過 **`cache/symbolic/checkpoints`** 保存進度[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L101-L108)。
- **符號解法精進**：
    1. **調整搜索參數**：基於初步測試情況，調整搜索深度、beam width 等參數以兼顧**求解率**與**時限**。當前預設 **`max_depth=12`**、**`beam_width=64`**[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L66-L74)對某些複雜任務可能不足，必要時可提高深度上限；但在 Kaggle 執行時單題時間有限（soft/hard timeout 分別90/150秒[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L70-L73)），需平衡兩者。此外 **`max_expansions=5000`** 和 **`max_nodes=20000`** 等參數控制整體搜索規模[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L66-L73)，可根據試跑中內存/時間使用情況進行收緊或放寬。
    2. **啟發式校準**：對規則型啟發權重進行校準，確保 heuristic 評分符合預期。比如可以透過 **`tools/compare_heuristics.py`** 測試不同權重組合對節點排名的影響，或調整 **`symbolic.heuristics.rule_based.weights`** 中各項係數來優化搜索順序[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L76-L84)。若神經模型已可用，也需要驗證其輸出分數合理，否則可暫時停用或降低其權重避免干擾。
    3. **SMT 證明整合**：專案設計了一個 SMT 閘道機制，在提交候選給仲裁前先利用 Z3 解算器驗證候選程式的正確性[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/SMT_GATEKEEPER.md#L3-L11)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/SMT_GATEKEEPER.md#L13-L21)。目前 VerificationRunner 已包含 SMT attestation 檢查，需要每個 Symbolic/LLM 候選提供 **`smt_token`** 作為已驗證標記[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L54-L62)。然後仲裁才會承認該候選[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L57-L65)。若沒有 attestation token，**`verify_candidates`** 會將候選直接標記為 REJECTED[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L60-L68)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L164-L173)。**現階段暫無完整的 SMT 編碼實現**，為避免 Symbolic 正確解被誤拒，可採兩種措施：其一，**在 SymbolicModule 產生候選時加註虛擬 token**（如以 **`"smt:"`** 為前綴，加8位隨機字元[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L61-L69)）暫時繞過檢查；其二，**在設定中關閉 SMT 閘道**（將 **`smt.enabled`** 設為 false），使驗證器跳過 token 檢查直接進行實際輸出比對[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L50-L59)。建議採用第二種方式於首次全域測試，以降低整合複雜度，待日後實裝 SMT 證明後再行開啟。

## **Test-Time Training (TTT) 模組實裝計畫**

TTT 模組旨在利用**少量支援範例**對模型在推理時進行快速微調，以捕捉規則搜索可能忽略的**統計線索**[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L3-L8)。目前 TTT 僅是將訓練輸出回顯的 stub[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/ttt/__init__.py#L50-L57)。為了在基礎版本中實現完整功能，我們計畫如下：

- **模型骨架**：搭建一個輕量的 **卷積神經網路** 作為 TTT 模型基礎。理想情況下，結合 CNN 提取局部圖案和 Transformer 捕捉全局關係[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L10-L13)；但在基礎版中可簡化為僅幾層卷積+ReLU+Pool 的淺層網路，或加入一小段 self-attention 層模擬 Transformer 效果。模型輸入為**堆疊的多通道 grid**：可以將訓練輸入 grid（以及可能的輔助特徵，例如顏色直方圖或物件遮罩）作為網路輸入張量，輸出與 grid 同尺寸的10類別softmax（對應每個像素的顏色預測）。這樣模型就能直接對每個像素進行分類，預測輸出圖。
- **支援集構建**：對於每個 ARC 任務，我們使用提供的所有訓練 I/O 對作為支援資料。若只有1個範例，也可以透過**資料增強**來產生更多訓練樣本[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L15-L23)。增強方法包括：
    - **對稱變換**：對輸入和輸出圖同時做水平/垂直翻轉、旋轉90度等操作（在不破壞任務語義前提下）生成等價樣本。
    - **調色盤置換**：隨機重新映射顏色ID（例如將所有藍色和紅色對調），只要任務的規則與具體顏色無關，就不影響輸出，從而得到新的訓練對。
    - **雜訊平滑**：對輸入做輕微干擾，如隨機改變少數像素（前提是ARC任務允許微小變動），以提升模型抗雜訊能力。
        
        初版實作可從最簡單的水平/垂直翻轉開始，如檢測到輸出與輸入在某軸對稱，可以加入相應翻轉的對稱樣本。
        
- **損失函數**：設定多元損失以引導模型學習：
    - **重建損失**（reconstruction loss）：主要損失，度量模型預測輸出與實際輸出之間每個像素的差異。我們可使用**逐像素交叉熵**（multi-class cross entropy）或均方誤差（MSE，但交叉熵對分類問題更合適）作為重建損失。[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L17-L25)中的輔助損失可作為 regularization，我們視時間酌情實現：
    - **顏色守恆損失**：懲罰預測輸出與輸入（或與期望輸出）在顏色分佈上差異過大[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L17-L20)。例如比較輸入和預測輸出的顏色直方圖，用加權L1差作為損失，鼓勵模型避免無依據地改變整體顏色數量。
    - **物件數量損失**：鼓勵模型預測的輸出**物件個數**與輸入一致[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L17-L20)（或與正確輸出一致）。實現上，可利用項目現有的 **`detect_objects`** 邏輯計算輸入/輸出的物件regions數，將差的平方作為懲罰項。
    - **平滑度損失**：偏好輸出圖案的連續一致，懲罰過於雜亂的預測[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L17-L21)。可透過計算預測輸出中相鄰像素顏色變化的次數，或局部3x3區域內顏色方差，作為粗略的「不平滑度」度量來加權。此損失可防止模型隨機填充輸出而缺乏結構。
        
        初版建議**以重建損失為主**（權重1.0），其他輔助損失給較小權重（例如顏色0.5, 物件0.3, 平滑0.2[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L120-L126)），逐步嘗試效果。如時間不足，可僅實作重建+顏色守恆兩部分，已能提供一定正則效果。
        
- **適應過程**：模型以隨機初始化或預訓練權重開始（目前沒有預訓練模型，可直接隨機初始化）。在每個任務上，用上述支援集進行**短暫梯度下降微調**[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L16-L24)。配置預設迭代步數16步、學習率3e-4[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L116-L124)。使用 AdamW 優化器，並應用**梯度裁剪**（例如 max norm = 1.0[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L118-L126)）以穩定訓練。由於步數很少，可以不需要學習率調度（或使用簡單的cosine decay如文檔建議[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L21-L24)）。加入**早停**判斷：根據驗證集（可從支援集中留出1個樣例）監控重建損失，如連續3步無改善則提前停止[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L21-L24)。不過在16步以內，損失下降趨勢明顯即可跑完全部步數。此外，要防止**梯度爆炸**：若出現loss為NaN或驟增，可嘗試減小learning rate或重設部分參數梯度。
- **預測與候選輸出**：微調結束後，用更新後的模型對**該任務的測試輸入**逐一進行推理，產生預測輸出。TTTModule 應將每個測試輸入對應的輸出組成清單，作為一個候選提交給仲裁。為符合仲裁接口，候選格式可類似：
    
    ```python
    {
        "candidate_id": f"ttt-{task_id}",
        "type": "grid",
        "payload": {"outputs": [grid1, grid2, ...]},  # 如果有多個test輸入
        "metadata": {"confidence": conf, "strategy": "ttt_model"}
    }
    
    ```
    
    其中 **`confidence`** 可根據模型在訓練集的表現估計，例如**最後驗證損失反比**或**預測輸出的平均置信度**（softmax最大值均值）來計算一個0~1之間的值。由於TTT輸出是經過訓練樣例調優的，理論上只要**預測完全擬合所有訓練例**，仲裁階段VerificationRunner會驗證它在訓練集上通過[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L211-L220)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L224-L232)。為安全起見，TTTModule 也可以主動將訓練輸入跑一遍模型，確認預測與訓練輸出全相符，標記 **`verification_passed=True`** 以提示仲裁器（或直接在 metadata 中附上 **`requires_smt=False`** 減少不必要的SMT驗證）。
    
- **錯誤回退機制**：如果適應過程失敗（例如loss始終居高不下或輸出與訓練輸出仍差異巨大），TTTModule可考慮實施回退策略[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L28-L31)。例如檢測到最終訓練loss仍很大，則放棄該候選或降低其信心，使仲裁有可能選擇其它模組結果。甚至可以**重置模型**為初始權重，用更保守的超參數重訓一次（例如更低LR, 更少步數）[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L28-L31)，以防第一次更新跑飛。但在基礎版本中，時間有限可暫不深入實作回退，只需將不理想候選正常提交，仲裁器會在評分階段因信心不足自動偏好其它候選或 fallback。

完成上述實裝後，TTT 模組將從 stub 升級為**真正能產生預測輸出**的學習模組。它預期能解出某些符號搜尋難以覆蓋的題目（例如需要辨識圖樣統計特徵的任務），並與Symbolic/LLM候選一起提交仲裁，提高整體解題覆蓋率。

## **LLM 程式生成模組整合計畫**

LLM Codegen 模組負責利用大型語言模型，從任務例子中**生成潛在解題程式**，為求解提供創造性候選。當前 LLMModule 僅為 stub，返回訓練輸出作為虛擬候選[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/llm/__init__.py#L48-L56)。計畫在基礎版本中，整合倉庫提供的 7B 編碼模型 **Qwen-2.5 Coder 7B-Instruct** 作為本地推理的 LLM，引入以下功能：

- **模型載入與量化**：由於 Kaggle/本地環境資源有限，我們將使用 **4-bit 量化** 加載 Qwen-7B 模型[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L129-L137)。可透過 HuggingFace Transformers 庫與 bitsandbytes 配合實現：例如設定 **`quantization_config=BitsAndBytesConfig(load_in_4bit=True, ... )`** 來加載 safetensors 權重。需要注意準備對應的 tokenizer 和 model config。如果 **`models/Qwen2.5-Coder-7B-Instruct/`** 目錄下已包含 HuggingFace 格式的 config 和 tokenizer 檔案，直接使用 **`AutoModelForCausalLM.from_pretrained`** 從本地加載；否則需先取得 Qwen 的配置（可以從 HuggingFace 同版本模型獲取並調整）。模型加載後將駐留於GPU記憶體（約數GB級別，4-bit壓縮後應在5GB左右，7B模型可接受）。確保在 Kaggle Notebook 啟動時執行 **`pip install transformers>=4.33, accelerate, bitsandbytes`** 等庫（已在 **`requirements.txt`** 中，離線環境則須預先打包輪子）以支援4-bit推理。
- **提示構建（Prompting）**：設計適合 Qwen Coder 的 prompt，將 ARC 任務的已有資訊轉化為模型可理解的文字。建議採用**程式化描述**方式，以便模型生成程式或代碼：
    - **直接DSL請求**：由於我們的DSL語法接近Lisp風格，可嘗試直接要求模型輸出 DSL 程式。例如 prompt 模板：
        
        ```
        根據以下ARC任務的訓練範例，產生一個能將輸入轉換為輸出 的程序，使用項目定義的DSL (S-expression語法)。只需給出最終的 DSL 程式，無需其他解釋。
        範例1:
        輸入=
        [[...], [...], ...]  # 輸入grid的二維陣列表示
        輸出=
        [[...], [...], ...]
        範例2:
        輸入= ...
        輸出= ...
        (如果有多組範例逐一列出)
        DSL程式:
        
        ```
        
        讓模型填充**`DSL程式:`**後的內容為 **`(pipeline ... )`** 格式的程式碼。這要求模型瞭解DSL語法和任務意圖。由於 Qwen-7B 未經專門訓練ARC DSL，初期效果未知。但我們可以在 prompt 中**提供DSL基本文法或範例**作提示。如列舉常用運算子（rotate, reflect, paint_region 等）的用法，或者附上一個簡單任務的DSL解答示例，讓模型模仿格式。
        
    - **Python代碼路徑**：若直輸出DSL困難，可改讓模型輸出**Python函數**實現轉換。Qwen Code 是專門針對程式碼指令調優的，可能更擅長輸出Python程式。我們可提示：
        
        ```
        根據以下ARC任務例子，撰寫一個Python函數 solve(grid: List[List[int]]) -> List[List[int]]，使其能將輸入grid轉換為正確輸出。
        請只提供函數定義的程式碼。
        範例...
        
        ```
        
        模型若輸出Python程式碼，我們可以直接將其**`exec`**執行，傳入任務輸入得到輸出，再驗證是否匹配。但執行未知程式碼有風險，需要注意**沙盒**安全（限制不進行檔案I/O等操作）。在離線環境中可透過**`exec`**在受控命名空間運行模型代碼，並設置超時防止長時間運算。
        
    
    初版嘗試建議**以DSL為目標輸出**，因為我們已有完善的DSL解譯器可驗證程式正確性。如模型在DSL語法上產生困難，再考慮Python方案或進一步提示。
    
- **生成與篩選**：根據配置，我們將對每個任務讓模型**抽樣產生多個候選**。預設初始採樣數為8[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L132-L140)。可透過不同**prompt版本**來豐富多樣性，例如：
    - Prompt1: 直接要求DSL程式。
    - Prompt2: 要求先思考步驟再給程式（chain-of-thought）。
    - Prompt3: 提示可能的操作序列（如「可能需要旋轉然後填色」）引導模型。
        
        不同提示產生的響應匯總為候選集。採樣時設置**溫度**較高如0.7[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L134-L137)並使用**top-p約0.9**[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L136-L139)，增強多樣性。同時限制最大tokens避免超時（根據經驗，限制在256 tokens 以涵蓋中等長度程式和少量說明文字）。
        
    
    生成完畢後，**對每個候選進行驗證**：我們可直接利用現有 **`DSLInterpreter`** 執行模型輸出的DSL程式（或Python函數）在所有訓練輸入上，檢查是否完全產生對應的訓練輸出[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L211-L220)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L224-L232)。若某候選無法解析或執行錯誤，直接捨棄[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L190-L199)；若執行後輸出與任一訓練輸出不符，標記該候選為失敗（不通過驗證）[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L211-L220)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L224-L232)。**只保留通過所有訓練例驗證的候選**。這相當於在仲裁前就進行了一次“SMT過濾”[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/LLM_CODEGEN.md#L16-L24)（只是不用Z3而用直接執行檢查），可大幅減少無效候選進入仲裁流程的干擾。
    
    實際上，LLM候選大多可能不通過驗證（尤其模型未見過DSL，很可能輸出錯誤程式）。預期8個中可能0個通過。若**沒有候選通過**，LLMModule 可以回傳空候選列表，或選擇性地**傳回其中最有希望的幾個候選**供仲裁做備用（它們會在仲裁的VerificationRunner中被標記FAILED並通常不被選中）。但為保險起見，仍可提交幾個沒有通過的候選，並在metadata標註 **`confidence`** 很低以及 **`note: "failed_verification"`**。仲裁器會綜合評分，不太可能選取明顯無效的候選，而且即使選了也有 fallback 機制避免輸出錯誤答案。
    
- **候選封裝與提交**：對於每個通過驗證的 LLM 產生程式，我們構造候選字典：
    
    ```python
    {
        "candidate_id": f"llm-{task_id}-{index}",
        "type": "program",
        "payload": {"program": "(pipeline (op1 arg1 arg2)...)"},  # 或 Program AST/列表形式
        "metadata": {"confidence": conf, "prompt_version": ver}
    }
    
    ```
    
    如果模型輸出的是DSL字串，直接存入payload的**`program`**欄位（VerificationRunner會自動解析執行[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L317-L325)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L326-L331)）；如果我們採用Python代碼候選，則可考慮將代碼字串存入**`program`**並在 VerificationRunner中擴充對 Python 的執行支持。但目前框架未明確支持任意Python候選，因此**優先使用DSL**路線，以無縫利用現有驗證/執行基礎設施。
    
    同Symbolic，LLM候選也需要 SMT attestation token。如前述，基礎版我們暫時**停用SMT**或給假token處理，確保仲裁正常驗收 LLM 候選[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L54-L62)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L61-L69)。另外，可在 metadata 附加 **`module="llm"`**、**`strategy="LLM_codegen"`** 等標記，以便仲裁日誌區分來源。
    
- **資源與性能考量**：LLM 推理時間相對較長，每個候選可能需數秒到十數秒不等（取決於生成長度和模型size）。為避免拖慢整體：
    - 模組可**限制生成總次數**，如根據任務困難度決定採樣數。簡單任務可能只需嘗試2-4個候選就能命中，複雜任務上限8個。配置的 **`initial_candidates=8`** 和 **`refinement_candidates=4`** 暗示也可以先生成若干初稿，再根據某種自我反饋（例如讓模型評論失敗原因）進行少量精調採樣[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/LLM_CODEGEN.md#L16-L24)。基礎版可以暫不實作二階段refine，僅用單階段生成。
    - **批量處理**：如果硬體允許，對多個提示版本可合併成一個批（batch）送入模型一次生成，減少重複的編碼開銷[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/LLM_CODEGEN.md#L16-L24)。我們配置了 **`batch_size: 2`**[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L132-L135)示意可並行兩條prompt。但由於7B模型一次多生成可能超GPU顯存，實測再決定是否降低batch。
    - **輸出控制**：透過**`stop`**字串避免模型輸出無關內容，例如可以讓模型在輸出DSL程式後加特殊標記如**`<END>`**，我們檢測到此標記或換行即可截斷。這防止模型產生過長獨白影響效率。

完成上述整合後，LLMModule 將能在本地執行 Qwen-7B 模型推理，提供一些非常規但潛在有用的解題思路。雖然預期初版 LLM 候選質量不高，但它豐富了解題手段，**萬一**某些任務Symbolic無解而LLM能猜出（即便低概率），也為最終解提升了一點可能性。[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/LLM_CODEGEN.md#L6-L9)

最後，需注意監控 LLM 模組的產出和資源：我們會將 LLM 推理過程中的日志（如生成的程式、驗證結果等）記錄在仲裁的決策報告裡，便於分析模型行為，為後續fine-tune做準備。

## **Kaggle Notebook 環境準備與首次全域測試**

完成各模組的基礎功能開發後，下一步是在 Kaggle Notebook 環境中進行首次全量測試與提交。根據專案提供的說明文件[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L16-L24)，我們需要做好以下準備工作：

1. **環境設置**：Kaggle Notebook **GPU : T4*2。**Notebook 啟動後，執行 **`bash scripts/setup_kaggle_env.sh`** 來進行環境初始化[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L20-L26)。該腳本會安裝所需的 Python 套件（從預先上傳的離線輪子檔案），配置 Z3 等依賴，與本地環境需求一致[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L8-L14)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L22-L26)。我們需確保所有依賴都在 **`vendor/wheels/`** 打包上傳，否則 Kaggle 無網路情況下無法安裝。[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L22-L26)。
2. 路徑參考 : 
唯讀 : `/kaggle/input/tri-arc/Tri-ARC`, `/kaggle/input/tri-arc/Tri-ARC/arc/llm/mocks.py`, `/kaggle/input/tri-arc/Tri-ARC/data/arcagi2`.
可讀寫 : `/kaggle/working/`
3. **配置調整**：根據 Notebook 硬體情況調整 Tri-ARC 的預設配置：
    - 如果實際只有1塊GPU，可以在進入 **`run_eval.py`** 前，修改 **`docs/CONFIG_DEFAULTS.yaml`** 中的 **`global.device_map`**，將 symbolic/ttt/llm 都映射到同一 GPU（例如都設為 **`"cuda:0"`**），或者透過環境變數約束 **`CUDA_VISIBLE_DEVICES=0`**[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L24-L28)，讓程式只看到一張卡。這樣 Scheduler 在排程時不會嘗試使用不存在的 CUDA:1/2。由於我們配置了 **`scheduler.resource_pool.gpu_capacity: 1.0`**[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L60-L63)，多模組共用一卡時 SchedulerCore 應該會串行執行它們避免競爭（需要留意 Scheduler 資源追蹤是否如預期工作）。如有4卡可用，則保持默認映射，分配 Symbolic→cuda:0, TTT→cuda:1, LLM→cuda:2, 其餘模組→cuda:3[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L4-L11)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L24-L33)，並使用 **`CUDA_VISIBLE_DEVICES=0,1,2,3`** 明確對應實體GPU[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L24-L28)。
    - 根據Kaggle環境的RAM/VRAM情況，可調整一些**內存相關參數**。例如若發現Symbolic搜索佔用記憶體過多，可降低 **`symbolic.max_nodes`** 或關閉 **`egraph.enabled`** 降低記憶消耗。又如 LLM 生成如有Timeout風險，可適當減少 **`llm.initial_candidates`** 或縮短 max tokens。
    - 暫時關閉 SMT 驗證（**`smt.enabled: false`**），除非我們成功將 Z3 也打包進環境且確信 attestation token 已妥善處理。否則保持預設true但無token，會導致Symbolic/LLM候選全部被仲裁拒絕，等同於浪費它們的計算結果。
4. **執行全域評測**：環境就緒後，在 Notebook 裡啟動評測腳本。例如執行：
    
    ```bash
    cd /kaggle/working/Tri-ARC
    python scripts/run_eval.py --split evaluation
    
    ```
    
    這將讀取 **`data/arcagi2/evaluation`** 子集的所有任務，逐一送入 Scheduler 處理。Scheduler 會平行/串行調用 Symbolic、TTT、LLM 模組解每題，仲裁器彙總決策，最終輸出結果到 **`reports/`** 與 **`outputs/`** 資料夾中[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L140-L148)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L282-L290)。專案中仲裁器設定將最終答案寫入 **`outputs/pass2.json`**[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L282-L290)，其中每個任務ID對應模型輸出（以列表形式列出所有測試輸出的預測grid）[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L280-L288)。我們需要將該文件作為提交結果檔案。如果競賽要求特定格式，可能要轉換此JSON為Kaggle指定的CSV或別的格式；但若遵循ARC原始競賽規範，應提交每題的預測輸出。在確認輸出格式正確後，提交 **`pass2.json`** 即可。
    
5. **監控日誌與調適**：首次全域跑可能暴露一些問題，我們應留意 Notebook 輸出日志和生成的報告：
    - **`logs/runtime.log`**：全域運行時每個模組的INFO/DEBUG日志（因為配置中 logging.level=INFO[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L166-L174)）。可檢視有無錯誤exception，或模組超時被中止等訊息。
    - **`reports/metrics.jsonl`**：內含每題各模組執行時長、解題成敗等關鍵指標[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L56-L62)。可在跑完後下載分析，了解 Symbolic平均擴展了多少節點、TTT是否頻繁重訓失敗等。
    - **`reports/arbitration_summary_*.md`**：仲裁總結報告，記錄每題用哪個模組答案、候選分數及被拒原因[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L294-L303)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L310-L318)。特別關注 **`Rejected candidates`** 清單中是否有我們意料之外被拒絕的候選（例如Symbolic明明正確卻因token問題被拒）。
    - 如有部分任務模型全失敗且 fallback 用上，也會在報告標註 **`fallback_used: true`**[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L260-L267)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L99-L108)，日後可重點分析這些題改進。
        
        總之，透過這些日志我們可以驗證整個系統在 Kaggle 環境下的**正確性與穩定性**，並蒐集初步性能資料。
        
6. **結果提交與評估**：若 Notebook 跑完整個 evaluation split（或競賽正式測試集）且 **`outputs/pass2.json`** 生成成功，我們即可將其壓縮提交Kaggle評分。提交前再次核對檔案格式符合競賽要求。如果需要，可寫簡短腳本轉換為競賽指定格式再提交。第一次全域測試的重點是**驗證功能完備性**而非追求高分，所以評分結果可能較低（預期Symbolic能正確解出一些簡單任務，但TTT/LLM可能尚未提供顯著貢獻）。透過提交結果，我們也能從Kaggle評分系統獲取哪些題解對了、哪些錯了，以便下一步有針對性地優化。

經過以上步驟，我們將完成 Tri-ARC 系統在離線競賽環境的部署與第一次全量跑通。這標誌著**基礎版本的所有功能**（符號搜索、DSL執行、即時訓練、LLM解碼、多模組仲裁整合）已全部開發並集成。接下來可根據首跑結果，迭代改進模型效果和效率，例如調整權重、針對失敗任務加入新DSL原語或finetune LLM等，不斷提升整體解題率。此次整合奠定了完整架構，在此基礎上精進各模組性能，最終有望在ARC挑戰中取得優異表現！[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L46-L51)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/LLM_CODEGEN.md#L41-L45)

**來源**：上述內容參考並綜合了 Tri-ARC 專案程式碼與文件，包括模組實作檔案[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/ttt/__init__.py#L48-L57)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/llm/__init__.py#L48-L56)、DSL規格[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L288-L296)、Symbolic/TTT/LLM 模組設計文檔[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L12-L19)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L16-L24)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/LLM_CODEGEN.md#L16-L24)以及環境部署說明[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L16-L24)[GitHub](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L52-L56)等。以上計畫既遵循現有架構初衷，也結合實際情況提出具體可行的實作步驟，以確保所有功能在基礎版本均可正常運作並通過Kaggle測試。

**引用**

[**__init__.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L80-L88](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L80-L88)
[**solver.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/solver.py#L108-L116](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/solver.py#L108-L116)
[**__init__.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L88-L95](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L88-L95)
[**__init__.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L36-L44](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L36-L44)
[**core.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/scheduler/core.py#L154-L163](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/scheduler/core.py#L154-L163)
[**core.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/scheduler/core.py#L114-L122](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/scheduler/core.py#L114-L122)
[**module.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L86-L94](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L86-L94)
[**module.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L163-L171](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L163-L171)
[**module.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L93-L101](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L93-L101)
[**module.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L99-L108](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L99-L108)
[**module.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L109-L112](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L109-L112)
[**ENV_SETUP.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L46-L49](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L46-L49)
[**ENV_SETUP.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L44-L49](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L44-L49)
[**__init__.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/ttt/__init__.py#L50-L57](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/ttt/__init__.py#L50-L57)
[**__init__.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/llm/__init__.py#L48-L56](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/llm/__init__.py#L48-L56)
[**DSL_SPEC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L13-L21](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L13-L21)
[**interpreter.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L288-L296](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L288-L296)
[**interpreter.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L54-L62](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L54-L62)
[**DSL_SPEC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L60-L69](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L60-L69)
[**interpreter.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L138-L147](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L138-L147)
[**interpreter.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L170-L178](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L170-L178)
[**DSL_SPEC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L52-L59](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L52-L59)
[**DSL_SPEC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L64-L71](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L64-L71)
[**interpreter.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L76-L85](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L76-L85)
[**interpreter.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L96-L104](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/dsl/interpreter.py#L96-L104)
[**DSL_SPEC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L92-L100](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L92-L100)
[**DSL_SPEC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L76-L84](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L76-L84)
[**SYMBOLIC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L32-L40](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L32-L40)
[**DSL_SPEC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L2-L5](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/DSL_SPEC.md#L2-L5)
[**SYMBOLIC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L12-L16](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L12-L16)
[**SYMBOLIC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L12-L19](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L12-L19)
[**SYMBOLIC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L14-L19](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L14-L19)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L76-L84](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L76-L84)
[**SYMBOLIC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L18-L22](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L18-L22)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L88-L96](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L88-L96)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L74-L82](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L74-L82)
[**ENV_SETUP.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L52-L56](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L52-L56)
[**SYMBOLIC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L8-L16](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L8-L16)
[**SYMBOLIC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L24-L31](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L24-L31)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L94-L101](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L94-L101)
[**SYMBOLIC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L12-L20](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L12-L20)
[**__init__.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L134-L143](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L134-L143)
[**__init__.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L146-L154](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L146-L154)
[**__init__.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L40-L48](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/symbolic/__init__.py#L40-L48)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L101-L108](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L101-L108)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L66-L74](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L66-L74)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L70-L73](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L70-L73)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L66-L73](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L66-L73)
[**SMT_GATEKEEPER.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/SMT_GATEKEEPER.md#L3-L11](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/SMT_GATEKEEPER.md#L3-L11)
[**SMT_GATEKEEPER.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/SMT_GATEKEEPER.md#L13-L21](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/SMT_GATEKEEPER.md#L13-L21)
[**verification.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L54-L62](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L54-L62)
[**verification.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L57-L65](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L57-L65)
[**verification.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L60-L68](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L60-L68)
[**verification.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L164-L173](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L164-L173)
[**verification.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L61-L69](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L61-L69)
[**verification.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L50-L59](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L50-L59)
[**TTT.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L3-L8](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L3-L8)
[**TTT.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L10-L13](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L10-L13)
[**TTT.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L15-L23](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L15-L23)
[**TTT.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L17-L25](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L17-L25)
[**TTT.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L17-L20](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L17-L20)
[**TTT.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L17-L21](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L17-L21)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L120-L126](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L120-L126)
[**TTT.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L16-L24](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L16-L24)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L116-L124](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L116-L124)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L118-L126](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L118-L126)
[**TTT.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L21-L24](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L21-L24)
[**verification.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L211-L220](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L211-L220)
[**verification.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L224-L232](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L224-L232)
[**TTT.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L28-L31](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L28-L31)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L129-L137](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L129-L137)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L132-L140](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L132-L140)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L134-L137](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L134-L137)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L136-L139](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L136-L139)
[**verification.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L190-L199](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L190-L199)
[**LLM_CODEGEN.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/LLM_CODEGEN.md#L16-L24](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/LLM_CODEGEN.md#L16-L24)
[**verification.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L317-L325](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L317-L325)
[**verification.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L326-L331](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/verification.py#L326-L331)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L132-L135](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L132-L135)
[**LLM_CODEGEN.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/LLM_CODEGEN.md#L6-L9](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/LLM_CODEGEN.md#L6-L9)
[**ENV_SETUP.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L16-L24](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L16-L24)
[**ENV_SETUP.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L20-L26](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L20-L26)
[**ENV_SETUP.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L8-L14](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L8-L14)
[**ENV_SETUP.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L22-L26](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L22-L26)
[**ENV_SETUP.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L18-L24](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L18-L24)
[**ENV_SETUP.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L24-L28](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/ENV_SETUP.md#L24-L28)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L60-L63](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L60-L63)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L4-L11](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L4-L11)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L24-L33](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L24-L33)
[**module.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L140-L148](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L140-L148)
[**module.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L282-L290](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L282-L290)
[**module.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L280-L288](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L280-L288)
[**CONFIG_DEFAULTS.yaml**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L166-L174](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/CONFIG_DEFAULTS.yaml#L166-L174)
[**SYMBOLIC.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L56-L62](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/SYMBOLIC.md#L56-L62)
[**module.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L294-L303](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L294-L303)
[**module.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L310-L318](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L310-L318)
[**module.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L260-L267](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/arbitration/module.py#L260-L267)
[**TTT.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L46-L51](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/TTT.md#L46-L51)
[**LLM_CODEGEN.md**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/LLM_CODEGEN.md#L41-L45](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/docs/MODULES/LLM_CODEGEN.md#L41-L45)
[**__init__.py**https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/ttt/__init__.py#L48-L57](https://github.com/Danwuoo/Tri-ARC/blob/09950425170103c54392b1bd930d697015c67712/arc/ttt/__init__.py#L48-L57)