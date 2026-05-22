import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import requests
from psycopg2.extras import Json
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from connectDB import get_cursor  # noqa: E402

load_dotenv()

logging.basicConfig(
    filename='script.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s',
)
sys.stdout.reconfigure(encoding='utf-8')


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MASH_COLLECTION_NO       = 2
AOKO_COLLECTION_NO       = 413
MELUSINE_FORM_SKILL_ID   = 888550

NP_DAMAGE_FUNC_TYPES = {
    'damageNp',
    'damageNpPierce',
    'damageNpIndividual',
    'damageNpStateIndividualFix',
    'damageNpIndividualSum',
}

KEEP_WAR_TYPES  = {'eventQuest', 'permanent'}
RECOMMEND_LVS   = {'90', '90+', '90++', '90★', '90★★'}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def fetch_with_backoff(url, retries=3):
    """GET url with exponential backoff. Returns parsed JSON or None."""
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                try:
                    return response.json()
                except json.JSONDecodeError as exc:
                    logging.error('JSONDecodeError for %s: %s', url, exc)
                    return None
            logging.error('HTTP %s for %s', response.status_code, url)
        except requests.RequestException as exc:
            logging.error('RequestException for %s: %s', url, exc)
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    return None


# ---------------------------------------------------------------------------
# Guardrail Parser Pipeline
# ---------------------------------------------------------------------------

def _extract_np_card(data):
    nps = sorted(data.get('noblePhantasms', []), key=lambda x: x.get('id', 0))
    return nps[-1].get('card') if nps else None


def _extract_attack_type(data):
    nps = sorted(data.get('noblePhantasms', []), key=lambda x: x.get('id', 0))
    if not nps:
        return 'support'
    for func in nps[-1].get('functions', []):
        if func.get('funcType') in NP_DAMAGE_FUNC_TYPES:
            target = func.get('funcTargetType', '')
            if target == 'enemy':
                return 'attackEnemyOne'
            if target in ('enemyAll', 'enemyFull'):
                return 'attackEnemyAll'
    return 'support'


def _extract_face_url(data):
    """Return the highest-ascension face image URL from extraAssets."""
    ascension = (
        data.get('extraAssets', {})
            .get('faces', {})
            .get('ascension', {})
    )
    if not ascension:
        return None
    for key in ('4', '3', '2', '1'):
        if key in ascension:
            return ascension[key]
    vals = list(ascension.values())
    return vals[0] if vals else None


def run_guardrail_pipeline(data):
    """
    5-step pre-parse of raw Atlas Academy servant JSON.
    Returns a dict of structured column values for public.servants.
    """
    collection_no = data.get('collectionNo')
    nps = sorted(data.get('noblePhantasms', []), key=lambda x: x.get('id', 0))
    np_cards = sorted({np_.get('card') for np_ in nps if np_.get('card')})
    variable = len(np_cards) > 1

    result = {
        'np_card':          None if variable else _extract_np_card(data),
        'np_card_variable': variable,
        'np_card_options':  np_cards if variable else None,
        'attack_type':      _extract_attack_type(data),
        'is_enemy_only':    data.get('isEnemy', False),
        'form_transition':  None,
        'parser_flags':     {},
        'face_url':         _extract_face_url(data),
    }

    # Step 1 — transformServant in skill functions (Jekyll-style one-way transform)
    transform_skills = [
        s for s in data.get('skills', [])
        if any(f.get('funcType') == 'transformServant' for f in s.get('functions', []))
    ]
    if len(transform_skills) == 1:
        result['form_transition'] = 'irreversible'
        result['parser_flags']['has_transform_servant'] = True
    elif len(transform_skills) > 1:
        result['form_transition'] = 'reversible'
        result['parser_flags']['has_transform_servant'] = True

    # Step 2 — costumeAdd: Mash hard-coded to Ortinax (most upgraded form)
    if collection_no == MASH_COLLECTION_NO:
        result['parser_flags']['mash_ortinax'] = True

    # Step 3 — formIdx: Melusine's form-change skill ID → override to irreversible
    for skill in data.get('skills', []):
        if skill.get('id') == MELUSINE_FORM_SKILL_ID:
            result['form_transition'] = 'irreversible'
            result['parser_flags']['melusine_form_skill'] = True

    # Step 4 — condLimitCount: record ascension-gated skill IDs for the sim engine
    gated = [s.get('id') for s in data.get('skills', []) if s.get('condLimitCount', 0) > 0]
    if gated:
        result['parser_flags']['ascension_gated_skill_ids'] = gated

    # Step 5 — modal NP card choice (Space Ishtar, Emiya etc.)
    if variable:
        result['parser_flags']['requires_choice'] = True

    # Aoko: BattleEngine needs to know to apply post-NP transform
    if collection_no == AOKO_COLLECTION_NO:
        result['parser_flags']['is_aoko'] = True

    return result


