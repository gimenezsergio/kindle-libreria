from __future__ import annotations
import json, urllib.parse, urllib.request, uuid
from pathlib import Path
from .db import connect_database

class CoverSearchError(RuntimeError): pass

def search_covers(database, work_id, covers_dir, *, search_round=None):
    connection = connect_database(database)
    try:
        work = connection.execute("SELECT preferred_title FROM works WHERE id=?", (work_id,)).fetchone()
        if work is None: raise CoverSearchError("La obra no existe")
        current = connection.execute("SELECT COALESCE(MAX(search_round),0) FROM cover_candidates WHERE work_id=?", (work_id,)).fetchone()[0]
        round_number = search_round or current + 1
        if round_number > 3: raise CoverSearchError("Ya se realizaron tres rondas automáticas")
        title = work["preferred_title"].replace("_", " ")
        url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode({"title": title, "limit": 12, "page": round_number})
        with urllib.request.urlopen(url, timeout=15) as response: docs = json.load(response).get("docs", [])
        existing = {row[0] for row in connection.execute("SELECT external_key FROM cover_candidates WHERE work_id=?", (work_id,))}
        added = 0; Path(covers_dir).mkdir(parents=True, exist_ok=True)
        for doc in docs:
            cover_id = doc.get("cover_i"); key = f"openlibrary:{cover_id}"
            if not cover_id or key in existing: continue
            filename = f"{work_id[:8]}-ol-{cover_id}.jpg"
            try:
                with urllib.request.urlopen(f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg", timeout=15) as response:
                    data = response.read()
                if len(data) < 2000: continue
                Path(covers_dir, filename).write_bytes(data)
            except Exception: continue
            with connection:
                connection.execute("INSERT INTO cover_candidates(id,work_id,local_path,source_label,edition_label,confidence,display_order,status,external_key,search_round) VALUES(?,?,?,?,?,'medium',?,'available',?,?)", (str(uuid.uuid4()),work_id,filename,"Open Library",doc.get("first_publish_year"),added,key,round_number))
            added += 1
            if added == 3: break
        if not added: raise CoverSearchError("No se encontraron portadas nuevas")
        return added
    finally: connection.close()
