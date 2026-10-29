"""CSV Rescue: local-only cleaning with optional Ollama rule suggestions."""
import json
import urllib.error
import urllib.request
from .profiler import profile_csv
from html import escape
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from csv_rescue.core import ALLOWED, clean, read_csv, audit_csv
from csv_rescue.profiler import profile_csv
from csv_rescue.recommend import recommend, compatible

app = FastAPI(title="CSV Rescue")
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "qwen3:8b"
MAX_BYTES = 5_000_000


def ask_ollama(prompt: str) -> str:
    payload = {"model": OLLAMA_MODEL, "stream": False, "think": False,
               "format": "json", "messages": [
                   {"role": "system", "content": "Recommend conservative CSV cleaning rules. Never invent missing values. Return a JSON object with a rules array."},
                   {"role": "user", "content": prompt}]}
    request = urllib.request.Request(OLLAMA_URL, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
        return result["message"]["content"]
    except (urllib.error.URLError, TimeoutError, KeyError) as exc:
        raise ValueError(f"Ollama request failed: {exc}") from exc


async def csv_text(file: UploadFile) -> str:
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Maximum file size is 5 MB")
    return raw.decode("utf-8-sig")


def validated_rules(rules, columns):
    if not isinstance(rules, list):
        raise ValueError("Rules must be a JSON array")
    accepted, rejected = [], []
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("operation") not in ALLOWED:
            rejected.append(rule)
            continue
        op = rule["operation"]
        if op == "deduplicate":
            keys = rule.get("columns")
            if isinstance(keys, list) and keys and all(isinstance(k, str) and k in columns for k in keys):
                normalized = {"operation": op, "columns": keys}
            else:
                rejected.append(rule)
                continue
        elif isinstance(rule.get("column"), str) and rule["column"] in columns:
            normalized = {"operation": op, "column": rule["column"]}
        else:
            rejected.append(rule)
            continue
        if not compatible(normalized, columns):
            rejected.append(rule)
            continue
        if normalized not in accepted:
            accepted.append(normalized)
    return accepted, rejected


@app.get("/", response_class=HTMLResponse)
def home():
    return HTML

@app.post("/recommend")
async def recommendations(
    file: UploadFile = File(...),
    shopify_mode: bool = Form(False),
):
    try:
        content = await csv_text(file)
        columns, rows = read_csv(content)
        return {
            "columns": columns,
            "total_rows": len(rows),
            "shopify_detected": {
                "Handle", "Title", "Variant SKU", "Variant Price"
            }.issubset(columns),
            "recommended_rules": recommend(
                content, shopify_mode=shopify_mode
            ),
        }
    except (ValueError, UnicodeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/analyze")
async def analyze(file: UploadFile = File(...)):
    try:
        content = await csv_text(file)
        columns, rows = read_csv(content)
        profile = profile_csv(content)

        prompt = f"""
You are analyzing a CSV file to recommend safe cleaning operations.

The following profile was calculated by Python across the ENTIRE CSV:

{json.dumps(profile, ensure_ascii=False)}

Supported operations:
- trim_whitespace: Remove leading/trailing whitespace.
- normalize_blank: Convert N/A, NA, null, none, and - to blank.
- normalize_currency: Convert dollar amounts to decimal numbers.
- normalize_date: Convert recognized dates to YYYY-MM-DD.
- deduplicate: Remove exact duplicate records.

Return a JSON object containing a "rules" array.

Example:
{{
  "rules": [
    {{"operation": "trim_whitespace", "column": "Customer"}}
  ]
}}

For exact deduplication, use:
{{"operation": "deduplicate", "columns": {json.dumps(columns)}}}

Important:
- Recommend operations only when the profile provides evidence.
- Use exact column names.
- Never invent missing values.
- Recommend deduplication only when exact_duplicate_rows is greater than zero.
- If recommending deduplication, use ALL columns as the keys.
- Do not recommend unsupported operations.
"""

        parsed = json.loads(ask_ollama(prompt))
        proposed = parsed.get("rules") if isinstance(parsed, dict) else parsed

        accepted, rejected = validated_rules(proposed, columns)
        # Merge Python's evidence-backed candidates with AI suggestions.
        for candidate in profile["candidate_rules"]:
            if candidate not in accepted:
                accepted.append(candidate)
                
        evidence_checked = []

        for rule in accepted:
            operation = rule["operation"]

            if operation == "trim_whitespace":
                column = rule["column"]
                supported = (
                    profile["columns"][column]["whitespace_count"] > 0
                )

            elif operation == "deduplicate":
                supported = (
                    profile["exact_duplicate_rows"] > 0
                    and rule["columns"] == columns
                )

            else:
                # Currency, date, and blank validation come next.
                supported = True

            if supported:
                evidence_checked.append(rule)
            else:
                rejected.append(rule)

        accepted = [r for r in evidence_checked if compatible(r, columns)]

        return {
            "columns": columns,
            "sample_rows": min(len(rows), 15),
            "total_rows": len(rows),
            "recommended_rules": accepted,
            "rejected_rules": rejected,
            "profile": profile,
        }

    except (ValueError, UnicodeError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/preview")
async def preview(file: UploadFile = File(...), rules: str = Form(...)):
    try:
        content = await csv_text(file)
        columns, original = read_csv(content)
        accepted, rejected = validated_rules(json.loads(rules), columns)
        if rejected:
            raise ValueError("One or more rules are invalid")
        result = clean(content, accepted)
        _, after = read_csv(result["csv"])
        return {"columns": columns, "before": original[:10], "after": after[:10],
                "changes": result["changes"][:30], "change_count": len(result["changes"]),
                "flagged": result["flagged"][:30], "flagged_count": len(result["flagged"]),
                "input_rows": result["input_rows"], "output_rows": result["output_rows"], "output_source_rows": result["source_rows"][:10]}
    except (ValueError, UnicodeError, TypeError, json.JSONDecodeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/report")
async def report(file: UploadFile = File(...), rules: str = Form(...)):
    try:
        content = await csv_text(file)
        columns, _ = read_csv(content)
        accepted, rejected = validated_rules(json.loads(rules), columns)
        if rejected:
            raise ValueError("One or more rules are invalid")
        result = clean(content, accepted)
        return Response(audit_csv(result), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="change-report.csv"'})
    except (ValueError, UnicodeError, TypeError, json.JSONDecodeError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@app.post("/clean")
async def process(file: UploadFile = File(...), rules: str = Form(...)):
    try:
        content = await csv_text(file)
        columns, _ = read_csv(content)
        accepted, rejected = validated_rules(json.loads(rules), columns)
        if rejected:
            raise ValueError("One or more rules are invalid")
        result = clean(content, accepted)
        return Response(result["csv"], media_type="text/csv", headers={
            "Content-Disposition": 'attachment; filename="cleaned.csv"',
            "X-Change-Count": str(len(result["changes"])),
            "X-Flagged-Count": str(len(result["flagged"]))})
    except (ValueError, UnicodeError, TypeError, json.JSONDecodeError) as exc:
        return HTMLResponse(f"<h2>Could not clean CSV</h2><pre>{escape(str(exc))}</pre><a href='/'>Try again</a>", status_code=400)


HTML = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CSV Rescue</title><style>
:root{color-scheme:dark}body{font:16px system-ui,sans-serif;background:#111827;color:#f9fafb;max-width:1080px;margin:40px auto;padding:0 22px}h1{font-size:2.4rem;margin-bottom:4px}h2{font-size:1.2rem}p,small{color:#bac4d2}.panel{background:#1f2937;border:1px solid #374151;border-radius:12px;padding:22px;margin:20px 0}button{background:#fb923c;color:#111827;border:0;border-radius:7px;padding:11px 18px;font-weight:750;cursor:pointer;margin:5px 8px 5px 0}button:disabled{opacity:.45;cursor:not-allowed}.secondary{background:#374151;color:#fff}input[type=file]{margin:12px 0}.rule{display:block;margin:12px 0;padding:10px;border:1px solid #475569;border-radius:7px}input[type=checkbox]{accent-color:#fb923c;transform:scale(1.2);margin-right:10px}.muted{color:#9ca3af}#status{min-height:24px;color:#fdba74}table{border-collapse:collapse;width:100%;font-size:.85rem}th,td{border:1px solid #475569;padding:7px;text-align:left;max-width:240px;overflow-wrap:anywhere}th{background:#374151}.scroll{overflow:auto;max-height:360px} .data-preview table{width:max-content;min-width:100%;table-layout:auto} .data-preview th,.data-preview td{min-width:130px;max-width:260px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;overflow-wrap:normal} .data-preview td:hover{white-space:normal;overflow:visible} .changed-cell{background:#294a3b;color:#d1fae5;box-shadow:inset 0 0 0 1px #4ade80} .warning-note{border-left:3px solid #fbbf24;padding:8px 12px;background:#3a3020;margin:12px 0} .result-block{margin-top:22px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#111827;padding:12px;border-radius:6px} .cols{display:grid;grid-template-columns:minmax(0,1fr);gap:18px;min-width:0}.cols>div{min-width:0;max-width:100%}.data-preview{width:100%;max-width:100%;overflow-x:auto;overflow-y:auto;box-sizing:border-box}.data-preview table{width:max-content;min-width:100%}#results{min-width:0;overflow:hidden}
</style></head><body>
<h1>CSV Rescue</h1><p>Local CSV cleanup, with optional Qwen3 recommendations. Your original file is never modified.</p>
<section class="panel"><h2>1. Choose a CSV</h2><input id="file" type="file" accept=".csv,text/csv"><p class="muted">Maximum 5 MB. Data is processed locally; analysis sends a statistical profile to your local Ollama server.</p><button id="analyze" disabled>Analyze with AI</button><button id="manual" class="secondary" disabled>Get safe recommendations</button><p id="status" role="status" aria-live="polite"></p></section>

<section class="panel" id="review" hidden>
  <h2>2. Review cleaning rules</h2>
  <p>Compatible rules are recommended automatically. Review them before approving.</p>

  <label class="rule">
    <input type="checkbox" id="shopify-mode" disabled>
    <span>
      <strong>Use Shopify-aware recommendations</strong>
      <small style="display:block;opacity:.7">
        Use conservative Shopify-specific rules for products and variants.
        Avoid unnecessary normalization and optional-field warnings.
      </small>
    </span>
  </label>

  <div>
    <button type="button" class="secondary" id="select-all">Select All Recommended</button>
    <button type="button" class="secondary" id="clear-all">Clear All</button>
  </div>

  <div id="rules"></div>
  <button id="preview" disabled>Preview selected changes</button>
</section>


</section>
<section class="panel" id="results" hidden><h2>3. Preview results</h2><p id="summary"></p><div class="cols"><div><h3>Original (first 10 rows)</h3><div id="before" class="scroll data-preview"></div></div><div><h3>Cleaned (first 10 rows)</h3><div id="after" class="scroll data-preview"></div></div></div><div class="result-block"><h3>Automatic corrections</h3><p class="muted">Green cells in the cleaned preview have changed. Hover over a cell to read long values.</p><div id="changes" class="scroll"></div></div><div class="result-block"><h3>Warnings requiring review</h3><p class="warning-note">Warnings are not automatically fixed. Review these before using the cleaned CSV.</p><div id="flagged" class="scroll"></div></div><p class="muted">Preview shows up to 10 rows and 30 changes/issues. Download the complete change report for all changes and flagged issues.</p><button id="download">Approve & download cleaned CSV</button><button id="report" class="secondary">Download complete change report</button></section>
<script>
const $=id=>document.getElementById(id);let selectedFile=null,columns=[],suggestions=[],lastPreviewRules=null;
const names={normalize_boolean:'Normalize Yes/No to TRUE/FALSE',flag_blank:'Flag blank values',flag_duplicate:'Flag duplicate identifiers',flag_barcode:'Flag suspicious barcodes',flag_shopify_handle:'Check Shopify handle formatting',trim_whitespace:'Trim whitespace',normalize_blank:'Normalize blank values',normalize_currency:'Normalize currency',normalize_date:'Normalize dates',deduplicate:'Remove duplicate rows'};
function status(s){$('status').textContent=s}
function reset(){suggestions=[];columns=[];lastPreviewRules=null;$('review').hidden=true;$('results').hidden=true;$('rules').replaceChildren()}
$('file').addEventListener('change',()=>{selectedFile=$('file').files[0]||null;reset();$('analyze').disabled=!selectedFile;$('manual').disabled=!selectedFile;status(selectedFile?selectedFile.name+' selected':'')});

async function send(path,rules){
  const body=new FormData();
  body.append('file',selectedFile,selectedFile.name);

  if(path==='/recommend'){
    body.append('shopify_mode',$('shopify-mode').checked?'true':'false');
  }

  if(rules!==undefined){
    body.append('rules',JSON.stringify(rules));
  }

  const response=await fetch(path,{method:'POST',body});

  if(path==='/clean'||path==='/report'){
    if(!response.ok){
      throw new Error((await response.text()).replace(/<[^>]*>/g,' ').slice(0,400));
    }
    return response.blob();
  }

  const result=await response.json();
  if(!response.ok||result.error){
    throw new Error(result.error||'Request failed');
  }
  return result;
}
function renderRules(){const box=$('rules');box.replaceChildren();suggestions.forEach((rule,i)=>{const label=document.createElement('label');label.className='rule';const check=document.createElement('input');check.type='checkbox';check.checked=true;check.dataset.index=String(i);check.addEventListener('change',()=>{$('results').hidden=true;lastPreviewRules=null});const text=document.createElement('span');text.textContent=(names[rule.operation]||rule.operation)+' — '+(rule.column||rule.columns.join(', '));label.append(check,text);box.append(label)});$('review').hidden=false;$('preview').disabled=!suggestions.length}
function setAllRules(checked){$('rules').querySelectorAll('input[type=checkbox]').forEach(el=>{el.checked=checked});$('results').hidden=true;lastPreviewRules=null;$('preview').disabled=!checked||!suggestions.length}
$('select-all').onclick=()=>setAllRules(true);$('clear-all').onclick=()=>setAllRules(false);
function chosen(){return [...$('rules').querySelectorAll('input:checked')].map(el=>suggestions[Number(el.dataset.index)])}
function table(target,rows,cols,changedKeys=null,sourceRows=null){const host=$(target);host.replaceChildren();if(!rows.length){host.textContent='No rows';return}const t=document.createElement('table'),head=document.createElement('tr');cols.forEach(c=>{const th=document.createElement('th');th.textContent=c;head.append(th)});t.append(head);rows.forEach((r,i)=>{const tr=document.createElement('tr');cols.forEach(c=>{const td=document.createElement('td');td.textContent=String(r[c]??'');td.title=String(r[c]??'');if(changedKeys&&sourceRows&&changedKeys.has(String(sourceRows[i])+'\u0000'+c)){td.classList.add('changed-cell');td.title='Changed from original: '+td.title}tr.append(td)});t.append(tr)});host.append(t)}
$('analyze').onclick=async()=>{if(!selectedFile)return;reset();status('Analyzing with Qwen3… this may take a minute.');$('analyze').disabled=true;try{const result=await send('/analyze');columns=result.columns;suggestions=result.recommended_rules;renderRules();status(`${suggestions.length} suggested rules. ${result.rejected_rules.length} rejected.`);if(!suggestions.length)status('No safe rules suggested. You can choose manual rules.')}catch(e){status('Analysis error: '+e.message)}finally{$('analyze').disabled=false}};
$('manual').onclick=async()=>{if(!selectedFile)return;reset();status('Analyzing columns...');$('manual').disabled=true;try{const result=await send('/recommend');columns=result.columns;const checkbox=$('shopify-mode');checkbox.disabled=!result.shopify_detected;checkbox.checked=Boolean(result.shopify_detected);if(checkbox.checked){const shopifyResult=await send('/recommend');suggestions=shopifyResult.recommended_rules;}else{suggestions=result.recommended_rules;}renderRules();status(`${suggestions.length} safe rules recommended.`);if(!suggestions.length)status('No safe cleaning operations identified.')}catch(e){status('Recommendation error: '+e.message)}finally{$('manual').disabled=false}};
$('shopify-mode').onchange=async()=>{
  if(!selectedFile)return;

  $('results').hidden=true;
  lastPreviewRules=null;
  status('Updating recommendations...');

  try{
    const result=await send('/recommend');
    columns=result.columns;
    suggestions=result.recommended_rules;
    renderRules();
    status(`${suggestions.length} recommendations updated.`);
  }catch(e){
    status('Recommendation error: '+e.message);
  }
};
$('preview').onclick=async()=>{const rules=chosen();if(!rules.length){status('Select at least one rule.');return}status('Generating preview…');$('preview').disabled=true;try{const result=await send('/preview',rules);table('before',result.before,result.columns);const originalBySource=new Map(result.before.map((r,i)=>[i+2,r]));const changedKeys=new Set();result.after.forEach((r,i)=>{const src=result.output_source_rows[i],original=originalBySource.get(src);if(original)result.columns.forEach(c=>{if(String(original[c]??'')!==String(r[c]??''))changedKeys.add(String(src)+'\u0000'+c)})});table('after',result.after,result.columns,changedKeys,result.output_source_rows);table('changes',result.changes,['row','column','operation','before','after']);table('flagged',result.flagged,['row','column','value','reason','note']);$('summary').textContent=`${result.input_rows} input rows → ${result.output_rows} output rows; ${result.change_count} cell changes; ${result.flagged_count} flagged issues.`;$('results').hidden=false;lastPreviewRules=JSON.stringify(rules);status('Preview ready. Review before downloading.')}catch(e){status('Preview error: '+e.message)}finally{$('preview').disabled=false}};
$('report').onclick=async()=>{const rules=chosen();if(JSON.stringify(rules)!==lastPreviewRules){status('Rules changed. Preview again before downloading.');return}try{const blob=await send('/report',rules);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='change-report.csv';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);status('Downloaded complete change report.')}catch(e){status('Report error: '+e.message)}};
$('download').onclick=async()=>{const rules=chosen();if(JSON.stringify(rules)!==lastPreviewRules){status('Rules changed. Preview again before downloading.');$('results').hidden=true;return}status('Preparing download…');try{const blob=await send('/clean',rules);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='cleaned.csv';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);status('Downloaded cleaned.csv. Original unchanged.')}catch(e){status('Download error: '+e.message)}};
</script></body></html>'''
