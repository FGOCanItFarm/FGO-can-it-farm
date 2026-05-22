import requests
import json
import os
import time
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(filename='script.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

# Load environment variables from .env file
load_dotenv()

# Adjust logging level for pymongo to suppress debug messages
logging.getLogger('pymongo').setLevel(logging.WARNING)

# MongoDB connection
mongo_uri = os.getenv('MONGO_URI')
if not mongo_uri:
    raise ValueError("No MONGO_URI environment variable set")

client = MongoClient(mongo_uri)
db = client['FGOCanItFarmDatabase']
servants_collection = db['servants']
quests_collection = db['quests']
mysticcode_collection = db['mysticcodes']
metadata_collection = db['metadata']


def fetch_with_backoff(url, retries=3):
    """Fetch a URL with exponential backoff. Returns parsed JSON or None."""
    for attempt in range(retries):
        try:
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                try:
                    return response.json()
                except json.JSONDecodeError as e:
                    logging.error(f"JSONDecodeError for {url}: {e}")
                    return None
            else:
                logging.error(f"HTTP {response.status_code} for {url}")
        except requests.RequestException as e:
            logging.error(f"RequestException for {url}: {e}")
        if attempt < retries - 1:
            time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s
    return None


# ---------------------------------------------------------------------------
# Servants
# ---------------------------------------------------------------------------

def retrieve_servants(progress_callback=None):
    """Auto-discover all servants via basic_servant.json, hash-diff update."""
    basic_url = 'https://api.atlasacademy.io/export/JP/basic_servant.json'
    basic_list = fetch_with_backoff(basic_url)
    if basic_list is None:
        logging.error("Failed to fetch basic_servant.json")
        return 0, 0

    servants_checked = 0
    servants_updated = 0

    for entry in basic_list:
        collection_no = entry.get('collectionNo')
        aa_hash = entry.get('hash', '')
        if not collection_no:
            continue

        servants_checked += 1

        # Check stored hash
        existing = servants_collection.find_one(
            {'collectionNo': collection_no},
            {'_aa_data_hash': 1}
        )
        stored_hash = existing.get('_aa_data_hash', '') if existing else None

        if stored_hash == aa_hash and existing is not None:
            logging.info(f"Servant {collection_no}: hash unchanged, skipping")
            continue

        # Fetch full nice data
        url = f'https://api.atlasacademy.io/nice/JP/servant/{collection_no}?lore=true&expand=true&lang=en'
        data = fetch_with_backoff(url)
        if data is None:
            logging.error(f"Failed to fetch servant {collection_no}")
            time.sleep(0.5)
            continue

        data['_aa_data_hash'] = aa_hash
        servants_collection.update_one(
            {'collectionNo': collection_no},
            {'$set': data},
            upsert=True
        )
        servants_updated += 1
        logging.info(f"Upserted servant {collection_no} (hash changed or new)")

        if progress_callback:
            progress_callback('servant', collection_no, servants_checked, servants_updated)

        time.sleep(0.5)

    return servants_checked, servants_updated


# ---------------------------------------------------------------------------
# Quests
# ---------------------------------------------------------------------------

def upsert_quest(data):
    quest_id = data.get('id')
    stages = data.get('stages', [])
    if quest_id and stages and 'enemies' in stages[0] and len(stages[0]['enemies']) > 0:
        quests_collection.update_one(
            {'id': quest_id},
            {'$set': data},
            upsert=True
        )
        logging.info(f"Upserted quest {quest_id}")
    else:
        logging.error(f"Quest data missing id or empty enemies for quest ID: {quest_id}")


def retrieve_quests():
    """Auto-discover wars via basic_war.json, filter and upsert matching quests."""
    basic_war_url = 'https://api.atlasacademy.io/export/JP/basic_war.json'
    basic_wars = fetch_with_backoff(basic_war_url)
    if basic_wars is None:
        logging.error("Failed to fetch basic_war.json")
        return 0

    KEEP_TYPES = {'eventQuest', 'permanent'}
    war_ids = [
        w['id'] for w in basic_wars
        if w.get('type') in KEEP_TYPES
    ]
    logging.info(f"Discovered {len(war_ids)} wars to process")

    all_quest_ids = []
    for war_id in war_ids:
        url = f'https://api.atlasacademy.io/nice/JP/war/{war_id}?lang=en'
        data = fetch_with_backoff(url)
        if data is None:
            logging.error(f"Failed to fetch war {war_id}")
            time.sleep(0.3)
            continue
        for spot in data.get('spots', []):
            for quest in spot.get('quests', []):
                recommend_lv = quest.get('recommendLv', '')
                consume = quest.get('consume', 0)
                after_clear = quest.get('afterClear', '')
                if (
                    recommend_lv in ['90', '90+', '90++', '90★', '90★★']
                    and consume == 40
                    and after_clear == 'repeatLast'
                ):
                    all_quest_ids.append(quest.get('id'))
        time.sleep(0.3)

    logging.info(f"Found {len(all_quest_ids)} matching quests")

    quests_updated = 0
    for quest_id in all_quest_ids:
        url = f'https://api.atlasacademy.io/nice/JP/quest/{quest_id}/1?lang=en'
        data = fetch_with_backoff(url)
        if data is None:
            logging.error(f"Failed to fetch quest {quest_id}")
            time.sleep(0.3)
            continue
        upsert_quest(data)
        quests_updated += 1
        time.sleep(0.3)

    return quests_updated


# ---------------------------------------------------------------------------
# Mystic Codes
# ---------------------------------------------------------------------------

def retrieve_mystic_codes():
    """Auto-discover all mystic codes via basic_mystic_code.json, hash-diff update."""
    basic_url = 'https://api.atlasacademy.io/export/JP/basic_mystic_code.json'
    basic_list = fetch_with_backoff(basic_url)
    if basic_list is None:
        logging.error("Failed to fetch basic_mystic_code.json")
        return 0

    mc_updated = 0
    for entry in basic_list:
        mc_id = entry.get('id')
        aa_hash = entry.get('hash', '')
        if not mc_id:
            continue

        existing = mysticcode_collection.find_one(
            {'id': mc_id},
            {'_aa_data_hash': 1}
        )
        stored_hash = existing.get('_aa_data_hash', '') if existing else None

        if stored_hash == aa_hash and existing is not None:
            logging.info(f"Mystic code {mc_id}: hash unchanged, skipping")
            continue

        url = f'https://api.atlasacademy.io/nice/JP/MC/{mc_id}?lang=en'
        data = fetch_with_backoff(url)
        if data is None:
            logging.error(f"Failed to fetch mystic code {mc_id}")
            time.sleep(0.3)
            continue

        data['_aa_data_hash'] = aa_hash
        mysticcode_collection.update_one(
            {'id': mc_id},
            {'$set': data},
            upsert=True
        )
        mc_updated += 1
        logging.info(f"Upserted mystic code {mc_id} (hash changed or new)")
        time.sleep(0.3)

    return mc_updated


# ---------------------------------------------------------------------------
# Version / metadata
# ---------------------------------------------------------------------------

def update_jp_hash():
    """Fetch JP game hash from /info and store in metadata collection."""
    info = fetch_with_backoff('https://api.atlasacademy.io/info')
    if info is None:
        logging.error("Failed to fetch /info")
        return ''
    jp_hash = info.get('JP', {}).get('hash', '')
    metadata_collection.update_one(
        {'_id': 'aa_version'},
        {'$set': {'jp_hash': jp_hash, 'updated_at': datetime.now(timezone.utc)}},
        upsert=True
    )
    logging.info(f"Stored JP hash: {jp_hash}")
    return jp_hash


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_update(progress_callback=None):
    """
    Run the full update flow.

    Returns a summary dict:
        {
            "servants_checked": int,
            "servants_updated": int,
            "quests_updated": int,
            "mystic_codes_updated": int,
            "new_jp_hash": str,
            "duration_seconds": float,
        }
    """
    start = time.monotonic()
    logging.info("=== Starting update run ===")

    new_jp_hash = update_jp_hash()
    servants_checked, servants_updated = retrieve_servants(progress_callback)
    quests_updated = retrieve_quests()
    mc_updated = retrieve_mystic_codes()

    duration = time.monotonic() - start
    summary = {
        'servants_checked': servants_checked,
        'servants_updated': servants_updated,
        'quests_updated': quests_updated,
        'mystic_codes_updated': mc_updated,
        'new_jp_hash': new_jp_hash,
        'duration_seconds': round(duration, 2),
    }
    logging.info(f"Update complete: {summary}")
    return summary


if __name__ == "__main__":
    result = run_update()
    print(result)
