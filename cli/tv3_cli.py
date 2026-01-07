#!/usr/bin/env python3
import argparse
import requests
import csv
import os
import re
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from tqdm import tqdm

# -----------------------------
# CONFIG / LOGGING
# -----------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("TV3")

# -----------------------------
# UTILIDADES
# -----------------------------
def ensure_folder(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def safe_filename(name):
    return re.sub(r'[\\/:"*?<>|]+', '-', name)

def make_session(retries=5, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504)):
    s = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(['GET','POST'])
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; TV3enmassa/1.0)'})
    return s

SESSION = make_session()

def fetch_json(url, params=None, timeout=15):
    r = SESSION.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

# -----------------------------
# API helpers (mejorados)
# -----------------------------
def obtener_program_id(nombonic):
    data = fetch_json("https://api.3cat.cat/programestv")
    items = []
    try:
        lletra = data["resposta"]["items"]["lletra"]
        if isinstance(lletra, dict) and "item" in lletra:
            it = lletra["item"]
            items = it if isinstance(it, list) else [it]
        elif isinstance(lletra, list):
            for l in lletra:
                if "item" in l:
                    it = l["item"]
                    items += it if isinstance(it, list) else [it]
    except Exception:
        pass

    for p in items:
        if isinstance(p, dict) and p.get("nombonic") == nombonic:
            return p.get("id")
    raise RuntimeError(f"No se encontró programa con nombonic={nombonic}")

def obtener_program_name(nombonic):
    data = fetch_json("https://api.3cat.cat/programestv")
    items = []
    try:
        lletra = data["resposta"]["items"]["lletra"]
        if isinstance(lletra, dict) and "item" in lletra:
            it = lletra["item"]
            items = it if isinstance(it, list) else [it]
        elif isinstance(lletra, list):
            for l in lletra:
                if "item" in l:
                    it = l["item"]
                    items += it if isinstance(it, list) else [it]
    except Exception:
        pass

    for p in items:
        if isinstance(p, dict) and p.get("nombonic") == nombonic:
            return p.get("titol")
    raise RuntimeError(f"No se encontró programa con nombonic={nombonic}")

from concurrent.futures import ThreadPoolExecutor, as_completed

def obtener_ids_capitulos(programatv_id, items_pagina=1000, orden="capitol", workers=10):
    """
    Obtiene TODOS los IDs de los capítulos de un programa, paginando en paralelo.
    """
    # 1) Primero obtener cuántas páginas hay
    params = {
        "items_pagina": items_pagina,
        "ordre": orden,
        "programatv_id": programatv_id,
        "pagina": 1
    }
    data = fetch_json("https://api.3cat.cat/videos", params=params)
    pags = data["resposta"]["paginacio"]["total_pagines"]

    print(f"📄 Total páginas: {pags}")

    # 2) Función para obtener IDs de una sola página
    def fetch_page(page):
        try:
            params = {
                "items_pagina": items_pagina,
                "ordre": orden,
                "programatv_id": programatv_id,
                "pagina": page
            }
            d = fetch_json("https://api.3cat.cat/videos", params=params)

            item_list = d["resposta"]["items"]["item"]
            if isinstance(item_list, dict):
                item_list = [item_list]

            ids_local = [i["id"] for i in item_list if "id" in i]
            return ids_local

        except Exception as e:
            print(f"⚠️ Error en página {page}: {e}")
            return []  # no rompe el proceso

    # 3) Ejecutar en paralelo todas las páginas
    all_ids = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_page, page): page for page in range(1, pags+1)}

        for future in as_completed(futures):
            page = futures[future]
            try:
                ids_pag = future.result()
                print(f"✔ Página {page}: {len(ids_pag)} capítulos")
                all_ids.extend(ids_pag)
            except Exception as e:
                print(f"❌ Error inesperado en página {page}: {e}")

    # 4) Eliminar duplicados, ordenar
    all_ids = sorted(set(all_ids), key=int)

    print(f"\n📌 Total capítulos obtenidos: {len(all_ids)}")
    return all_ids


