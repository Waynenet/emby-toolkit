import logging
import os
import threading
from typing import Any, Dict, Iterable, List, Optional

from psycopg2.extras import Json, execute_values

from .connection import get_db_connection


logger = logging.getLogger(__name__)
LEGACY_STATE_KEY = "p115_upload_monitor_state"
_migration_lock = threading.Lock()
_migration_done = False


def _record_values(record_key: str, record_type: str, payload: Dict[str, Any]):
    data = dict(payload or {})
    mapping_id = str(data.get("mapping_id") or "")
    local_path = str(data.get("path") or data.get("local_path") or "")
    if record_type == "completed":
        key_parts = str(record_key).split(":", 1)
        mapping_id = mapping_id or key_parts[0]
        local_path = local_path or (key_parts[1] if len(key_parts) > 1 else "")
    return (
        str(record_key),
        record_type,
        mapping_id or None,
        local_path or None,
        str(data.get("relative_path") or "") or None,
        str(data.get("target_cid") or "") or None,
        str(data.get("pick_code") or "") or None,
        str(data.get("status") or ("completed" if record_type == "completed" else "pending")),
        Json(data),
    )


def _upsert_values(cursor, values) -> None:
    if not values:
        return
    execute_values(
        cursor,
        """
        INSERT INTO p115_upload_records (
            record_key, record_type, mapping_id, local_path, relative_path,
            target_cid, pick_code, status, payload_json
        ) VALUES %s
        ON CONFLICT (record_key) DO UPDATE SET
            record_type = EXCLUDED.record_type,
            mapping_id = EXCLUDED.mapping_id,
            local_path = EXCLUDED.local_path,
            relative_path = EXCLUDED.relative_path,
            target_cid = EXCLUDED.target_cid,
            pick_code = EXCLUDED.pick_code,
            status = EXCLUDED.status,
            payload_json = EXCLUDED.payload_json,
            updated_at = NOW()
        """,
        values,
        page_size=500,
    )


def _backfill_completed_pickcodes(cursor) -> int:
    cursor.execute(
        """
        WITH unique_matches AS (
            SELECT r.record_key, MIN(c.pick_code) AS pick_code
            FROM p115_upload_records r
            JOIN p115_filesystem_cache c
              ON LOWER(REPLACE(COALESCE(c.local_path, ''), '\\', '/'))
                 LIKE '%' || LOWER(REPLACE(r.relative_path, '\\', '/'))
             AND COALESCE(c.pick_code, '') <> ''
            WHERE r.record_type = 'completed'
              AND COALESCE(r.pick_code, '') = ''
              AND COALESCE(r.relative_path, '') <> ''
            GROUP BY r.record_key
            HAVING COUNT(DISTINCT c.pick_code) = 1
        )
        UPDATE p115_upload_records r
        SET pick_code = matched.pick_code,
            payload_json = jsonb_set(r.payload_json, '{pick_code}', to_jsonb(matched.pick_code), true),
            updated_at = NOW()
        FROM unique_matches matched
        WHERE r.record_key = matched.record_key
        """
    )
    return int(cursor.rowcount or 0)


def ensure_legacy_state_migrated() -> None:
    global _migration_done
    if _migration_done:
        return
    with _migration_lock:
        if _migration_done:
            return
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT value_json FROM app_settings WHERE setting_key = %s FOR UPDATE",
                    (LEGACY_STATE_KEY,),
                )
                row = cursor.fetchone()
                legacy = (row or {}).get("value_json") if row else None
                values = []
                if isinstance(legacy, dict):
                    for key, payload in (legacy.get("jobs") or {}).items():
                        if isinstance(payload, dict):
                            values.append(_record_values(key, "job", payload))
                    for key, payload in (legacy.get("completed") or {}).items():
                        relative_path = str((payload or {}).get("relative_path") or "") if isinstance(payload, dict) else ""
                        if (
                            isinstance(payload, dict)
                            and not payload.get("derived")
                            and os.path.splitext(relative_path)[1].lower() != ".strm"
                        ):
                            values.append(_record_values(key, "completed", payload))
                _upsert_values(cursor, values)
                backfilled = _backfill_completed_pickcodes(cursor) if row else 0
                if row:
                    cursor.execute("DELETE FROM app_settings WHERE setting_key = %s", (LEGACY_STATE_KEY,))
                conn.commit()
        if values:
            logger.info("  ➜ [115上传监控] 已将 %s 条历史记录迁移到独立上传记录表。", len(values))
        if backfilled:
            logger.info("  ➜ [115上传监控] 已为 %s 条历史上传记录补齐 pick_code。", backfilled)
        _migration_done = True


def list_jobs() -> Dict[str, Dict[str, Any]]:
    ensure_legacy_state_migrated()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT record_key, payload_json FROM p115_upload_records WHERE record_type = 'job'")
            return {str(row["record_key"]): dict(row.get("payload_json") or {}) for row in cursor.fetchall()}


