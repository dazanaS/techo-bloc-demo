#!/usr/bin/env python3
"""Benchmark the Techo-Bloc Genie space.

For each question:
  - start a conversation
  - poll the message until terminal status
  - capture: total latency, generated SQL, attachment summary, row count, error
Then print a markdown summary table.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

PROFILE = "Dazana-classic-ws-pat"
SPACE_ID = "01f143e3caf119e3b09d967d4ef4fc91"
WAREHOUSE = "a82088b3bfe8752c"

QUESTIONS: list[tuple[str, str]] = [
    ("kpi_metric_view",
     "What is our total net revenue by product line over the last year?"),
    ("kpi_margin",
     "Which territory has the highest gross margin %?"),
    ("top_customers",
     "Show me the top 10 customers by lifetime revenue, broken out by segment."),
    ("ar_aging",
     "What is the AR aging across all customers, by territory?"),
    ("system_split",
     "How does revenue from D365_FO compare to AX_2012 over the last 24 months?"),
    ("campaigns",
     "Which campaigns drove the most quote-request events in 2026?"),
    ("trend",
     "What's the gross margin trend, monthly, by product line?"),
    ("complex_join",
     "Which contractors had open pipeline > $100K but no invoice activity in the last 90 days?"),
    ("discount_segment",
     "What's our discount % by customer segment this year?"),
    ("gl_5yr",
     "Show GL spend by category over the last 5 years (revenue, COGS, OpEx, CapEx)."),
    ("yoy_growth",
     "Which products had the largest year-over-year revenue growth?"),
    ("share_segment",
     "What share of revenue comes from each customer segment, by territory?"),
]


def db_api(method: str, path: str, body: dict | None = None) -> dict:
    cmd = ["databricks", "api", method, path, f"--profile={PROFILE}"]
    if body is not None:
        cmd.append(f"--json={json.dumps(body)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"API error ({path}): {r.stderr or r.stdout}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


@dataclass
class Result:
    label: str
    question: str
    status: str = ""
    total_seconds: float = 0.0
    sql: str = ""
    attachment_kind: str = ""
    row_count: int | None = None
    error: str = ""
    poll_count: int = 0


def run_one(label: str, question: str, max_wait_s: int = 240, poll_s: float = 3.0) -> Result:
    res = Result(label=label, question=question)
    t0 = time.time()
    try:
        start = db_api("post", f"/api/2.0/genie/spaces/{SPACE_ID}/start-conversation",
                       {"content": question})
    except Exception as e:
        res.status = "ERROR_START"
        res.error = str(e)[:300]
        res.total_seconds = time.time() - t0
        return res

    conv_id = start["conversation_id"]
    msg_id = start["message_id"]

    # Poll until terminal
    while True:
        if time.time() - t0 > max_wait_s:
            res.status = "TIMEOUT"
            break
        res.poll_count += 1
        try:
            msg = db_api("get",
                         f"/api/2.0/genie/spaces/{SPACE_ID}/conversations/{conv_id}/messages/{msg_id}")
        except Exception as e:
            res.status = "ERROR_POLL"
            res.error = str(e)[:300]
            break
        status = msg.get("status", "")
        res.status = status
        if status in ("COMPLETED", "FAILED", "CANCELLED"):
            # capture SQL/attachment from the message
            attachments = msg.get("attachments") or []
            for att in attachments:
                if "query" in att:
                    q = att["query"] or {}
                    res.sql = (q.get("query") or "").strip()
                    res.attachment_kind = "query"
                    break
                if "text" in att:
                    res.attachment_kind = res.attachment_kind or "text"
            if status == "FAILED":
                res.error = (msg.get("error") or {}).get("error", "") or json.dumps(msg.get("error", {}))[:300]
            break
        time.sleep(poll_s)

    res.total_seconds = time.time() - t0

    # Optional: try to fetch query results to get row count if SQL was produced
    if res.sql and res.status == "COMPLETED":
        try:
            # The Genie API exposes a query-result subroute
            attachments = msg.get("attachments") or []
            attach_id = None
            for att in attachments:
                if att.get("query") and att.get("attachment_id"):
                    attach_id = att["attachment_id"]
                    break
            if attach_id:
                qr = db_api("get",
                            f"/api/2.0/genie/spaces/{SPACE_ID}/conversations/{conv_id}/messages/{msg_id}/attachments/{attach_id}/query-result")
                rows = ((qr.get("statement_response") or {}).get("result") or {}).get("data_array") or []
                res.row_count = len(rows)
        except Exception:
            pass

    return res


def write_markdown(results: list[Result], out_path: Path) -> None:
    ok = [r for r in results if r.status == "COMPLETED"]
    fail = [r for r in results if r.status != "COMPLETED"]
    p50 = statistics.median(r.total_seconds for r in results) if results else 0
    p95 = statistics.quantiles([r.total_seconds for r in results], n=20)[-1] if len(results) > 1 else 0
    avg = statistics.mean(r.total_seconds for r in results) if results else 0

    lines = [
        f"# Techo-Bloc Genie Benchmark",
        f"",
        f"- Space: `{SPACE_ID}`",
        f"- Warehouse: `{WAREHOUSE}` (Serverless Starter, Small)",
        f"- Questions: **{len(results)}** • Completed: **{len(ok)}** • Failed: **{len(fail)}**",
        f"- Latency — avg: **{avg:.1f}s** • p50: **{p50:.1f}s** • p95: **{p95:.1f}s**",
        f"",
        f"## Per-question results",
        f"",
        f"| # | Label | Status | Latency | Rows | Question |",
        f"|---|---|---|---:|---:|---|",
    ]
    for i, r in enumerate(results, 1):
        rows = "—" if r.row_count is None else str(r.row_count)
        lines.append(f"| {i} | `{r.label}` | {r.status} | {r.total_seconds:.1f}s | {rows} | {r.question} |")

    lines += ["", "## SQL produced by Genie", ""]
    for i, r in enumerate(results, 1):
        lines += [
            f"### {i}. {r.label} — _{r.question}_",
            f"**status:** {r.status} • **latency:** {r.total_seconds:.1f}s" + (
                f" • **rows:** {r.row_count}" if r.row_count is not None else ""),
        ]
        if r.error:
            lines += ["", f"**error:** `{r.error}`"]
        if r.sql:
            lines += ["", "```sql", r.sql, "```"]
        else:
            lines += ["", "_(no SQL produced)_"]
        lines += [""]

    out_path.write_text("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output", default="benchmark_results.md")
    ap.add_argument("--limit", type=int, default=0, help="Run only first N questions")
    args = ap.parse_args()

    qs = QUESTIONS if args.limit <= 0 else QUESTIONS[:args.limit]

    results: list[Result] = []
    for i, (label, q) in enumerate(qs, 1):
        print(f"[{i}/{len(qs)}] {label}: {q[:90]}", flush=True)
        r = run_one(label, q)
        marker = "OK" if r.status == "COMPLETED" else r.status
        rows = "" if r.row_count is None else f" • rows={r.row_count}"
        print(f"   → {marker} • {r.total_seconds:.1f}s{rows}", flush=True)
        results.append(r)

    out = Path(args.output)
    write_markdown(results, out)
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
