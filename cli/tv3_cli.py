#!/usr/bin/env python3
"""

Características incluidas:
- CLI con opciones
- Session con Retries
- Extracción paralela de IDs
- Extracción por capítulo (mp4 + vtt)
- CSV + manifest.json
- Caché (cache/<id>.json)
- Descarga paralela con barra global + barras individuales (velocidad, ETA)
- Resume con Range support (y modo --resume que solo actúa sobre .part)
- Integración opcional aria2 (si está disponible) — ignorada para resume de .part
- Logging a consola (INFO) y fichero (DEBUG)
"""
import argparse
import requests
import csv
import os
import re
import time
import json
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from tqdm import tqdm

# ----------------------------
# Config / Logging
# ----------------------------
LOGFILE = "tv3_cli_debug.log"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("TV3")
file_handler = logging.FileHandler(LOGFILE, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
logger.addHandler(file_handler)

# ----------------------------
# Utilities
# ----------------------------
def ensure_folder(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def safe_filename(name):
    name = re.sub(r'[\\/:"*?<>|]+', '-', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def make_session(retries=5, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504)):
    s = requests.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(['GET','POST','HEAD'])
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; TV3enmassa/8.1-pro)'})
    s.trust_env = False
    return s

SESSION = make_session()

def fetch_json(url, params=None, timeout=20):
    r = SESSION.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

# ----------------------------
# Cache helpers
# ----------------------------
CACHE_DIR = "cache"
ensure_folder(CACHE_DIR)

def cache_get(id_):
    path = os.path.join(CACHE_DIR, f"{id_}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def cache_set(id_, data):
    path = os.path.join(CACHE_DIR, f"{id_}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.debug("Cache write failed %s: %s", path, e)

# ----------------------------
# API helpers (fusión programestv)
# ----------------------------
def obtener_program_info(nombonic):
    data = fetch_json("https://api.3cat.cat/programestv")
    try:
        lletra = data["resposta"]["items"]["lletra"]
        items = []
        if isinstance(lletra, dict) and "item" in lletra:
            it = lletra["item"]
            items = it if isinstance(it, list) else [it]
        elif isinstance(lletra, list):
            for l in lletra:
                if "item" in l:
                    it = l["item"]
                    items += it if isinstance(it, list) else [it]
        for p in items:
            if isinstance(p, dict) and p.get("nombonic") == nombonic:
                return {"id": p.get("id"), "titol": p.get("titol"), "nombonic": p.get("nombonic")}
    except Exception as e:
        logger.debug("Error parsing programestv: %s", e)
    raise RuntimeError(f"No se encontró programa con nombonic={nombonic}")

# ----------------------------
# IDs extraction (parallel pages)
# ----------------------------
def obtener_ids_capitulos(programatv_id, items_pagina=100, orden="capitol", workers=8, max_retries=2):
    params = {"items_pagina": items_pagina, "ordre": orden, "programatv_id": programatv_id, "pagina": 1}
    data = fetch_json("https://api.3cat.cat/videos", params=params)
    pags = int(data["resposta"]["paginacio"].get("total_pagines", 1))
    logger.info("Total páginas: %s", pags)

    def fetch_page(page):
        attempts = 0
        while attempts <= max_retries:
            attempts += 1
            try:
                params = {"items_pagina": items_pagina, "ordre": orden, "programatv_id": programatv_id, "pagina": page}
                d = fetch_json("https://api.3cat.cat/videos", params=params)
                item_list = d["resposta"]["items"]["item"]
                if isinstance(item_list, dict):
                    item_list = [item_list]
                ids_local = [i["id"] for i in item_list if "id" in i]
                return ids_local
            except Exception as e:
                logger.debug("fetch_page(%s) error (attempt %s): %s", page, attempts, e)
                time.sleep(1 * attempts)
        logger.error("Página %s falló tras %s intentos", page, max_retries)
        return []

    all_ids = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_page, p): p for p in range(1, pags+1)}
        for future in as_completed(futures):
            page = futures[future]
            try:
                ids = future.result()
                logger.info("Página %s -> %s ids", page, len(ids))
                all_ids.extend(ids)
            except Exception as e:
                logger.error("Error página %s: %s", page, e)

    all_ids = sorted(set(all_ids), key=lambda x: int(x))
    logger.info("Total capítulos: %s", len(all_ids))
    return all_ids

# ----------------------------
# Extract media metadata per chapter (with cache)
# ----------------------------
def api_extract_media_urls(id_cap):
    cached = cache_get(id_cap)
    if cached:
        return cached

    url = "https://api.3cat.cat/pvideo/media.jsp"
    params = {"media": "video", "version": "0s", "idint": id_cap}
    try:
        r = SESSION.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        info = {}
        info["id"] = id_cap
        info["programa"] = data.get("informacio", {}).get("programa", "UnknownProgram")
        info["title"] = data.get("informacio", {}).get("titol", f"capitol-{id_cap}")
        info["capitol"] = data.get("informacio", {}).get("capitol", str(id_cap))
        info["temporada"] = data.get("informacio", {}).get("temporada") or ""
        files = data.get("media", {}).get("url", []) or []
        if isinstance(files, dict):
            files = [files]
        mp4s = []
        for entry in files:
            if not isinstance(entry, dict): continue
            mp4 = entry.get("file")
            label = entry.get("label") or entry.get("quality") or entry.get("descripcio") or ""
            if mp4 and ("mp4" in mp4.lower()):
                mp4s.append({"label": label or "mp4", "url": mp4})
        vfiles = data.get("subtitols", []) or []
        if isinstance(vfiles, dict):
            vfiles = [vfiles]
        vtts = []
        for entry in vfiles:
            if not isinstance(entry, dict): continue
            vtt = entry.get("url")
            label = entry.get("text") or entry.get("lang") or ""
            if vtt and (".vtt" in vtt.lower() or "vtt" in vtt.lower()):
                vtts.append({"label": label or "vtt", "url": vtt})
        info["mp4s"] = mp4s
        info["vtts"] = vtts
        cache_set(id_cap, info)
        return info
    except Exception as e:
        logger.error("Error fetch media id=%s : %s", id_cap, e)
        return None

# ----------------------------
# CSV + manifest builder (parallel)
# ----------------------------
def build_links_csv(cids, output_csv="links-fitxers.csv", manifest_path="manifest.json", workers=8, retry_failed=2, include_vtt=True, quality_filter=""):
    ensure_folder("cache")
    rows = []
    failed = []

    def worker(cid):
        attempts = 0
        while attempts <= retry_failed:
            attempts += 1
            res = api_extract_media_urls(cid)
            if res:
                break
            logger.warning("Retry media id=%s attempt=%s", cid, attempts)
            time.sleep(1 * attempts)
        if not res:
            failed.append(cid)
            return []
        program = safe_filename(res["programa"])
        title = safe_filename(res["title"])
        capitol = res.get("capitol", str(res["id"]))
        safe_name = f"{program} - {title}"
        local = []
        # Filtrar mp4 por quality_filter
        for mp in res["mp4s"]:
            if quality_filter and quality_filter not in mp["label"]:
                continue
            fname = mp["url"].split("/")[-1]
            local.append([capitol, program, title, safe_name, mp["label"], mp["url"], fname, "mp4"])
        # Subtítulos solo si include_vtt=True
        if include_vtt:
            for vt in res["vtts"]:
                fname = vt["url"].split("/")[-1]
                local.append([capitol, program, title, safe_name, vt["label"], vt["url"], fname, "vtt"])
        return local

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(worker, cid): cid for cid in cids}
        with tqdm(total=len(futures), desc="Extrayendo capítulos", unit="cap") as p:
            for future in as_completed(futures):
                cid = futures[future]
                try:
                    chapter_rows = future.result()
                    rows.extend(chapter_rows)
                except Exception as e:
                    logger.error("Error procesando id %s: %s", cid, e)
                    failed.append(cid)
                p.update(1)

    def safe_int(x):
        try:
            return int(x)
        except:
            return 0
    rows_sorted = sorted(rows, key=lambda r: safe_int(r[0]))

    # CSV
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Capitol", "Program", "Title", "Name", "Quality", "Link", "File Name", "Type"])
        writer.writerows(rows_sorted)

    # Manifest JSON
    manifest = {"generated_at": time.time(), "items": []}
    for r in rows_sorted:
        manifest["items"].append({
            "capitol": r[0],
            "program": r[1],
            "title": r[2],
            "name": r[3],
            "quality": r[4],
            "link": r[5],
            "file_name": r[6],
            "type": r[7]
        })
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, ensure_ascii=False, indent=2)

    if failed:
        with open("errors_ids.txt", "w", encoding="utf-8") as ef:
            for fid in failed:
                ef.write(str(fid) + "\n")
        logger.warning("Algunos ids fallaron. Guardados en errors_ids.txt")

    logger.info("CSV generado: %s, manifest: %s, filas: %s", output_csv, manifest_path, len(rows_sorted))
    return output_csv, manifest_path, len(rows_sorted)

