#!/usr/bin/env python3
"""Run SQL against the Dazana-classic-ws serverless warehouse.

Usage:
    ./run_sql.py "SELECT 1"
    ./run_sql.py -f file.sql           # splits on `;` and runs each statement
    ./run_sql.py -f file.sql --no-split  # runs whole content as one statement
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

PROFILE = "Dazana-classic-ws-pat"
WAREHOUSE = "a82088b3bfe8752c"


def db_api(method: str, path: str, body: dict | None = None) -> dict:
    cmd = ["databricks", "api", method, path, f"--profile={PROFILE}"]
    if body is not None:
        cmd.append(f"--json={json.dumps(body)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"API error: {r.stderr}\n{r.stdout}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def run_statement(stmt: str, warehouse: str = WAREHOUSE, timeout_s: int = 600,
                  catalog: str | None = None, schema: str | None = None) -> dict:
    body = {
        "statement": stmt,
        "warehouse_id": warehouse,
        "wait_timeout": "50s",
        "on_wait_timeout": "CONTINUE",
        "disposition": "INLINE",
        "format": "JSON_ARRAY",
    }
    if catalog:
        body["catalog"] = catalog
    if schema:
        body["schema"] = schema
    resp = db_api("post", "/api/2.0/sql/statements", body)
    sid = resp["statement_id"]
    deadline = time.time() + timeout_s
    while True:
        state = resp.get("status", {}).get("state")
        if state in ("SUCCEEDED", "FAILED", "CANCELED", "CLOSED"):
            return resp
        if time.time() > deadline:
            raise TimeoutError(f"Statement {sid} timed out, last state {state}")
        time.sleep(2)
        resp = db_api("get", f"/api/2.0/sql/statements/{sid}")


def split_sql(text: str) -> list[str]:
    """Split SQL text on ; while ignoring those inside strings/comments."""
    out, buf, in_s, in_d, in_line, in_block = [], [], False, False, False, False
    i = 0
    while i < len(text):
        c = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line:
            buf.append(c)
            if c == "\n":
                in_line = False
        elif in_block:
            buf.append(c)
            if c == "*" and nxt == "/":
                buf.append(nxt)
                i += 1
                in_block = False
        elif in_s:
            buf.append(c)
            if c == "'" and nxt == "'":
                buf.append(nxt)
                i += 1
            elif c == "'":
                in_s = False
        elif in_d:
            buf.append(c)
            if c == '"':
                in_d = False
        elif c == "-" and nxt == "-":
            in_line = True
            buf.append(c)
        elif c == "/" and nxt == "*":
            in_block = True
            buf.append(c)
        elif c == "'":
            in_s = True
            buf.append(c)
        elif c == '"':
            in_d = True
            buf.append(c)
        elif c == ";":
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
        else:
            buf.append(c)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def print_result(resp: dict, stmt_preview: str) -> bool:
    state = resp.get("status", {}).get("state")
    if state != "SUCCEEDED":
        err = resp.get("status", {}).get("error", {})
        print(f"FAIL  | {stmt_preview}")
        print(f"      | state={state} message={err.get('message','')}", file=sys.stderr)
        return False
    res = resp.get("result", {})
    rows = res.get("data_array")
    cols = [c["name"] for c in resp.get("manifest", {}).get("schema", {}).get("columns", [])]
    if rows is not None:
        print(f"OK    | {stmt_preview}  ({len(rows)} rows)")
        if rows:
            print("        " + " | ".join(cols))
            for row in rows[:50]:
                print("        " + " | ".join(str(v) for v in row))
            if len(rows) > 50:
                print(f"        ... {len(rows) - 50} more rows")
    else:
        print(f"OK    | {stmt_preview}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sql", nargs="?")
    ap.add_argument("-f", "--file")
    ap.add_argument("--no-split", action="store_true")
    ap.add_argument("--stop-on-error", action="store_true", default=True)
    ap.add_argument("--continue-on-error", action="store_true")
    ap.add_argument("--catalog")
    ap.add_argument("--schema")
    args = ap.parse_args()

    if args.file:
        text = Path(args.file).read_text()
    elif args.sql:
        text = args.sql
    else:
        ap.error("Provide SQL or -f file.sql")

    statements = [text] if args.no_split else split_sql(text)
    stop = not args.continue_on_error

    n_ok, n_fail = 0, 0
    for stmt in statements:
        prev = re.sub(r"\s+", " ", stmt)[:90]
        try:
            resp = run_statement(stmt, catalog=args.catalog, schema=args.schema)
        except Exception as e:
            print(f"FAIL  | {prev}\n      | exception: {e}", file=sys.stderr)
            n_fail += 1
            if stop:
                return 2
            continue
        ok = print_result(resp, prev)
        if ok:
            n_ok += 1
        else:
            n_fail += 1
            if stop:
                return 2
    print(f"\nSummary: {n_ok} ok, {n_fail} failed, {len(statements)} total")
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
