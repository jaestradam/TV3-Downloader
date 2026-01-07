import re
import requests
import csv
import os
import time

# -----------------------------
#  UTILIDADES
# -----------------------------
def ensure_folder(path):
    if not os.path.exists(path):
        os.makedirs(path)

def safe_filename(name):
    # Evita caracteres problemáticos en filenames
    return re.sub(r'[\\/:"*?<>|]+', '-', name)

def download_file_to_folder(url, folder, final_name, timeout=30):
    """
    Descarga un archivo desde 'url' hacia 'folder'.
    Devuelve la ruta local si se descarga correctamente, o None si falla.
    """
    if not url:
        return None

    ensure_folder(folder)
    local_name = url.split("/")[-1]
    local_name = final_name
    local_path = os.path.join(folder, local_name)

    try:
        with requests.get(url, stream=True, timeout=timeout, headers={'User-Agent': 'Mozilla/5.0'}) as r:
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        return local_path
    except Exception as e:
        print(f"    ! Error descargando {url}: {e}")
        return None

# -----------------------------
#  EXTRACCION
# -----------------------------
def extract_video_code(url):
    pattern = r"/(\d+)/?$"
    matches = re.findall(pattern, url)
    return matches[-1] if matches else None

def extract_video_codes(urls):
    return [extract_video_code(u) for u in urls if extract_video_code(u)]

def generate_video_urls(video_codes):
    return [
        f"http://dinamics.ccma.cat/pvideo/media.jsp?media=video&version=0s&idint={code}"
        for code in video_codes
    ]

def extract_media_urls(url):
    print("Fetching content from:", url)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(url, headers=headers)
    print("Response status code:", response.status_code)
    content = response.text

    # Programa y titol (si no existeixen, posam valors defaults)
    programa_match = re.search(r'"programa":"([^"]+)"', content)
    programa = programa_match.group(1) if programa_match else "SensePrograma"

    title_match = re.search(r'"titol":"([^"]+)"', content)
    title = title_match.group(1) if title_match else "SenseTitol"

    # Troba tots els mp4 i les seves etiquetes
    mp4_matches = re.findall(r'"file":"(https?://[^"]+\.mp4)","label":"([^"]+)"', content)

    # Troba subtítols: retorna tuples (texteEtiqueta, urlVtt)
    vtt_matches = re.findall(r'"subtitols":\[\{"text":"([^"]+)"[^}]+"url":"((?!sprite\.vtt).+?\.vtt)"', content)

    # Agafar l'últim 720p i l'últim 480p (com el codi original)
    last_720p = None
    last_480p = None
    for mp4_url, label in mp4_matches:
        if label == "720p":
            last_720p = mp4_url
        elif label == "480p":
            last_480p = mp4_url

    # Retornem programa, titol, llista [720p,480p], i subtitols tal qual
    return programa, title, [last_720p, last_480p], vtt_matches

# -----------------------------
#  GENERAR CSV AMB ELS ENLLAÇOS (estructura original)
# -----------------------------
def build_links_csv(links_txt="links.txt", output_csv="links-fitxers.csv"):
    with open(links_txt, "r", encoding="utf-8") as f:
        html_urls = [line.strip() for line in f if line.strip()]

    video_codes = extract_video_codes(html_urls)
    video_urls = generate_video_urls(video_codes)

    with open(output_csv, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Program", "Title", "Name", "Quality", "Link", "File Name"])  # mateixa estructura que l'original

        for video_url in video_urls:
            programa, title, mp4_urls, vtt_urls = extract_media_urls(video_url)
            safe_name = safe_filename(f"{programa} - {title}")
            safe_programa = safe_filename(f"{programa}")
            safe_title = safe_filename(f"{title}")

            # Escriure línies per als MP4 (una per qualitat existent)
            for i, mp4 in enumerate(mp4_urls):
                if mp4 is None:
                    continue
                label = "720p" if i == 0 else "480p"
                file_name = mp4.split("/")[-1]
                writer.writerow([safe_programa, safe_title, safe_name, label, mp4, file_name])

            # Escriure línies per als VTT (una per subtítol)
            for text_label, vtt_url in vtt_urls:
                # El regex ja ha de retornar la URL completa; si no, aquí es podria fer un fix
                link = vtt_url
                file_name = link.split("/")[-1] if link else ""
                writer.writerow([safe_programa, safe_title, safe_name, text_label, link, file_name])

    print("CSV generado:", output_csv)
    return output_csv

# -----------------------------
#  BLOQUE DE DESCARGA: LLEGIR CSV I DESCARGAR SEGONS EXTENSIÓ
# -----------------------------
def download_from_csv(csv_path="links-fitxers.csv", videos_folder="videos", subtitols_folder="subtitols"):
    ensure_folder(videos_folder)
    ensure_folder(subtitols_folder)

    with open(csv_path, "r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            link = row.get("Link", "").strip()
            file_name = row.get("File Name", "").strip()
            program_name = row.get("Program", "").strip()
            final_name = row.get("Name", "").strip()
            final_label = row.get("Quality", "").strip()
            if not link:
                print("  - Saltant fila sense link:", row)
                continue

            ext = file_name.split(".")[-1].lower() if "." in file_name else ""
            print(f"Descargando [{row.get('Quality')}] {final_name} {final_label} {file_name} ...")
            final_videos_folder=videos_folder+"/"+program_name
            final_subtitols_folder=subtitols_folder+"/"+program_name
            if ext == "mp4":
                saved = download_file_to_folder(link, final_videos_folder, final_name+" - "+final_label+".mp4")
            elif ext == "vtt":
                saved = download_file_to_folder(link, final_subtitols_folder, final_name+" - "+final_label+".vtt")
            else:
                # si extensió desconeguda, intentar deduir per la url
                if ".mp4" in link:
                    saved = download_file_to_folder(link, final_videos_folder, final_name+" - "+final_label+".mp4")
                elif ".vtt" in link:
                    saved = download_file_to_folder(link, final_subtitols_folder, final_name+" - "+final_label+".vtt")
                else:
                    print("  ! No se reconoce la extensión, saltando:", link)
                    saved = None

            if saved:
                print("   -> Guardado en:", saved)
            else:
                print("   -> No guardado.")

            # Pequeña pausa para no sobrecargar el servidor (opcional)
            time.sleep(0.2)

# -----------------------------
#  MAIN
# -----------------------------
if __name__ == "__main__":
    csv_path = build_links_csv(links_txt="links.txt", output_csv="links-fitxers.csv")
    print("Iniciando descarga de los archivos listados en", csv_path)
    download_from_csv(csv_path, videos_folder="videos", subtitols_folder="subtitols")
    print("✔ Proceso completado.")
