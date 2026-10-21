# CSV Rescue — Hacktoberfest starter

Local-first CSV cleanup with explicit, auditable operations. **This is a working foundation, not the finished AI product.**

## Run on Windows (PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn csv_rescue.app:app --host 127.0.0.1 --port 8767 --reload
```

Visit http://127.0.0.1:8767, upload `samples/messy.csv`, and use the default rules.

## Test

```powershell
python -m pytest -q
```

## Safety and current limitations

- Original file is never overwritten.
- CSV is processed on the local machine, not uploaded to a third-party service.
- Rules must be manually specified as JSON. AI rule suggestions, preview/approval UI, and downloadable audit report are **not implemented yet**.
- Deduplication omits later matching rows from output and reports them in the Python API; the current browser download does not expose the full audit details.
- Max file size 5 MB; CSV must be UTF-8 and have unique headers.
- Date conversion supports YYYY-MM-DD, MM/DD/YYYY, MM/DD/YY, YYYY/MM/DD; ambiguous date conventions require review.
- Currency conversion strips $ and commas and emits two decimal places; do not use for high-precision accounting values.

## Next milestone

1. Add a preview + approval screen and downloadable change/exception reports.
2. Integrate Ollama via localhost, require structured JSON proposals, and validate proposals against the allowlist.
3. Add a compelling before/after demo and document local-only privacy properties.

License: choose and add an OSI-approved license before publishing.