# -----------------------------
# Extraer MP4 + VTT de un id de capítulo (robusto)
# -----------------------------
def api_extract_media_urls(id_cap):
    url = "https://api.3cat.cat/pvideo/media.jsp"
    params = {"media": "video", "version": "0s", "idint": id_cap}
    try:
        r = SESSION.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        programa = data.get("informacio", {}).get("programa", "UnknownProgram")
        title = data.get("informacio", {}).get("titol", f"capitol-{id_cap}")

        # MP4: puede ser lista o dict
        files = data.get("media", {}).get("url", [])
        if isinstance(files, dict):
            files = [files]
        if not isinstance(files, list):
            files = []

        mp4s = []
        for entry in files:
            if not isinstance(entry, dict):
                continue
            mp4 = entry.get("file")
            label = entry.get("label") or entry.get("quality") or ""
            if mp4 and mp4.lower().endswith(".mp4"):
                mp4s.append((label or "mp4", mp4))

        # VTT:
        vfiles = data.get("subtitols", []) or []
        if isinstance(vfiles, dict):
            vfiles = [vfiles]
        if not isinstance(vfiles, list):
            vfiles = []

        subtitols = []
        for entry in vfiles:
            if not isinstance(entry, dict):
                continue
            vtt = entry.get("url")
            label = entry.get("text") or entry.get("lang") or ""
            if vtt and vtt.lower().endswith(".vtt"):
                subtitols.append((label or "vtt", vtt))

        return {"id": id_cap, "programa": programa, "title": title, "mp4s": mp4s, "vtts": subtitols}
    except Exception as e:
        logger.error("Error obtener datos id=%s : %s", id_cap, e)
        return None

# -----------------------------
# CSV build (paralelo) con reintentos y registro de fallos
# -----------------------------
def build_links_csv(cids, output_csv="links-fitxers.csv", workers=8, retry_failed=2):
    logger.info("Generando CSV en paralelo (workers=%s)...", workers)
    rows = []
    failed = []

    def worker(cid):
        attempts = 0
        while attempts <= retry_failed:
            attempts += 1
            res = api_extract_media_urls(cid)
            if res:
                break
            logger.warning("Reintentando extracción id=%s (intento %s)...", cid, attempts)
            time.sleep(1 * attempts)
        if not res:
            failed.append(cid)
            return []
        programa = res["programa"]
        title = res["title"]
        safe_programa = safe_filename(programa)
        safe_title = safe_filename(title)
        safe_name = safe_filename(f"{programa} - {title}")
        local_rows = []
        for label, mp4 in res["mp4s"]:
            file_name = mp4.split("/")[-1]
            local_rows.append([res["id"], safe_programa, safe_title, safe_name, label, mp4, file_name])
        for label, vtt in res["vtts"]:
            file_name = vtt.split("/")[-1]
            local_rows.append([res["id"], safe_programa, safe_title, safe_name, label, vtt, file_name])
        return local_rows

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(worker, cid): cid for cid in cids}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Extrayendo", unit="cap"):
            cid = futures[future]
            try:
                chapter_rows = future.result()
                rows.extend(chapter_rows)
            except Exception as e:
                logger.error("Error procesando capítulo %s: %s", cid, e)
                failed.append(cid)

    # Escribir CSV (ordenamos por id para tener consistencia)
    rows_sorted = sorted(rows, key=lambda r: int(r[0]) if str(r[0]).isdigit() else 0)
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["ID", "Program", "Title", "Name", "Quality", "Link", "File Name"])
        writer.writerows(rows_sorted)

    if failed:
        with open("errors_ids.txt", "w", encoding="utf-8") as ef:
            for fid in failed:
                ef.write(str(fid) + "\n")
        logger.warning("Algunos ids fallaron. Guardados en errors_ids.txt")

    logger.info("CSV generado: %s (filas: %s)", output_csv, len(rows_sorted))
    return output_csv