# ----------------------------
# Downloader (igual que antes, con resume-only logic en download_from_csv)
# ----------------------------
def supports_range(url):
    try:
        r = SESSION.head(url, timeout=10)
        if r.status_code // 100 == 2:
            return 'accept-ranges' in r.headers.get('accept-ranges', '').lower() or 'bytes' in r.headers.get('accept-ranges', '').lower()
    except Exception as e:
        logger.debug("supports_range error %s", e)
    return False

def download_chunked(url, dst, desc_name, max_retries=4, timeout=30, use_range=True):
    ensure_folder(os.path.dirname(dst))
    tmp = dst + ".part"
    existing = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    headers = {}

    if use_range and existing > 0:
        headers["Range"] = f"bytes={existing}-"

    backoff = 1
    last_exc = None

    for attempt in range(1, max_retries + 1):
        try:
            with SESSION.get(url, stream=True, timeout=timeout, headers=headers) as r:

                # ---------- CLAVE ----------
                if "Range" in headers:
                    if r.status_code == 206:
                        mode = "ab"   # resume REAL
                    elif r.status_code == 416:
                        # Ya estaba completo
                        os.replace(tmp, dst)
                        return dst
                    else:
                        # 200 OK → servidor ignoró Range
                        logger.warning("Servidor ignoró Range para %s, reiniciando descarga", dst)
                        existing = 0
                        headers.pop("Range", None)
                        mode = "wb"
                else:
                    mode = "wb"
                # ---------------------------

                r.raise_for_status()

                total = r.headers.get("Content-Length")
                total = int(total) if total else None
                total_bytes = (existing + total) if total and mode == "ab" else total

                with open(tmp, mode) as f, tqdm(
                    total=total_bytes,
                    initial=existing if mode == "ab" else 0,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=desc_name,
                    leave=False,
                    miniters=1,
                    mininterval=0.1
                ) as pbar:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

                os.replace(tmp, dst)
                return dst

        except Exception as e:
            last_exc = e
            logger.debug("download attempt %s failed for %s: %s", attempt, url, e)
            time.sleep(backoff)
            backoff *= 2

    logger.error("Failed download %s after %s attempts: %s", url, max_retries, last_exc)
    return None

