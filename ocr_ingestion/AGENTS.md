# OCR ingestion work

Read `README.md` before changing this package. Keep extraction, human review, persistence, and reference evaluation separate; contract validation is a later phase. Preserve the stored schema and full identifiers, source wording, unknown values, and explicit review requirements. Do not modify existing notebook source or comments. Never commit real documents, extracted records, private evidence, or saved notebook outputs.

When present locally, read the ignored `INSTRUCTIONS.md` and `../MEMORY.md` before changing this package. They record approved requirements, private findings, and implementation history; update the local progress checklist when a milestone is verified. Fresh clones do not include these private handoffs. Recheck live state rather than treating a handoff as automatically current. Keep all source documents, extracted data, evidence, and evaluation reports in ignored local storage.

Run `python -m pytest -q` from the repository root using the development dependencies. Keep regression tests synthetic and generate document fixtures in temporary directories. Do not commit, push, or open a PR without a user request.
