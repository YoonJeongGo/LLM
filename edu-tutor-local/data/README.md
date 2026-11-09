# Original demo data

45 records: train 25, validation 8, test 12. Each has a distinct substantive problem family. The build script authors the questions, explanations and expected results; no model response is presented as an actual evaluation result.

All records remain `generated_unreviewed`, `demo_only=true`. They are suitable for the explicit demo profile only. SQLite execution can verify the 42 SQL fixtures, but does not turn the Korean explanations into human-reviewed teaching material. Three records concern primary keys, foreign keys and missing information.

`build_demo.py` deterministically writes JSONL files. `edu_tutor.training.audit.audit_dataset` executes schema/rights/family/duplicate checks and each SQL reference against the subprocess sandbox, then writes actual evidence. When an explicit local tokenizer path is supplied, it also records actual token IDs, response masks and target decodes. Validation and test records are never selected for training.

The family validator rejects declared cross-split families, exact duplicate questions/answers and common renamed/numeric SQL variants. It cannot prove every semantic near-duplicate has been caught. The 45-record corpus is a small pipeline exercise, not a statistically meaningful education benchmark. No test answer belongs in the RAG corpus.