def download_with_aria2(url, dst, aria2c_bin="aria2c"):
    ensure_folder(os.path.dirname(dst))
    cmd = [
        aria2c_bin,
        "--file-allocation=none",
        "--max-connection-per-server=4",
        "--split=4",
        "--continue=true",
        "--dir", os.path.dirname(dst),
        "--out", os.path.basename(dst),
        url
    ]
    try:
        subprocess.check_call(cmd)
        return dst
    except Exception as e:
        logger.debug("aria2 failed: %s", e)
        return None

def download_from_csv(csv_path, program_name, total_files, videos_folder="downloads", subtitols_folder="downloads", max_workers=6, use_aria2=False, resume=True):
    """
    Si resume=True -> solo intenta descargar archivos que tengan dst + '.part' existentes.
    Si resume=False -> omite los archivos completos (dst) y descarga los que faltan.
    """
    program_safe = safe_filename(program_name)
    base_folder = videos_folder
    ensure_folder(base_folder)

    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    logger.info("Iniciando descargas: %s archivos (manifiesto)", len(rows))

    # Preparar lista de tareas según modo resume
    tasks = []  # cada item = dict(link, dst, desc_name, method_use_aria2_bool)
    for row in rows:
        link = row["Link"].strip()
        fname = row["File Name"].strip()
        program = safe_filename(row["Program"])
        folder = os.path.join(base_folder, program)
        ensure_folder(folder)
        cap = row["Capitol"]
        try:
            final_name = f"S01E{int(cap):02d} - {row['Name']}.{fname.split('.')[-1]}"
        except Exception:
            final_name = f"{row['Name']}.{fname.split('.')[-1]}"
        dst = os.path.join(folder, safe_filename(final_name))
        tmp = dst + ".part"

        # Resume-only mode: solo filas con .part existentes
        if resume:
            if not os.path.exists(tmp):
                logger.debug("Skipping %s: no existe %s (resume-only)", dst, os.path.basename(tmp))
                continue
            # Forzar uso del downloader interno para reanudar .part (aria2 no trabaja con nuestro .part)
            if use_aria2:
                logger.info("resume=True: forzando downloader interno para reanudar %s (aria2 ignorado)", dst)
                method_use_aria2 = False
            else:
                method_use_aria2 = False
        else:
            # Normal mode: omitimos si ya existe el archivo completo
            if os.path.exists(dst):
                logger.info("Skip %s, ya existe", dst)
                continue
            method_use_aria2 = bool(use_aria2)

        desc_name = os.path.basename(dst)
        tasks.append({"link": link, "dst": dst, "desc": desc_name, "use_aria2": method_use_aria2})

    if not tasks:
        logger.info("No hay tareas para procesar (según el modo resume/estado de .part/archivos existentes).")
        return

    logger.info("Tareas a ejecutar: %s", len(tasks))

    # Ejecutar descargas paralelas
    with ThreadPoolExecutor(max_workers=max_workers) as ex, tqdm(total=len(tasks), desc="Progreso total", unit="tarea") as pbar:
        futures = {}
        for t in tasks:
            if t["use_aria2"]:
                fut = ex.submit(download_with_aria2, t["link"], t["dst"])
            else:
                fut = ex.submit(download_chunked, t["link"], t["dst"], t["desc"], 4, 30, not resume)  # use_range=True en modo normal; en resume ya estamos reanudando por .part
            futures[fut] = t["dst"]

        for future in as_completed(futures):
            dst = futures[future]
            try:
                res = future.result()
                if res:
                    logger.debug("Guardado: %s", res)
                else:
                    logger.warning("No guardado: %s", dst)
            except Exception as e:
                logger.error("Error en descarga: %s (%s)", dst, e)
            pbar.update(1)

    logger.info("Descargas finalizadas.")

