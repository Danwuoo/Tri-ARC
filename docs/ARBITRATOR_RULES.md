# Arbitrator Rules

The arbitrator consolidates outputs from the symbolic solver, TTT adaptor, and LLM code generator. It enforces strict example consistency, manages voting, and produces up to two answers per ARC task to satisfy pass@2 scoring.

## Responsibilities
- Validate candidate programs or grids against all provided input-output pairs.
- Score and rank consistent candidates using reliability priors and confidence signals.
- Select primary and secondary answers for submission, ensuring diversity when helpful.
- Generate provenance logs for evaluation and debugging (see `docs/DEBUG_PLAYBOOK.md`).

## Consistency Verification
1. **Execution harness**: Run each candidate on every provided example. For symbolic and LLM programs, execution is done through the shared interpreter; TTT outputs are already concrete grids.
2. **Delta analysis**: Compare candidate outputs with ground-truth examples. Any mismatch disqualifies the candidate.
3. **Constraint traces**: Capture failure reasons (first mismatching coordinate, violated invariant) and forward them to the originating module for potential retries.
4. **SMT attestation**: LLM candidates must carry a success token from the SMT gatekeeper (see `docs/SMT_GATEKEEPER.md`). Symbolic programs optionally carry e-graph proof summaries when rewrites were applied.

Only candidates that pass these checks enter the voting stage.

## Candidate Scoring
- **Module priors**: Each lane maintains a rolling success rate; higher rates increase the base score.
- **Confidence metrics**:
  - Symbolic: program complexity cost (lower is better) and e-graph stability.
  - TTT: ensemble variance and final loss magnitude.
  - LLM: log-probability of the emitted program and SMT solver slack.
- **Runtime penalty**: Candidates produced near the hard timeout incur a small penalty to prevent late, potentially unstable answers from overriding earlier confident solutions.
- **Diversity bonus**: Solutions with distinct transformation signatures (different DSL primitives, different grid edits) receive a bonus when building pass@2 submissions.

Scores are normalised to [0, 1] before ranking.

## Voting And Selection
1. Sort candidates by score.
2. Choose the top candidate as the primary answer if it exceeds a confidence threshold (default 0.65). If no candidate meets the threshold, select the highest-scoring option and flag the task as low confidence for analysis.
3. For pass@2:
   - If a second candidate exists whose score is within 10% of the primary and differs in transformation signature, emit it as the secondary answer.
   - Otherwise, run diversification heuristics (e.g., request an alternative from the next-best module) until a suitable secondary candidate is found or the budget expires.
4. Record the module provenance, score, and any supporting rationale strings for both answers.

## Conflict Resolution
- If two candidates tie within numerical tolerance, prefer the one from the module with higher recent success.
- If modules produce identical outputs, the arbitrator keeps a single entry but retains provenance of all contributing modules for traceability.
- If no candidate survives consistency checks, trigger fallback templates or return a conservative guess while logging a failure event.

## Logging And Telemetry
- Every decision includes timestamps, candidate identifiers, score breakdown, and verification latency.
- Logs feed `docs/PERF_BUDGET.md` dashboards and inform scheduler feedback loops.
- Failure cases automatically enqueue for ARC-Forge adversarial task generation (see `docs/DATASETS.md`).
- Structured decision summaries live under `logs/arbitrator/decisions/`, with verification traces in `logs/arbitrator/verification/` for counterexample replay.
- Daily markdown reports (`reports/arbitration_summary_<date>.md`) and health dashboards (`reports/arbitrator_health_<date>.md`) track fallback usage, confidence distribution, and latency trends.
