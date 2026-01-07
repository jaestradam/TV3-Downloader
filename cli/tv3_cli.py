import argparse
import requests
import csv
import os
import re
import time
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed

# -----------------------------
# UTILIDADES
# -----------------------------
def ensure_folder(path):
    if not os.path.exists(path):
        os.makedirs(path)

def safe_filename(name):
    return re.sub(r'[\\/:"*?<>|]+', '-', name)

def fetch_json(url, params=None, timeout=15):
    r = requests.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0'}, timeout=timeout)
    r.raise_for_status()
    return r.json()

def download_file_to_folder(url, folder, final_name, timeout=30):
    """
    Descarga un archivo desde 'url' hacia 'folder/final_name'.
    Devuelve la ruta local si se descarga correctamente, o None si falla.
    Incluye barra de progreso compatible con descargas paralelas.
    """
    ensure_folder(folder)
    local_path = os.path.join(folder, final_name)

    # Si ya existe, no lo descargamos
    if os.path.exists(local_path):
        return local_path

    try:
        with requests.get(url, stream=True, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'}) as r:
            r.raise_for_status()

            total = int(r.headers.get("content-length", 0))

            # Barra de progreso individual
            with open(local_path, "wb") as f, tqdm(
                total=total,
                unit="B",
                unit_scale=True,
                desc=final_name,
                leave=False
            ) as pbar:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

        return local_path

    except Exception as e:
        print(f"    ❌ Error descargando {url}: {e}")
        # Si hubo fallo, borrar archivo corrupto
        if os.path.exists(local_path):
            os.remove(local_path)
        return None


# -----------------------------
# API 3CAT: obtener program ID
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

# -----------------------------
# API 3CAT: obtener program ID
# -----------------------------
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

# -----------------------------
# Obtener IDs de capítulos
# -----------------------------
def obtener_ids_capitulos(programatv_id):
    params = {"items_pagina": 1000, "ordre": "capitol", "programatv_id": programatv_id}
    data = fetch_json("https://api.3cat.cat/videos", params=params)
    ids = []

    try:
        item_list = data["resposta"]["items"]["item"]
        if isinstance(item_list, dict):
            item_list = [item_list]
        for i in item_list:
            if "id" in i:
                ids.append(i["id"])
    except Exception:
        pass
    return ids

# -----------------------------
# Extraer MP4 + VTT de un permalink
# -----------------------------
def api_extract_media_urls(id_cap):
    url = "https://api.3cat.cat/pvideo/media.jsp"
    params = {"media": "video", "version": "0s", "idint": id_cap}

    try:
        r = requests.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        r.raise_for_status()
        data = r.json()

        programa = data["informacio"]["programa"]
        title = data["informacio"]["titol"]

        # ---- MP4 ----
        files = data["media"]["url"]
        if not isinstance(files, list):
            files = []

        mp4s = []
        for entry in files:
            mp4 = entry.get("file")
            label = entry.get("label")
            if mp4 and mp4.lower().endswith(".mp4"):
                mp4s.append((label, mp4))

        # ---- VTT ----
        files = data.get("subtitols", [])
        if not isinstance(files, list):
            files = []

        subtitols = []
        for entry in files:
            vtt = entry.get("url")
            label = entry.get("text")
            if vtt and vtt.lower().endswith(".vtt"):
                subtitols.append((label, vtt))

        return programa, title, mp4s, subtitols

    except Exception as e:
        print(f"❌ Error al obtener los datos para id={id_cap}: {e}")
        return None

# -----------------------------
# Generar CSV con todos los enlaces
# -----------------------------
from concurrent.futures import ThreadPoolExecutor, as_completed

def build_links_csv(cids, output_csv="links-fitxers.csv", workers=10):
    print("\n📄 Generando CSV en paralelo...\n")

    rows = []

    def worker(cid):
        """Extrae los datos de un capítulo y devuelve la lista de filas CSV."""
        result = api_extract_media_urls(cid)
        if not result:
            return []  # fallo → nada para escribir

        programa, title, mp4s, vtts = result

        safe_programa = safe_filename(programa)
        safe_title = safe_filename(title)
        safe_name = safe_filename(f"{programa} - {title}")

        local_rows = []

        # MP4
        for label, mp4 in mp4s:
            if not mp4:
                continue
            file_name = mp4.split("/")[-1]
            local_rows.append([safe_programa, safe_title, safe_name, label, mp4, file_name])

        # VTT
        for text_label, vtt_url in vtts:
            if not vtt_url:
                continue
            file_name = vtt_url.split("/")[-1]
            local_rows.append([safe_programa, safe_title, safe_name, text_label, vtt_url, file_name])

        return local_rows

    # ---- Paralelización ----
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, cid): cid for cid in cids}

        for future in tqdm(as_completed(futures), total=len(cids), desc="Extrayendo", unit="capítulo"):
            try:
                chapter_rows = future.result()
                rows.extend(chapter_rows)
            except Exception as e:
                print(f"❌ Error procesando capítulo {futures[future]}: {e}")

    # ---- Escritura final del CSV ----
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Program", "Title", "Name", "Quality", "Link", "File Name"])
        writer.writerows(rows)

    print("✔ CSV generado:", output_csv)
    return output_csv

# -----------------------------
# Descarga paralela desde CSV
# -----------------------------
def download_task(row, videos_folder="videos", subtitols_folder="subtitols"):
    link = row["Link"].strip()
    file_name = row["File Name"].strip()
    program = safe_filename(row["Program"])
    base_name = safe_filename(row["Name"])
    label = safe_filename(row["Quality"])

    ext = file_name.split(".")[-1].lower()
    folder = videos_folder if ext == "mp4" else subtitols_folder

    final_name = f"{base_name} - {label}.{ext}"
    return download_file_to_folder(link, folder, final_name)

def download_from_csv(csv_path, program, videos_folder="videos", subtitols_folder="subtitols", max_workers=8):
    videos_folder = os.path.join(videos_folder, program)
    subtitols_folder = os.path.join(subtitols_folder, program)
    ensure_folder(videos_folder)
    ensure_folder(subtitols_folder)

    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    print("\n⬇️ Descargando archivos en paralelo…\n")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_task, row, videos_folder, subtitols_folder): row for row in rows}
        for future in tqdm(as_completed(futures), total=len(rows), desc="Descargando", unit="archivo"):
            try:
                _ = future.result()
            except Exception as e:
                print("Error:", e)

# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("programa", help="Nombre del programa (nombonic)")
    parser.add_argument("--csv", default="links-fitxers.csv")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    print("\n🔍 Buscando programa en API…\n")
    program_id = obtener_program_id(args.programa)
    print(f"✔ ID del programa: {program_id}")

    print("\n📺 Obteniendo capítulos…\n")
    chapter_ids = obtener_ids_capitulos(program_id)
    print(f"✔ {len(chapter_ids)} capítulos encontrados.")

    # Generar CSV
    csv_path = build_links_csv(chapter_ids, output_csv=args.csv, workers=args.workers)

    # Pausa para validar CSV
    print("\n🛑 Ahora puedes revisar y editar el CSV antes de descargar.")
    input("👉 Presiona ENTER para iniciar las descargas...")

    # Descargas paralelas
    download_from_csv(csv_path, obtener_program_name(args.programa), max_workers=args.workers)

    print("\n🎉 Proceso completado.\n")