# ---------------------------------------------------------------------------
# Servants
# ---------------------------------------------------------------------------

_SERVANT_UPSERT_SQL = """
    INSERT INTO public.servants (
        collection_no, name, class_name, rarity,
        np_card, np_card_variable, np_card_options, attack_type,
        is_enemy_only, form_transition, parser_flags,
        face_url, aa_data_hash, data, updated_at
    ) VALUES (
        %(collection_no)s, %(name)s, %(class_name)s, %(rarity)s,
        %(np_card)s, %(np_card_variable)s, %(np_card_options)s, %(attack_type)s,
        %(is_enemy_only)s, %(form_transition)s, %(parser_flags)s,
        %(face_url)s, %(aa_data_hash)s, %(data)s, now()
    )
    ON CONFLICT (collection_no) DO UPDATE SET
        name             = EXCLUDED.name,
        class_name       = EXCLUDED.class_name,
        rarity           = EXCLUDED.rarity,
        np_card          = EXCLUDED.np_card,
        np_card_variable = EXCLUDED.np_card_variable,
        np_card_options  = EXCLUDED.np_card_options,
        attack_type      = EXCLUDED.attack_type,
        is_enemy_only    = EXCLUDED.is_enemy_only,
        form_transition  = EXCLUDED.form_transition,
        parser_flags     = EXCLUDED.parser_flags,
        face_url         = EXCLUDED.face_url,
        aa_data_hash     = EXCLUDED.aa_data_hash,
        data             = EXCLUDED.data,
        updated_at       = now()
"""


def _upsert_servant(data, aa_hash):
    parsed = run_guardrail_pipeline(data)
    params = {
        'collection_no':    data.get('collectionNo'),
        'name':             data.get('name', ''),
        'class_name':       data.get('className', ''),
        'rarity':           data.get('rarity', 0),
        'np_card':          parsed['np_card'],
        'np_card_variable': parsed['np_card_variable'],
        'np_card_options':  parsed['np_card_options'],
        'attack_type':      parsed['attack_type'],
        'is_enemy_only':    parsed['is_enemy_only'],
        'form_transition':  parsed['form_transition'],
        'parser_flags':     Json(parsed['parser_flags']),
        'face_url':         parsed['face_url'],
        'aa_data_hash':     aa_hash,
        'data':             Json(data),
    }
    with get_cursor() as cur:
        cur.execute(_SERVANT_UPSERT_SQL, params)


def retrieve_servants(progress_callback=None):
    """Auto-discover servants via basic_servant.json, hash-diff upsert."""
    basic_list = fetch_with_backoff('https://api.atlasacademy.io/export/JP/basic_servant.json')
    if basic_list is None:
        logging.error('Failed to fetch basic_servant.json')
        return 0, 0

    servants_checked = 0
    servants_updated = 0

    for entry in basic_list:
        collection_no = entry.get('collectionNo')
        aa_hash = entry.get('hash', '')
        if not collection_no:
            continue

        servants_checked += 1

        with get_cursor() as cur:
            cur.execute(
                'SELECT aa_data_hash FROM public.servants WHERE collection_no = %s',
                (collection_no,),
            )
            row = cur.fetchone()
        if row and row['aa_data_hash'] == aa_hash:
            logging.info('Servant %s: hash unchanged, skipping', collection_no)
            continue

        url = (
            f'https://api.atlasacademy.io/nice/JP/servant/{collection_no}'
            '?lore=true&expand=true&lang=en'
        )
        data = fetch_with_backoff(url)
        if data is None:
            logging.error('Failed to fetch servant %s', collection_no)
            time.sleep(0.5)
            continue

        _upsert_servant(data, aa_hash)
        servants_updated += 1
        logging.info('Upserted servant %s', collection_no)

        if progress_callback:
            progress_callback('servant', collection_no, servants_checked, servants_updated)

        time.sleep(0.5)

    return servants_checked, servants_updated