# ----------------------------
# Main CLI
# ----------------------------
def main():
    parser = argparse.ArgumentParser(description="TV3 CLI - Downloader")
    parser.add_argument("programa", help="Nombre del programa (nombonic) ej: dr-slump")
    parser.add_argument("--csv", default="links-fitxers.csv")
    parser.add_argument("--manifest", default="manifest.json")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--pagesize", type=int, default=100)
    parser.add_argument("--only-list", action="store_true", help="Solo generar CSV/manifest, no descargar")
    parser.add_argument("--quality", type=str, default="", help="Filtrar calidad e.g. 720")
    parser.add_argument("--no-vtt", action="store_true", help="No descargar subtitulos")
    parser.add_argument("--aria2", action="store_true", help="Usar aria2c para descargas si disponible")
    parser.add_argument("--resume", action="store_true", help="Habilitar resume con Range si es posible (modo resume-only: solo actúa sobre .part)")
    parser.add_argument("--debug", action="store_true", help="Activar debug logs")
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug mode on")

    try:
        info = obtener_program_info(args.programa)
        logger.info("Programa: %s  id=%s", info.get("titol"), info.get("id"))
        cids = obtener_ids_capitulos(info.get("id"), items_pagina=args.pagesize, workers=args.workers)
        csv_path, manifest_path, total_files = build_links_csv(
            cids,
            output_csv=args.csv,
            manifest_path=args.manifest,
            workers=args.workers,
            include_vtt=not args.no_vtt,
            quality_filter=args.quality
        )
        if args.only_list:
            logger.info("Solo list. CSV y manifest generados.")
            return
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        total_assets = len(manifest.get("items", []))
        download_from_csv(csv_path, info.get("titol"), total_assets, max_workers=args.workers, use_aria2=args.aria2, resume=args.resume)
        logger.info("Proceso completado.")
    except KeyboardInterrupt:
        logger.warning("Interrumpido por usuario.")
    except Exception as e:
        logger.exception("Fallo general: %s", e)

if __name__ == "__main__":
    main()
