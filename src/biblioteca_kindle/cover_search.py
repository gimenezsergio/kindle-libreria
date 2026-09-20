import json, re, urllib.parse, urllib.request, uuid
from pathlib import Path
from .db import connect_database

class CoverSearchError(RuntimeError): pass

def clean_title(title: str) -> str:
    t = re.sub(r'-cdeKey$', '', title, flags=re.IGNORECASE)
    t = re.sub(r'\.(pdf|azw3|mobi|epub)$', '', t, flags=re.IGNORECASE)
    t = t.replace('_', ' ')
    t = re.sub(r'\s+by\s+.*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'trad[._\s]+.*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'Ed[._\s]+RAE.*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'Edicion.*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\(.*?\)', '', t)
    parts = re.split(r'\s*-\s*', t)
    if len(parts) >= 2 and len(parts[0].strip()) > 3:
        return parts[0].strip()
    return t.strip()

def search_covers(database, work_id, covers_dir, *, search_round=None):
    connection = connect_database(database)
    try:
        work = connection.execute("SELECT preferred_title FROM works WHERE id=?", (work_id,)).fetchone()
        if work is None: raise CoverSearchError("La obra no existe")
        current = connection.execute("SELECT COALESCE(MAX(search_round),0) FROM cover_candidates WHERE work_id=?", (work_id,)).fetchone()[0]
        round_number = search_round or current + 1
        if round_number > 3: raise CoverSearchError("Ya se realizaron tres rondas automáticas")
        raw_title = work["preferred_title"]
        cleaned = clean_title(raw_title)
        
        # Query Open Library using q parameter first, fallback to title parameter
        docs = []
        for param in ({"q": cleaned}, {"title": cleaned}):
            url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode({**param, "limit": 12, "page": round_number})
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "BibliotecaKindle/1.0"})
                with urllib.request.urlopen(req, timeout=15) as response:
                    res_docs = json.load(response).get("docs", [])
                    if res_docs:
                        docs = res_docs
                        break
            except Exception:
                continue

        existing = {row[0] for row in connection.execute("SELECT external_key FROM cover_candidates WHERE work_id=?", (work_id,))}
        added = 0; Path(covers_dir).mkdir(parents=True, exist_ok=True)
        for doc in docs:
            cover_id = doc.get("cover_i"); key = f"openlibrary:{cover_id}"
            if not cover_id or key in existing: continue
            filename = f"{work_id[:8]}-ol-{cover_id}.jpg"
            try:
                img_req = urllib.request.Request(f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg", headers={"User-Agent": "BibliotecaKindle/1.0"})
                with urllib.request.urlopen(img_req, timeout=15) as response:
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