def get_jobs(record_keys: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    ensure_legacy_state_migrated()
    keys = [str(key) for key in record_keys if str(key or "")]
    if not keys:
        return {}
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT record_key, payload_json FROM p115_upload_records WHERE record_type = 'job' AND record_key = ANY(%s)",
                (keys,),
            )
            return {str(row["record_key"]): dict(row.get("payload_json") or {}) for row in cursor.fetchall()}


def get_job(record_key: str) -> Optional[Dict[str, Any]]:
    return get_jobs([record_key]).get(str(record_key))


def get_completed(record_keys: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    ensure_legacy_state_migrated()
    keys = [str(key) for key in record_keys if str(key or "")]
    if not keys:
        return {}
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT record_key, payload_json FROM p115_upload_records WHERE record_type = 'completed' AND record_key = ANY(%s)",
                (keys,),
            )
            return {str(row["record_key"]): dict(row.get("payload_json") or {}) for row in cursor.fetchall()}


def upsert_jobs(jobs: Iterable[Dict[str, Any]]) -> None:
    ensure_legacy_state_migrated()
    values = [_record_values(job["id"], "job", job) for job in jobs if isinstance(job, dict) and job.get("id")]
    if not values:
        return
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            _upsert_values(cursor, values)
            conn.commit()


def delete_jobs(record_keys: Iterable[str]) -> None:
    ensure_legacy_state_migrated()
    keys = [str(key) for key in record_keys if str(key or "")]
    if not keys:
        return
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM p115_upload_records WHERE record_type = 'job' AND record_key = ANY(%s)", (keys,))
            conn.commit()


def complete_job(job_id: str, completed_key: str, completed: Dict[str, Any]) -> None:
    ensure_legacy_state_migrated()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM p115_upload_records WHERE record_type = 'job' AND record_key = %s", (job_id,))
            _upsert_values(cursor, [_record_values(completed_key, "completed", completed)])
            conn.commit()


def get_status() -> Dict[str, Any]:
    ensure_legacy_state_migrated()
    counts = {"pending": 0, "uploading": 0, "failed": 0}
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT status, COUNT(*) AS total FROM p115_upload_records WHERE record_type = 'job' GROUP BY status")
            for row in cursor.fetchall():
                if row.get("status") in counts:
                    counts[row["status"]] = int(row.get("total") or 0)
            cursor.execute("SELECT COUNT(*) AS total FROM p115_upload_records WHERE record_type = 'completed'")
            completed = int((cursor.fetchone() or {}).get("total") or 0)
            cursor.execute(
                "SELECT payload_json FROM p115_upload_records WHERE record_type = 'job' ORDER BY updated_at DESC LIMIT 20"
            )
            recent = [dict(row.get("payload_json") or {}) for row in cursor.fetchall()]
    return {**counts, "completed": completed, "recent": recent}


def find_completed_by_pickcodes(pickcodes: Iterable[str]) -> List[Dict[str, Any]]:
    ensure_legacy_state_migrated()
    values = [str(value) for value in pickcodes if str(value or "")]
    if not values:
        return []
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT record_key, mapping_id, local_path, payload_json
                FROM p115_upload_records
                WHERE record_type = 'completed' AND pick_code = ANY(%s)
                """,
                (values,),
            )
            return [dict(row) for row in cursor.fetchall()]


def find_completed_by_local_paths(local_paths: Iterable[str]) -> List[Dict[str, Any]]:
    ensure_legacy_state_migrated()
    values = [os.path.abspath(path) for path in local_paths if str(path or "")]
    if not values:
        return []
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT record_key, mapping_id, local_path, pick_code, payload_json
                FROM p115_upload_records
                WHERE record_type = 'completed' AND local_path = ANY(%s)
                """,
                (values,),
            )
            return [dict(row) for row in cursor.fetchall()]


def delete_completed_and_jobs(completed_keys: Iterable[str], local_paths: Iterable[str]) -> None:
    ensure_legacy_state_migrated()
    keys = [str(key) for key in completed_keys if str(key or "")]
    normalized_paths = {os.path.normcase(os.path.abspath(path)) for path in local_paths if str(path or "")}
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            if keys:
                cursor.execute(
                    "DELETE FROM p115_upload_records WHERE record_type = 'completed' AND record_key = ANY(%s)",
                    (keys,),
                )
            if normalized_paths:
                cursor.execute("SELECT record_key, local_path FROM p115_upload_records WHERE record_type = 'job'")
                job_keys = [
                    str(row["record_key"])
                    for row in cursor.fetchall()
                    if row.get("local_path") and os.path.normcase(os.path.abspath(row["local_path"])) in normalized_paths
                ]
                if job_keys:
                    cursor.execute("DELETE FROM p115_upload_records WHERE record_key = ANY(%s)", (job_keys,))
            conn.commit()