# ---------------------------------------------------------------------------
# Quests
# ---------------------------------------------------------------------------

_QUEST_UPSERT_SQL = """
    INSERT INTO public.quests (
        id, name, war_id, war_name, recommend_lv, consume, after_clear,
        opened_at, data, updated_at
    ) VALUES (
        %(id)s, %(name)s, %(war_id)s, %(war_name)s,
        %(recommend_lv)s, %(consume)s, %(after_clear)s,
        %(opened_at)s, %(data)s, now()
    )
    ON CONFLICT (id) DO UPDATE SET
        name         = EXCLUDED.name,
        war_id       = EXCLUDED.war_id,
        war_name     = EXCLUDED.war_name,
        recommend_lv = EXCLUDED.recommend_lv,
        consume      = EXCLUDED.consume,
        after_clear  = EXCLUDED.after_clear,
        opened_at    = EXCLUDED.opened_at,
        data         = EXCLUDED.data,
        updated_at   = now()
"""


def _upsert_quest(data, war_id, war_name):
    quest_id = data.get('id')
    stages   = data.get('stages', [])
    if not (quest_id and stages and stages[0].get('enemies')):
        logging.error('Quest %s: missing id or empty enemies', quest_id)
        return
    params = {
        'id':           quest_id,
        'name':         data.get('name', ''),
        'war_id':       war_id,
        'war_name':     war_name,
        'recommend_lv': data.get('recommendLv', ''),
        'consume':      data.get('consume', 0),
        'after_clear':  data.get('afterClear', ''),
        'opened_at':    data.get('openedAt'),
        'data':         Json(data),
    }
    with get_cursor() as cur:
        cur.execute(_QUEST_UPSERT_SQL, params)
    logging.info('Upserted quest %s', quest_id)


KEEP_WAR_TYPES  = {'eventQuest', 'permanent'}
RECOMMEND_LVS   = {'90', '90+', '90++', '90★', '90★★'}


def retrieve_quests():
    """Auto-discover qualifying quests via basic_war.json."""
    basic_wars = fetch_with_backoff('https://api.atlasacademy.io/export/JP/basic_war.json')
    if basic_wars is None:
        logging.error('Failed to fetch basic_war.json')
        return 0

    war_ids = [w['id'] for w in basic_wars if w.get('type') in KEEP_WAR_TYPES]
    logging.info('Processing %d wars', len(war_ids))

    queue = []  # (quest_id, war_id, war_name)
    for war_id in war_ids:
        war_data = fetch_with_backoff(f'https://api.atlasacademy.io/nice/JP/war/{war_id}?lang=en')
        if war_data is None:
            logging.error('Failed to fetch war %s', war_id)
            time.sleep(0.3)
            continue
        war_name = war_data.get('longName') or war_data.get('name', '')
        for spot in war_data.get('spots', []):
            for quest in spot.get('quests', []):
                if (
                    quest.get('recommendLv') in RECOMMEND_LVS
                    and quest.get('consume') == 40
                    and quest.get('afterClear') == 'repeatLast'
                ):
                    queue.append((quest['id'], war_id, war_name))
        time.sleep(0.3)

    logging.info('Found %d qualifying quests', len(queue))

    quests_updated = 0
    for quest_id, war_id, war_name in queue:
        data = fetch_with_backoff(
            f'https://api.atlasacademy.io/nice/JP/quest/{quest_id}/1?lang=en'
        )
        if data is None:
            logging.error('Failed to fetch quest %s', quest_id)
            time.sleep(0.3)
            continue
        _upsert_quest(data, war_id, war_name)
        quests_updated += 1
        time.sleep(0.3)

    return quests_updated


