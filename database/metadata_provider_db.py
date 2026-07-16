import json
from datetime import date, datetime
from typing import Any, Dict, Optional

from psycopg2.extras import Json

from database.connection import get_db_connection


MEDIA_METADATA_SCHEMA_VERSION = 1


def _first_image(images: Dict[str, Any], key: str) -> Optional[str]:
    values = images.get(key) if isinstance(images, dict) else None
    for value in values or []:
        path = value.get("file_path") if isinstance(value, dict) else None
        if path:
            return str(path)
    return None


def _keywords(details: Dict[str, Any], media_type: str):
    container = details.get("keywords") or {}
    if isinstance(container, list):
        return container
    key = "results" if media_type == "tv" else "keywords"
    if isinstance(container, dict):
        return container.get(key) or []
    return []


def _directors(details: Dict[str, Any]):
    credits = details.get("credits") or {}
    return [
        {
            "id": person.get("id"),
            "name": person.get("name"),
            "profile_path": person.get("profile_path"),
        }
        for person in credits.get("crew") or []
        if person.get("job") in {"Director", "Series Director"} and person.get("id")
    ]


def _date_value(value):
    if not value:
        return None
    return str(value)[:10]


def _runtime(details: Dict[str, Any], media_type: str):
    value = details.get("runtime")
    if media_type == "tv" and not value:
        values = details.get("episode_run_time") or []
        value = values[0] if values else None
    try:
        value = int(value)
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def persist_initial_tmdb_metadata(
    details: Dict[str, Any],
    media_type: str,
    *,
    title: str = "",
    original_title: str = "",
    rating_label: str = "",
) -> bool:
    """Persist the pre-Emby TMDb snapshot without overwriting translated metadata."""
    if not isinstance(details, dict):
        return False
    tmdb_id = str(details.get("id") or "").strip()
    media_type = str(media_type or "").lower()
    if not tmdb_id.isdigit() or media_type not in {"movie", "tv"}:
        return False

    images = details.get("images") or {}
    poster_path = _first_image(images, "posters") or details.get("poster_path")
    backdrop_path = _first_image(images, "backdrops") or details.get("backdrop_path")
    logo_path = _first_image(images, "logos")
    thumb_path = _first_image(images, "backdrops") or backdrop_path
    item_type = "Series" if media_type == "tv" else "Movie"
    release_date = details.get("first_air_date") if media_type == "tv" else details.get("release_date")
    countries = details.get("origin_country") or [
        item.get("iso_3166_1")
        for item in details.get("production_countries") or []
        if item.get("iso_3166_1")
    ]
    row = {
        "tmdb_id": tmdb_id,
        "item_type": item_type,
        "title": title or details.get("name") or details.get("title"),
        "original_title": original_title or details.get("original_name") or details.get("original_title"),
        "original_language": details.get("original_language"),
        "overview": details.get("overview"),
        "tagline": details.get("tagline"),
        "release_date": _date_value(release_date),
        "release_year": int(str(release_date)[:4]) if release_date and str(release_date)[:4].isdigit() else None,
        "last_air_date": _date_value(details.get("last_air_date")),
        "poster_path": poster_path,
        "backdrop_path": backdrop_path,
        "logo_path": logo_path,
        "thumb_path": thumb_path,
        "homepage": details.get("homepage"),
        "runtime_minutes": _runtime(details, media_type),
        "rating": details.get("vote_average"),
        "custom_rating": rating_label if rating_label and rating_label != "未知" else None,
        "imdb_id": (details.get("external_ids") or {}).get("imdb_id"),
        "genres_json": details.get("genres") or [],
        "directors_json": _directors(details),
        "production_companies_json": details.get("production_companies") or [],
        "networks_json": details.get("networks") or [],
        "countries_json": countries,
        "keywords_json": _keywords(details, media_type),
        "total_episodes": details.get("number_of_episodes") or 0,
        "watchlist_tmdb_status": details.get("status"),
        "metadata_schema_version": MEDIA_METADATA_SCHEMA_VERSION,
    }

    columns = list(row)
    values = [
        Json(value, dumps=lambda obj: json.dumps(obj, ensure_ascii=False))
        if column.endswith("_json") else value
        for column, value in row.items()
    ]
    protected = {
        "title", "original_title", "original_language", "overview", "tagline",
        "release_date", "release_year", "last_air_date", "homepage", "runtime_minutes",
        "rating", "custom_rating", "imdb_id", "genres_json", "directors_json",
        "production_companies_json", "networks_json", "countries_json", "keywords_json",
        "total_episodes", "watchlist_tmdb_status",
    }
    updates = []
    for column in columns:
        if column in {"tmdb_id", "item_type"}:
            continue
        if column == "metadata_schema_version":
            updates.append(
                f"{column}=CASE WHEN media_metadata.actors_ready IS TRUE "
                f"THEN media_metadata.{column} ELSE EXCLUDED.{column} END"
            )
        elif column in protected:
            updates.append(
                f"{column}=CASE WHEN media_metadata.actors_ready IS TRUE "
                f"THEN COALESCE(media_metadata.{column}, EXCLUDED.{column}) ELSE EXCLUDED.{column} END"
            )
        else:
            updates.append(f"{column}=COALESCE(media_metadata.{column}, EXCLUDED.{column})")
    updates.extend([
        "metadata_ready=TRUE",
        "actors_ready=media_metadata.actors_ready",
        "last_updated_at=NOW()",
    ])

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO media_metadata ({', '.join(columns)}, metadata_ready, actors_ready)
                VALUES ({', '.join(['%s'] * len(columns))}, TRUE, FALSE)
                ON CONFLICT (tmdb_id, item_type) DO UPDATE SET {', '.join(updates)}
                """,
                values,
            )

            if media_type == "tv":
                for season in details.get("seasons") or []:
                    season_id = str(season.get("id") or "").strip()
                    season_number = season.get("season_number")
                    if not season_id or season_number is None:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO media_metadata (
                            tmdb_id, item_type, parent_series_tmdb_id, season_number,
                            title, overview, release_date, poster_path, total_episodes,
                            metadata_ready, actors_ready, metadata_schema_version
                        ) VALUES (%s, 'Season', %s, %s, %s, %s, %s, %s, %s, TRUE, FALSE, %s)
                        ON CONFLICT (tmdb_id, item_type) DO UPDATE SET
                            parent_series_tmdb_id=EXCLUDED.parent_series_tmdb_id,
                            season_number=EXCLUDED.season_number,
                            title=CASE WHEN media_metadata.actors_ready IS TRUE THEN media_metadata.title ELSE EXCLUDED.title END,
                            overview=CASE WHEN media_metadata.actors_ready IS TRUE THEN media_metadata.overview ELSE EXCLUDED.overview END,
                            release_date=CASE WHEN media_metadata.actors_ready IS TRUE THEN media_metadata.release_date ELSE EXCLUDED.release_date END,
                            poster_path=COALESCE(media_metadata.poster_path, EXCLUDED.poster_path),
                            total_episodes=CASE WHEN media_metadata.actors_ready IS TRUE THEN media_metadata.total_episodes ELSE EXCLUDED.total_episodes END,
                            metadata_ready=TRUE,
                            actors_ready=media_metadata.actors_ready,
                            metadata_schema_version=CASE WHEN media_metadata.actors_ready IS TRUE
                                THEN media_metadata.metadata_schema_version ELSE EXCLUDED.metadata_schema_version END,
                            last_updated_at=NOW()
                        """,
                        (
                            season_id, tmdb_id, season_number, season.get("name"),
                            season.get("overview"), _date_value(season.get("air_date")),
                            season.get("poster_path"), season.get("episode_count") or 0,
                            MEDIA_METADATA_SCHEMA_VERSION,
                        ),
                    )
        conn.commit()
    return True


