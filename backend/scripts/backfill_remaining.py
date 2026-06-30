"""Backfill all remaining JSON data to new Supabase tables."""

import json
import subprocess
from pathlib import Path

DB_URL = "postgresql://postgres:postgres@127.0.0.1:6432/postgres"
DATA = Path("/opt/bms-intelligence/backend/app/data")


def _run(sql: str) -> None:
    subprocess.run(["psql", DB_URL, "-c", sql], capture_output=True, timeout=30)


def _quote(val: str) -> str:
    return val.replace("'", "''")


def backfill_privacy_requests():
    path = DATA / "privacy_requests.json"
    if not path.exists():
        return
    data = json.loads(path.read_text())
    for rec in data.get("requests", []):
        assigned = "NULL" if not rec.get("assigned_to") else f"'{_quote(rec['assigned_to'])}'"
        closed = "NULL" if not rec.get("closed_at") else f"'{rec['closed_at']}'::timestamptz"
        outcome = "NULL" if not rec.get("outcome_summary") else f"'{_quote(rec['outcome_summary'])}'"
        meta = json.dumps(rec.get("metadata", {})).replace("'", "''")
        ev = json.dumps(rec.get("evidence_refs", [])).replace("'", "''")
        sql = (
            f"INSERT INTO public.privacy_requests "
            f"(request_id, data_subject_hash, request_type, channel, status, details, "
            f"requested_by, assigned_to, due_at, closed_at, created_at, outcome_summary, "
            f"evidence_refs, metadata) VALUES ("
            f"'{rec['request_id']}'::uuid, '{rec['data_subject_hash']}', "
            f"'{rec['request_type']}', '{rec['channel']}', '{rec['status']}', "
            f"'{_quote(rec.get('details', ''))}', '{rec.get('requested_by', '')}', "
            f"{assigned}, '{rec['due_at']}'::timestamptz, {closed}, "
            f"'{rec['created_at']}'::timestamptz, {outcome}, "
            f"'{ev}'::jsonb, '{meta}'::jsonb"
            f") ON CONFLICT (request_id) DO NOTHING;"
        )
        _run(sql)
    print(f"privacy_requests: {len(data.get('requests', []))} records")


def backfill_retention_runs():
    path = DATA / "popia_retention_runs.json"
    if not path.exists():
        return
    data = json.loads(path.read_text())
    for run in data.get("runs", []):
        cats = json.dumps(run.get("categories", [])).replace("'", "''")
        errs = json.dumps(run.get("errors", [])).replace("'", "''")
        sql = (
            f"INSERT INTO public.popia_retention_runs "
            f"(executed_at, dry_run, categories, total_reviewed, total_deleted, errors) VALUES ("
            f"'{run['executed_at']}'::timestamptz, "
            f"{str(run.get('dry_run', True)).lower()}, "
            f"'{cats}'::jsonb, "
            f"{run.get('total_reviewed', 0)}, "
            f"{run.get('total_deleted', 0)}, "
            f"'{errs}'::jsonb"
            f");"
        )
        _run(sql)
    print(f"popia_retention_runs: {len(data.get('runs', []))} runs")


def backfill_lighting():
    for prefix, table in [("lighting", "lighting_sources"), ("dali", "dali_sources")]:
        path = DATA / f"{prefix}_sources.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for sid, cfg in data.get("sites", {}).items():
            sc = {k: v for k, v in cfg.items() if k not in ("source", "description")}
            sc_json = json.dumps(sc).replace("'", "''")
            desc = "NULL" if not cfg.get("description") else f"'{_quote(cfg['description'])}'"
            sql = (
                f"INSERT INTO public.{table} "
                f"(site_id, source, source_config, description) VALUES ("
                f"'{sid}', '{cfg.get('source', 'json')}', "
                f"'{sc_json}'::jsonb, {desc}"
                f") ON CONFLICT (site_id, source) DO NOTHING;"
            )
            _run(sql)
        print(f"{table}: {len(data.get('sites', {}))} sites")


def backfill_site_phases():
    path = DATA / "onboarding_phase_state.json"
    if path.exists():
        data = json.loads(path.read_text())
        for key, val in data.items():
            if ":last_transition" in key:
                continue
            sql = f"INSERT INTO public.site_phases (site_id, current_phase) VALUES ('{key}', '{val}') ON CONFLICT (site_id) DO UPDATE SET current_phase = EXCLUDED.current_phase;"
            _run(sql)

        for key, val in data.items():
            if ":last_transition" not in key:
                continue
            site_id = key.replace(":last_transition", "")
            t = val
            reason = "NULL" if not t.get("reason") else f"'{_quote(t['reason'])}'"
            sql = (
                f"INSERT INTO public.site_phase_transitions "
                f"(site_id, from_phase, to_phase, changed_by, reason, transitioned_at) VALUES ("
                f"'{site_id}', '{t.get('from_phase', '')}', '{t.get('to_phase', '')}', "
                f"'{t.get('changed_by', 'system')}', {reason}, "
                f"'{t.get('created_at', '')}'::timestamptz"
                f");"
            )
            _run(sql)

    path = DATA / "site_processing_state.json"
    if path.exists():
        data = json.loads(path.read_text())
        for sid, enabled in data.items():
            sql = (
                f"INSERT INTO public.site_phases (site_id, current_phase, processing_enabled) "
                f"VALUES ('{sid}', 'unknown', {str(enabled).lower()}) "
                f"ON CONFLICT (site_id) DO UPDATE SET processing_enabled = EXCLUDED.processing_enabled;"
            )
            _run(sql)
    print("site_phases + transitions: done")


def backfill_policies():
    pdir = DATA / "policies"
    for f in sorted(pdir.glob("site-*-mode-policy.json")):
        site_id = f.stem.replace("-mode-policy", "")
        policy = json.loads(f.read_text())
        state_file = pdir / f"{site_id}-mode-policy-state.json"
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
        pol_json = json.dumps(policy).replace("'", "''")
        st_json = json.dumps(state).replace("'", "''")
        sql = (
            f"INSERT INTO public.site_mode_policies "
            f"(site_id, policy_json, state_json) VALUES ("
            f"'{site_id}', '{pol_json}'::jsonb, '{st_json}'::jsonb"
            f") ON CONFLICT (site_id) DO UPDATE SET "
            f"policy_json = EXCLUDED.policy_json, state_json = EXCLUDED.state_json;"
        )
        _run(sql)
    print("site_mode_policies: done")


if __name__ == "__main__":
    backfill_privacy_requests()
    backfill_retention_runs()
    backfill_lighting()
    backfill_site_phases()
    backfill_policies()
    print("All backfills complete")