# ---------------------------------------------------------------------------
# Mystic Codes
# ---------------------------------------------------------------------------

_MC_UPSERT_SQL = """
    INSERT INTO public.mystic_codes (id, name, aa_data_hash, data, updated_at)
    VALUES (%(id)s, %(name)s, %(aa_data_hash)s, %(data)s, now())
    ON CONFLICT (id) DO UPDATE SET
        name         = EXCLUDED.name,
        aa_data_hash = EXCLUDED.aa_data_hash,
        data         = EXCLUDED.data,
        updated_at   = now()
"""


def retrieve_mystic_codes():
    """Auto-discover mystic codes via basic_mystic_code.json, hash-diff upsert."""
    basic_list = fetch_with_backoff(
        'https://api.atlasacademy.io/export/JP/basic_mystic_code.json'
    )
    if basic_list is None:
        logging.error('Failed to fetch basic_mystic_code.json')
        return 0

    mc_updated = 0
    for entry in basic_list:
        mc_id   = entry.get('id')
        aa_hash = entry.get('hash', '')
        if not mc_id:
            continue

        with get_cursor() as cur:
            cur.execute(
                'SELECT aa_data_hash FROM public.mystic_codes WHERE id = %s',
                (mc_id,),
            )
            row = cur.fetchone()
        if row and row['aa_data_hash'] == aa_hash:
            logging.info('Mystic code %s: hash unchanged, skipping', mc_id)
            continue

        data = fetch_with_backoff(f'https://api.atlasacademy.io/nice/JP/MC/{mc_id}?lang=en')
        if data is None:
            logging.error('Failed to fetch mystic code %s', mc_id)
            time.sleep(0.3)
            continue

        with get_cursor() as cur:
            cur.execute(_MC_UPSERT_SQL, {
                'id':           mc_id,
                'name':         data.get('name', ''),
                'aa_data_hash': aa_hash,
                'data':         Json(data),
            })
        mc_updated += 1
        logging.info('Upserted mystic code %s', mc_id)
        time.sleep(0.3)

    return mc_updated


# ---------------------------------------------------------------------------
# Metadata / version
# ---------------------------------------------------------------------------

def update_jp_hash():
    info = fetch_with_backoff('https://api.atlasacademy.io/info')
    if info is None:
        logging.error('Failed to fetch /info')
        return ''
    jp_hash = info.get('JP', {}).get('hash', '')
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.metadata (key, value, updated_at)
            VALUES ('aa_version', %s, now())
            ON CONFLICT (key) DO UPDATE SET
                value      = EXCLUDED.value,
                updated_at = now()
            """,
            (Json({'jp_hash': jp_hash, 'updated_at': datetime.now(timezone.utc).isoformat()}),),
        )
    logging.info('Stored JP hash: %s', jp_hash)
    return jp_hash


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_update(progress_callback=None):
    """
    Full update flow. Returns summary dict:
        servants_checked, servants_updated, quests_updated,
        mystic_codes_updated, new_jp_hash, duration_seconds
    """
    start = time.monotonic()
    logging.info('=== Starting update run ===')

    new_jp_hash                        = update_jp_hash()
    servants_checked, servants_updated = retrieve_servants(progress_callback)
    quests_updated                     = retrieve_quests()
    mc_updated                         = retrieve_mystic_codes()

    duration = time.monotonic() - start
    summary = {
        'servants_checked':    servants_checked,
        'servants_updated':    servants_updated,
        'quests_updated':      quests_updated,
        'mystic_codes_updated': mc_updated,
        'new_jp_hash':         new_jp_hash,
        'duration_seconds':    round(duration, 2),
    }
    logging.info('Update complete: %s', summary)
    return summary


if __name__ == '__main__':
    result = run_update()
    print(result)