# -----------------------------
# Descarga con reintentos y barra global
# -----------------------------
def download_file_with_retries(link, dst_path, max_retries=4, timeout=30):
    if os.path.exists(dst_path):
        return dst_path
    last_exc = None
    backoff = 1
    for attempt in range(1, max_retries+1):
        try:
            with SESSION.get(link, stream=True, timeout=timeout) as r:
                r.raise_for_status()
                ensure_folder(os.path.dirname(dst_path))
                with open(dst_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            return dst_path
        except Exception as e:
            last_exc = e
            logger.debug("Attempt %s failed for %s: %s", attempt, link, e)
            time.sleep(backoff)
            backoff *= 2
    logger.error("Fallo descarga %s tras %s intentos: %s", link, max_retries, last_exc)
    return None

def download_from_csv(csv_path, program_name, videos_folder="videos", subtitols_folder="subtitols", max_workers=6):
    programa_safe = safe_filename(program_name)
    videos_folder = os.path.join(videos_folder, programa_safe)
    subtitols_folder = os.path.join(subtitols_folder, programa_safe)
    ensure_folder(videos_folder)
    ensure_folder(subtitols_folder)

    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    logger.info("Iniciando descargas (%d archivos) ...", len(rows))
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {}
        for row in rows:
            link = row["Link"].strip()
            fname = row["File Name"].strip()
            ext = fname.split(".")[-1].lower() if "." in fname else ""
            if ext == "mp4" or ".mp4" in link:
                dst = os.path.join(videos_folder, f'{safe_filename(row["Name"])} - {safe_filename(row["Quality"])}.mp4')
            else:
                dst = os.path.join(subtitols_folder, f'{safe_filename(row["Name"])} - {safe_filename(row["Quality"])}.{ext or "vtt"}')
            futures[ex.submit(download_file_with_retries, link, dst)] = (row, dst)

        for future in tqdm(as_completed(futures), total=len(futures), desc="Descargando", unit="file"):
            row, dst = futures[future]
            try:
                res = future.result()
                if res:
                    logger.debug("Guardado: %s", res)
                else:
                    logger.warning("No guardado: %s", dst)
            except Exception as e:
                logger.error("Error descarga fila %s : %s", row, e)

    logger.info("Descargas finalizadas.")

# -----------------------------
# MAIN
# -----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("programa", help="Nombre del programa (nombonic)")
    parser.add_argument("--csv", default="links-fitxers.csv")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--skip-csv", action="store_true", help="No regenerar CSV si existe")
    parser.add_argument("--force-csv", action="store_true", help="Forzar regeneración de CSV aunque exista")
    parser.add_argument("--caps-per-pag", type=int, default=1000)
    args = parser.parse_args()

    prog = args.programa

    try:
        logger.info("Buscando programa en API...")
        pid = obtener_program_id(prog)
        logger.info("ID del programa: %s", pid)

        logger.info("Obteniendo capítulos...")
        cids = obtener_ids_capitulos(pid,items_pagina=args.caps_per_pag)
        logger.info("%d capítulos encontrados.", len(cids))

        if not args.skip_csv or args.force_csv or not os.path.exists(args.csv):
            csv_path = build_links_csv(cids, output_csv=args.csv, workers=args.workers)
        else:
            csv_path = args.csv
            logger.info("Usando CSV existente: %s", csv_path)

        input("Revisa el CSV si quieres. Presiona ENTER para iniciar descargas...")

        pname = obtener_program_name(prog)
        download_from_csv(csv_path, pname, max_workers=args.workers)
        logger.info("Proceso completado.")

    except KeyboardInterrupt:
        logger.warning("Interrumpido por usuario.")
    except Exception as e:
        logger.exception("Fallo: %s", e)

if __name__ == "__main__":
    main()
