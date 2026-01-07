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
# Obtener permalink de capítulo
# -----------------------------
def obtener_permalink(id_cap):
    """
    Obtiene el permalink de un capítulo usando su idint.
    El permalink se encuentra en data['informacio']['permalink']
    """
    url = "https://api.3cat.cat/pvideo/media.jsp"
    params = {"media": "video", "version": "0s", "idint": id_cap}

    try:
        r = requests.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        r.raise_for_status()
        data = r.json()
        permalink = data["informacio"]["permalink"]
        if permalink:
            return permalink
        else:
            print(f"❌ No se encontró permalink en id={id_cap}")
            return None
    except Exception as e:
        print(f"❌ Error al obtener permalink para id={id_cap}: {e}")
        return None


# -----------------------------
# Obtener media de capítulo
# -----------------------------
def obtener_media(id_cap):
    """
    Obtiene todos los archivos MP4 de un capítulo usando su idint.
    Los MP4 están en data['media']['url']['file'], cada uno con 'label' y 'file'.
    
    Devuelve una lista de tuplas:
      [ (label, url_mp4), ... ]
    """
    url = "https://api.3cat.cat/pvideo/media.jsp"
    params = {"media": "video", "version": "0s", "idint": id_cap}

    try:
        r = requests.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        r.raise_for_status()
        data = r.json()

        # navegación segura
        files = data["media"]["url"]

        if not isinstance(files, list):
            print(f"❌ formato inesperado de 'file' en id={id_cap}")
            return []

        resultados = []
        for entry in files:
            mp4 = entry.get("file")
            label = entry.get("label")

            if mp4 and mp4.lower().endswith(".mp4"):
                resultados.append((label, mp4))

        if not resultados:
            print(f"❌ No se encontraron MP4 para id={id_cap}")

        return resultados

    except Exception as e:
        print(f"❌ Error al obtener MP4 para id={id_cap}: {e}")
        return []

# -----------------------------
# Obtener media de capítulo
# -----------------------------
def obtener_subtitulos(id_cap):
    """
    Obtiene todos los archivos MP4 de un capítulo usando su idint.
    Los MP4 están en data['media']['url']['file'], cada uno con 'label' y 'file'.
    
    Devuelve una lista de tuplas:
      [ (label, url_mp4), ... ]
    """
    url = "https://api.3cat.cat/pvideo/media.jsp"
    params = {"media": "video", "version": "0s", "idint": id_cap}

    try:
        r = requests.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        r.raise_for_status()
        data = r.json()

        # navegación segura
        files = data["subtitols"]

        if not isinstance(files, list):
            print(f"❌ formato inesperado de 'file' en id={id_cap}")
            return []

        resultados = []
        for entry in files:
            mp4 = entry.get("url")
            label = entry.get("text")

            if mp4 and mp4.lower().endswith(".vtt"):
                resultados.append((label, mp4))

        if not resultados:
            print(f"❌ No se encontraron MP4 para id={id_cap}")

        return resultados

    except Exception as e:
        print(f"❌ Error al obtener MP4 para id={id_cap}: {e}")
        return []


# -----------------------------
# Extraer MP4 + VTT de un permalink
# -----------------------------
def extract_media_urls(url):
    print("Fetching content from:", url)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(url, headers=headers)
    print("Response status code:", response.status_code)
    content = response.text

    # Programa y titol (si no existeixen, posam valors defaults)
    programa_match = re.search(r'"nomPrograma":"([^"]+)"', content)
    programa = programa_match.group(1) if programa_match else "SensePrograma"

    title_match = re.search(r'"titol":"([^"]+)"', content)
    title = title_match.group(1) if title_match else "SenseTitol"

    # Retornem programa, titol, llista [720p,480p], i subtitols tal qual
    return programa, title

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
def build_links_csv(cids, output_csv="links-fitxers.csv"):
    print("\n📄 Generando CSV...\n")
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Program", "Title", "Name", "Quality", "Link", "File Name"])

        for cid in tqdm(cids, desc="Extrayendo metadatos", unit="capítulo"):
            #programa, title = extract_media_urls(url)
            programa, title, mp4s, vtts = api_extract_media_urls(cid)
            #mp4s = obtener_media(cid)
            #vtts = obtener_subtitulos(cid)

            safe_programa = safe_filename(programa)
            safe_title = safe_filename(title)
            safe_name = safe_filename(f"{programa} - {title}")

            # MP4
            for label, mp4 in mp4s:
                if mp4 is None:
                    continue
                file_name = mp4.split("/")[-1]
                writer.writerow([safe_programa, safe_title, safe_name, label, mp4, file_name])

            # Todos los VTT
            for text_label, vtt_url in vtts:
                # El regex ja ha de retornar la URL completa; si no, aquí es podria fer un fix
                link = vtt_url
                file_name = link.split("/")[-1] if link else ""
                writer.writerow([safe_programa, safe_title, safe_name, text_label, link, file_name])

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
    #folder = os.path.join(folder, program)

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

    # Obtener permalinks de todos los capítulos
    # permalinks = []
    # for cid in tqdm(chapter_ids, desc="Generando permalinks", unit="capítulo"):
        # url = obtener_permalink(cid)
        # if url:
            # permalinks.append(url)

    # Generar CSV
    csv_path = build_links_csv(chapter_ids, output_csv=args.csv)

    # Pausa para validar CSV
    print("\n🛑 Ahora puedes revisar y editar el CSV antes de descargar.")
    input("👉 Presiona ENTER para iniciar las descargas...")

    # Descargas paralelas
    download_from_csv(csv_path, obtener_program_name(args.programa), max_workers=args.workers)

    print("\n🎉 Proceso completado.\n")