def has_initial_tmdb_metadata(tmdb_id: str, media_type: str) -> bool:
    item_type = "Series" if str(media_type).lower() == "tv" else "Movie"
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 FROM media_metadata
                WHERE tmdb_id=%s AND item_type=%s AND metadata_ready IS TRUE
                  AND metadata_schema_version >= %s
                LIMIT 1
                """,
                (str(tmdb_id), item_type, MEDIA_METADATA_SCHEMA_VERSION),
            )
            return cursor.fetchone() is not None


def needs_metadata_backfill(tmdb_id: str, media_type: str) -> bool:
    item_type = "Series" if str(media_type).lower() == "tv" else "Movie"
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 FROM media_metadata
                WHERE tmdb_id=%s AND item_type=%s AND in_library IS TRUE
                  AND metadata_schema_version < %s
                LIMIT 1
                """,
                (str(tmdb_id), item_type, MEDIA_METADATA_SCHEMA_VERSION),
            )
            return cursor.fetchone() is not None


def _json_value(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _text_date(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value) if value else None


def load_emby_metadata(
    tmdb_id: str,
    root_media_type: str,
    requested_type: str,
    *,
    season_number: Optional[int] = None,
    episode_number: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Return one normalized metadata document for the Emby bridge provider."""
    requested_type = str(requested_type or "").strip().title()
    root_media_type = str(root_media_type or "").strip().lower()
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            if requested_type == "Movie" and root_media_type == "movie":
                cursor.execute(
                    "SELECT * FROM media_metadata WHERE tmdb_id=%s AND item_type='Movie' AND metadata_ready IS TRUE",
                    (str(tmdb_id),),
                )
            elif requested_type == "Season":
                cursor.execute(
                    """
                    SELECT * FROM media_metadata
                    WHERE parent_series_tmdb_id=%s AND item_type='Season' AND season_number=%s
                      AND metadata_ready IS TRUE
                    ORDER BY last_updated_at DESC NULLS LAST LIMIT 1
                    """,
                    (str(tmdb_id), season_number),
                )
            elif requested_type == "Episode":
                cursor.execute(
                    """
                    SELECT * FROM media_metadata
                    WHERE parent_series_tmdb_id=%s AND item_type='Episode'
                      AND season_number=%s AND episode_number=%s
                      AND metadata_ready IS TRUE
                    ORDER BY last_updated_at DESC NULLS LAST LIMIT 1
                    """,
                    (str(tmdb_id), season_number, episode_number),
                )
            else:
                requested_type = "Series"
                cursor.execute(
                    "SELECT * FROM media_metadata WHERE tmdb_id=%s AND item_type='Series' AND metadata_ready IS TRUE",
                    (str(tmdb_id),),
                )
            row = cursor.fetchone()

            if not row and requested_type == "Episode":
                cursor.execute(
                    "SELECT * FROM media_metadata WHERE tmdb_id=%s AND item_type='Series' AND metadata_ready IS TRUE",
                    (str(tmdb_id),),
                )
                parent = cursor.fetchone()
                if not parent:
                    return None
                row = dict(parent)
                row.update({
                    "tmdb_id": None,
                    "item_type": "Episode",
                    "title": None,
                    "overview": None,
                    "season_number": season_number,
                    "episode_number": episode_number,
                    "poster_path": None,
                    "backdrop_path": None,
                    "logo_path": None,
                    "thumb_path": None,
                    "actors_ready": False,
                })
            if not row:
                return None

            row = dict(row)
            people = []
            if row.get("actors_ready"):
                actor_links = _json_value(row.get("actors_json"), [])
                actor_ids = [link.get("tmdb_id") for link in actor_links if link.get("tmdb_id")]
                actor_map = {}
                if actor_ids:
                    cursor.execute(
                        """
                        SELECT tmdb_person_id, primary_name, profile_path
                        FROM person_metadata WHERE tmdb_person_id=ANY(%s)
                        """,
                        (actor_ids,),
                    )
                    actor_map = {item["tmdb_person_id"]: item for item in cursor.fetchall()}
                for link in actor_links:
                    actor = actor_map.get(link.get("tmdb_id"))
                    if actor:
                        people.append({
                            "name": actor.get("primary_name"),
                            "role": link.get("character"),
                            "type": "Actor",
                            "tmdb_id": str(actor.get("tmdb_person_id")),
                            "image_url": _tmdb_image_url(actor.get("profile_path"), "w500"),
                            "order": link.get("order", 999),
                        })
                for director in _json_value(row.get("directors_json"), []):
                    if director.get("name"):
                        people.append({
                            "name": director.get("name"),
                            "type": "Director",
                            "tmdb_id": str(director.get("id") or ""),
                            "image_url": _tmdb_image_url(director.get("profile_path"), "w500"),
                            "order": 1000,
                        })

    official_ratings = _json_value(row.get("official_rating_json"), {})
    rating = row.get("custom_rating") or official_ratings.get("US")
    companies = _json_value(row.get("production_companies_json"), [])
    networks = _json_value(row.get("networks_json"), [])
    studios = [item.get("name") for item in networks + companies if item.get("name")]
    return {
        "item_type": requested_type,
        "tmdb_id": str(row.get("tmdb_id") or ""),
        "series_tmdb_id": str(tmdb_id) if root_media_type == "tv" else "",
        "imdb_id": row.get("imdb_id"),
        "name": row.get("title"),
        "original_title": row.get("original_title"),
        "overview": row.get("overview"),
        "tagline": row.get("tagline"),
        "premiere_date": _text_date(row.get("release_date")),
        "end_date": _text_date(row.get("last_air_date")),
        "production_year": row.get("release_year"),
        "community_rating": row.get("rating"),
        "official_rating": rating,
        "runtime_minutes": row.get("runtime_minutes"),
        "genres": [item.get("name") if isinstance(item, dict) else item for item in _json_value(row.get("genres_json"), [])],
        "tags": [
            item.get("name") if isinstance(item, dict) else item
            for item in _json_value(row.get("tags_json") or row.get("keywords_json"), [])
        ],
        "studios": studios,
        "season_number": (
            row.get("season_number") if row.get("season_number") is not None else season_number
        ) if requested_type in {"Season", "Episode"} else None,
        "episode_number": (
            row.get("episode_number") if row.get("episode_number") is not None else episode_number
        ) if requested_type == "Episode" else None,
        "actors_ready": bool(row.get("actors_ready")),
        "people": sorted(people, key=lambda item: item.get("order", 999)),
        "images": {
            "primary": _tmdb_image_url(row.get("poster_path"), "original"),
            "backdrop": _tmdb_image_url(row.get("backdrop_path"), "original"),
            "logo": _tmdb_image_url(row.get("logo_path"), "original"),
            "thumb": _tmdb_image_url(row.get("thumb_path"), "original"),
        },
    }


def _tmdb_image_url(path, size):
    if not path:
        return None
    path = str(path)
    if path.startswith(("http://", "https://")):
        return path
    return f"https://image.tmdb.org/t/p/{size}/{path.lstrip('/')}"
