# Arbitration Summary (20251105)

## Task sample_task

- Answers emitted: 1
- Low confidence: False
- Fallback used: True
- Solve latency: 2.7 ms
  - Candidate fallback-0 (module=fallback) score=1.000
- Rationale:
  - Primary candidate fallback-0 selected with score 1.000.
  - Secondary candidate not selected due to insufficient diversity or score gap.
- Rejected candidates:
  - symbolic-0 [symbolic] status=rejected reason=smt_attestation_failed:missing_smt_token
  - ttt-stub-sample_task [ttt] status=failed reason=output_mismatch
  - llm-stub-sample_task [llm] status=failed reason=output_mismatch
  - fallback-1 [fallback] status=passed reason=None
