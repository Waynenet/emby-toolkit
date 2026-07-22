import json

from psycopg2.extras import Json

from database.connection import get_db_connection


def _key(item_type, tmdb_id, season_number=None, episode_number=None):
    return (
        str(item_type or "").strip().title(),
        str(tmdb_id or "").strip(),
        int(season_number) if season_number is not None else -1,
        int(episode_number) if episode_number is not None else -1,
    )


def get_image_policy(item_type, tmdb_id, season_number=None, episode_number=None):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT policy_json, images_json
                FROM media_image_policy_cache
                WHERE item_type=%s AND tmdb_id=%s
                  AND season_number=%s AND episode_number=%s
                """,
                _key(item_type, tmdb_id, season_number, episode_number),
            )
            row = cursor.fetchone()
    return dict(row) if row else None


def replace_image_policy(
    item_type,
    tmdb_id,
    policy,
    images,
    season_number=None,
    episode_number=None,
):
    key = _key(item_type, tmdb_id, season_number, episode_number)
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT images_json FROM media_image_policy_cache
                WHERE item_type=%s AND tmdb_id=%s
                  AND season_number=%s AND episode_number=%s
                FOR UPDATE
                """,
                key,
            )
            row = cursor.fetchone()
            previous = list((row or {}).get("images_json") or [])
            cursor.execute(
                """
                INSERT INTO media_image_policy_cache (
                    item_type, tmdb_id, season_number, episode_number,
                    policy_json, images_json, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (item_type, tmdb_id, season_number, episode_number)
                DO UPDATE SET
                    policy_json=EXCLUDED.policy_json,
                    images_json=EXCLUDED.images_json,
                    updated_at=NOW()
                """,
                (*key, Json(policy), Json(images)),
            )
        conn.commit()
    return previous


def invalidate_image_policy(item_type, tmdb_id, season_number=None, episode_number=None):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE media_image_policy_cache
                SET policy_json='[]'::jsonb, updated_at=NOW()
                WHERE item_type=%s AND tmdb_id=%s
                  AND season_number=%s AND episode_number=%s
                """,
                _key(item_type, tmdb_id, season_number, episode_number),
            )
            updated = cursor.rowcount
        conn.commit()
    return updated


def source_is_referenced(source_url):
    value = json.dumps([{"source_url": str(source_url or "").strip()}])
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM media_image_policy_cache
                    WHERE images_json @> %s::jsonb
                ) AS used
                """,
                (value,),
            )
            row = cursor.fetchone()
    return bool((row or {}).get("used"))
