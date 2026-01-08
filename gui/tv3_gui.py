#!/usr/bin/env python3

"""
tv3_gui.py - Interfaz gráfica para TV3 GUI Downloader
Versión completa con Vista Previa de Capítulos y Selección Individual
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
import threading
import requests
import queue
import sys
import re
import time
import os
from datetime import datetime
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import logging

# ----------------------------
# Config / Logging [3, 4]
# ----------------------------
LOGFILE = "tv3_gui_debug.log"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("TV3")
file_handler = logging.FileHandler(LOGFILE, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
logger.addHandler(file_handler)

def make_session(retries=5):
    s = requests.Session()
    retry = Retry(
        total=retries, read=retries, connect=retries, backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(['GET', 'POST', 'HEAD'])
    )
    adapter = HTTPAdapter(max_retries=retry)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; TV3enmassa/8.1-pro)'})
    s.trust_env = False
    return s

SESSION = make_session()

# ----------------------------
# Clases de Apoyo [5-8]
# ----------------------------
class QueueLogHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    def emit(self, record):
        msg = self.format(record)
        self.log_queue.put(("log", msg))

class StdoutRedirector:
    def __init__(self, log_queue):
        self.log_queue = log_queue
        handler = QueueLogHandler(self.log_queue)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    def write(self, message):
        if message.strip(): self.log_queue.put(("log", message.rstrip()))
    def flush(self): pass

class CTkToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, event=None):
        if self.tipwindow or not self.text: return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tipwindow = tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = ctk.CTkLabel(tw, text=self.text, fg_color="#2b2b2b", corner_radius=6, padx=10, pady=5)
        label.pack()

    def _hide(self, event=None):
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

# ----------------------------
# Aplicaci車n Principal [9-11]
# ----------------------------
class TV3_GUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("TV3 GUI Downloader")
        self.geometry("1000x950")
        
        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.file_progress_queue = queue.Queue(maxsize=200)
        
        self.program_info = None
        self.manifest_data = None
        self.is_downloading = False
        self.active_downloads = {}
        self.logs_visible = False

        self.create_widgets()
        
        sys.stdout = StdoutRedirector(self.log_queue)
        self.update_logs()
        self.update_progress()
        self.update_file_progress()

    def create_widgets(self):
        # 1. Header [11]
        self.top_header = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray90", "gray20"))
        self.top_header.pack(side="top", fill="x")
        ctk.CTkLabel(self.top_header, text="?? TV3 GUI Downloader", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=15)

        # 2. Body Scrollable [12, 13]
        self.main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_scroll.pack(side="top", fill="both", expand=True)
        content_frame = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Configuraci車n [13-16]
        config_frame = ctk.CTkFrame(content_frame, corner_radius=10)
        config_frame.pack(fill="x", pady=(0, 20))
        
        ctk.CTkLabel(config_frame, text="?? Configuraci車n", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=15, pady=10)

        input_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        input_frame.pack(fill="x", padx=15, pady=5)
        self.program_entry = ctk.CTkEntry(input_frame, placeholder_text="ej: dr-slump")
        self.program_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.search_btn = ctk.CTkButton(input_frame, text="?? Buscar", width=100, command=self.search_program)
        self.search_btn.pack(side="left")

        # Selectores Grid [15-18]
        opts_grid = ctk.CTkFrame(config_frame, fg_color="transparent")
        opts_grid.pack(fill="x", padx=15, pady=10)
        
        self.quality_var = ctk.StringVar(value="Todas")
        self.quality_combo = ctk.CTkComboBox(opts_grid, values=["Todas"], variable=self.quality_var, width=140, state="disabled")
        self.quality_combo.grid(row=0, column=0, padx=5)

        self.vttlang_var = ctk.StringVar(value="Todos")
        self.vttlang_combo = ctk.CTkComboBox(opts_grid, values=["Todos"], variable=self.vttlang_var, width=140, state="disabled")
        self.vttlang_combo.grid(row=0, column=1, padx=5)

        self.workers_var = ctk.IntVar(value=3)
        self.workers_slider = ctk.CTkSlider(opts_grid, from_=1, to=10, number_of_steps=9, variable=self.workers_var, width=100)
        self.workers_slider.grid(row=0, column=2, padx=5)
        
        self.aria2_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts_grid, text="aria2c", variable=self.aria2_var).grid(row=0, column=3, padx=5)
        
        self.resume_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts_grid, text="Only Resume", variable=self.resume_var).grid(row=0, column=4, padx=5)

        # Output [19, 20]
        out_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        out_frame.pack(fill="x", padx=15, pady=10)
        self.output_entry = ctk.CTkEntry(out_frame)
        self.output_entry.insert(0, os.path.join(os.getcwd(), "downloads"))
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(out_frame, text="??", width=40, command=self.browse_folder).pack(side="left")

        # --- SECCI車N VISTA PREVIA (NUEVA) ---
        self.preview_frame = ctk.CTkFrame(content_frame, corner_radius=10)
        self.preview_frame.pack(fill="both", expand=True, pady=(0, 20))
        ctk.CTkLabel(self.preview_frame, text="?? Vista Previa de Cap赤tulos (Selecciona para filtrar)", 
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=15, pady=10)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview", background="#2a2d2e", foreground="white", fieldbackground="#2a2d2e", borderwidth=0)
        style.map("Treeview", background=[('selected', '#1f538d')])
        style.configure("Treeview.Heading", background="#333333", foreground="white", relief="flat")

        self.tree = ttk.Treeview(self.preview_frame, columns=("temp", "cap", "title", "quality", "size"), show="headings", height=8)
        headers = {"temp": "Temp.", "cap": "Cap.", "title": "T赤tulo", "quality": "Calidad", "size": "Tama?o"}
        for col, text in headers.items():
            self.tree.heading(col, text=text, command=lambda _c=col: self.sort_column(_c, False))
            self.tree.column(col, width=60 if col in ["temp", "cap"] else 100, anchor="center" if col != "title" else "w")
        self.tree.column("title", width=350)
        self.tree.pack(fill="both", expand=True, padx=15, pady=10)

        # Bot車n Descargar [21]
        self.download_btn = ctk.CTkButton(config_frame, text="?? Descargar Todo / Selecci車n", command=self.start_download, 
                                          height=40, fg_color="green", font=ctk.CTkFont(weight="bold"))
        self.download_btn.pack(fill="x", padx=15, pady=15)

        # Logs Frame [21-23]
        self.log_frame = ctk.CTkFrame(content_frame, corner_radius=10)
        self.log_frame.pack(fill="both", expand=True)
        log_head = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        log_head.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(log_head, text="?? Registro", font=ctk.CTkFont(weight="bold")).pack(side="left")
        self.toggle_log_btn = ctk.CTkButton(log_head, text="? Mostrar", width=80, command=self.toggle_logs)
        self.toggle_log_btn.pack(side="right")
        self.log_text_container = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        self.log_text = ctk.CTkTextbox(self.log_text_container, height=200)
        self.log_text.pack(fill="both", expand=True)

        # 3. Footer Progreso [11, 24, 25]
        self.bottom_fixed_frame = ctk.CTkFrame(self, height=220, fg_color=("gray90", "gray16"))
        self.bottom_fixed_frame.pack(side="bottom", fill="x", padx=20, pady=20)
        self.bottom_fixed_frame.pack_propagate(False)
        
        self.progress_info = ctk.CTkLabel(self.bottom_fixed_frame, text="Estado: Esperando...")
        self.progress_info.pack(pady=5)
        self.progress_bar = ctk.CTkProgressBar(self.bottom_fixed_frame)
        self.progress_bar.pack(fill="x", padx=20, pady=5)
        self.progress_bar.set(0)

        self.downloads_frame = ctk.CTkScrollableFrame(self.bottom_fixed_frame, height=120, label_text="? Descargas Activas")
        self.downloads_frame.pack(fill="x", padx=20, pady=5)
        self.no_downloads_label = ctk.CTkLabel(self.downloads_frame, text="Sin actividad", text_color="gray")
        self.no_downloads_label.pack(pady=10)

    # --- L車gica UI y Tablas ---
    def sort_column(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        try: l.sort(key=lambda t: int(t), reverse=reverse)
        except: l.sort(reverse=reverse)
        for index, (val, k) in enumerate(l): self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def update_preview_table(self):
        for i in self.tree.get_children(): self.tree.delete(i)
        if not self.manifest_data: return
        for item in self.manifest_data.get("items", []):
            self.tree.insert("", "end", values=(item["temporada"], item["temporada_capitol"], item["title"], item["quality"], "N/D"))

    def toggle_logs(self):
        if self.logs_visible: self.log_text_container.pack_forget()
        else: self.log_text_container.pack(fill="both", expand=True, padx=15, pady=5)
        self.logs_visible = not self.logs_visible
        self.toggle_log_btn.configure(text="? Ocultar" if self.logs_visible else "? Mostrar")

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder: self.output_entry.delete(0, "end"); self.output_entry.insert(0, folder)

    # --- L車gica de Hilos y Datos [26-32] ---
    def search_program(self):
        prog = self.program_entry.get().strip()
        if not prog: return
        self.search_btn.configure(state="disabled")
        self.progress_info.configure(text=f"Buscando {prog}...")
        
        def search_thread():
            try:
                info = obtener_program_info(prog)
                self.program_info = info
                self.log_queue.put(("log", f"? Programa: {info['titol']}"))
                cids = obtener_ids_capitulos(info['id'], workers=self.workers_var.get())
                self.manifest_data = build_manifest(cids, workers=self.workers_var.get())
                self.extract_available_qualities()
                self.extract_available_vttlangs()
                self.after(0, self.update_preview_table)
                self.progress_queue.put({"type": "info", "text": "? Listo para descargar"})
            except Exception as e:
                self.log_queue.put(("log", f"? Error: {str(e)}"))
            finally:
                self.after(0, lambda: self.search_btn.configure(state="normal"))

        threading.Thread(target=search_thread, daemon=True).start()

    def start_download(self):
        if not self.manifest_data: return
        
        # Obtener selecci車n del Treeview
        selected_indices = self.tree.selection()
        selected_titles = [self.tree.item(i)['values'][3] for i in selected_indices]

        def download_thread():
            try:
                self.after(0, lambda: self.download_btn.configure(state="disabled"))
                items = self.manifest_data.get("items", [])
                q_filt = self.quality_var.get()
                v_filt = self.vttlang_var.get()
                
                filtered = []
                for item in items:
                    # Si hay selecci車n en tabla, priorizarla
                    if selected_titles and item["title"] not in selected_titles: continue
                    # Filtros de combo si no hay selecci車n manual o como segundo filtro
                    if item["type"] == "mp4" and q_filt != "Todas" and q_filt not in item["quality"]: continue
                    if item["type"] == "vtt" and v_filt != "Todos" and v_filt not in item["quality"]: continue
                    filtered.append(item)

                if not filtered: 
                    self.log_queue.put(("log", "?? No hay archivos que coincidan.")); return

                self.download_from_manifest(filtered, self.program_info['titol'], len(filtered), 
                                           videos_folder=self.output_entry.get(), 
                                           max_workers=self.workers_var.get(), 
                                           use_aria2=self.aria2_var.get(), 
                                           resume=self.resume_var.get())
            except Exception as e:
                self.log_queue.put(("log", f"? Error descarga: {str(e)}"))
            finally:
                self.after(0, lambda: self.download_btn.configure(state="normal"))
                self.progress_queue.put({"type": "complete", "text": ""})

        threading.Thread(target=download_thread, daemon=True).start()

    # --- Motor de Descarga [33-36] ---
    def download_from_manifest(self, items, program_name, total_files, videos_folder="downloads", max_workers=3, use_aria2=False, resume=True):
        base_folder = videos_folder
        ensure_folder(base_folder)
        tasks = []
        for item in items:
            folder = os.path.join(base_folder, safe_filename(item["program"]))
            ensure_folder(folder)
            file_ext = item["file_name"].split('.')[-1]
            dst = os.path.join(folder, safe_filename(f"{item['name']}.{file_ext}"))
            
            if resume and not os.path.exists(dst + ".part"): continue
            if not resume and os.path.exists(dst): continue
            
            tasks.append({"link": item["link"], "dst": dst, "desc": os.path.basename(dst), "use_aria2": use_aria2})

        if not tasks: self.log_queue.put(("log", "?? Nada pendiente.")); return
        
        total_tasks = len(tasks)
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(download_chunked_with_callback if not t["use_aria2"] else download_with_aria2, 
                                 t["link"], t["dst"], t["desc"], progress_queue=self.file_progress_queue): t for t in tasks}
            for future in as_completed(futures):
                completed += 1
                self.progress_queue.put({"type": "progress", "value": completed/total_tasks})
                self.progress_queue.put({"type": "info", "text": f"Descargando: {completed}/{total_tasks}"})

    # (M谷todos de soporte para actualizar logs y progreso [37-42])
    def update_logs(self):
        try:
            while True:
                _, msg = self.log_queue.get_nowait()
                ts = datetime.now().strftime("%H:%M:%S")
                self.log_text.insert("end", f"[{ts}] {msg}\n"); self.log_text.see("end")
        except queue.Empty: pass
        self.after(100, self.update_logs)

    def update_progress(self):
        try:
            while True:
                p = self.progress_queue.get_nowait()
                if p["type"] == "progress": self.progress_bar.set(p["value"])
                if p["type"] == "info": self.progress_info.configure(text=f"Estado: {p['text']}")
                if p["type"] == "complete": self.progress_bar.set(1.0); self.progress_info.configure(text="? Finalizado")
        except queue.Empty: pass
        self.after(100, self.update_progress)

    def update_file_progress(self):
        try:
            while True:
                f = self.file_progress_queue.get_nowait()
                if f["type"] == "start": self.add_active_download(f["filename"])
                if f["type"] == "update": self.update_active_download(f["filename"], f["progress"])
                if f["type"] == "complete": self.remove_active_download(f["filename"])
        except queue.Empty: pass
        self.after(50, self.update_file_progress)

    def add_active_download(self, filename):
        if self.no_downloads_label.winfo_exists(): self.no_downloads_label.pack_forget()
        frame = ctk.CTkFrame(self.downloads_frame, fg_color="transparent")
        frame.pack(fill="x", pady=2)
        ctk.CTkLabel(frame, text=f"?? {filename[:50]}...", font=ctk.CTkFont(size=10)).pack(anchor="w")
        bar = ctk.CTkProgressBar(frame, height=5)
        bar.pack(fill="x"); bar.set(0)
        self.active_downloads[filename] = {"frame": frame, "bar": bar}

    def update_active_download(self, filename, progress):
        if filename in self.active_downloads: self.active_downloads[filename]["bar"].set(progress)

    def remove_active_download(self, filename):
        if filename in self.active_downloads:
            self.active_downloads[filename]["frame"].destroy()
            del self.active_downloads[filename]
        if not self.active_downloads: self.no_downloads_label.pack(pady=10)

    def extract_available_qualities(self):
        qs = sorted({i["quality"] for i in self.manifest_data["items"] if i["type"] == "mp4"}, reverse=True)
        self.after(0, lambda: self.quality_combo.configure(values=["Todas"] + qs, state="normal"))

    def extract_available_vttlangs(self):
        ls = sorted({i["quality"] for i in self.manifest_data["items"] if i["type"] == "vtt"})
        self.after(0, lambda: self.vttlang_combo.configure(values=["Todos"] + ls, state="normal"))

# ----------------------------
# Utilidades y API [8, 43-58]
# ----------------------------
def ensure_folder(path): 
    if not os.path.exists(path): os.makedirs(path, exist_ok=True)

def safe_filename(name): 
    return re.sub(r'[\\/:"*?<>|]+', '-', name).strip()

def fetch_json(url, params=None):
    r = SESSION.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def obtener_program_info(nombonic):
    data = fetch_json("https://api.3cat.cat/programestv")
    items = []
    lletra = data["resposta"]["items"]["lletra"]
    if isinstance(lletra, list):
        for l in lletra: 
            it = l.get("item", [])
            items += it if isinstance(it, list) else [it]
    for p in items:
        if p.get("nombonic") == nombonic: return {"id": p["id"], "titol": p["titol"]}
    raise ValueError("No encontrado")

def obtener_ids_capitulos(program_id, workers=3):
    d = fetch_json("https://api.3cat.cat/videos", params={"programatv_id": program_id, "items_pagina": 100})
    pags = int(d["resposta"]["paginacio"].get("total_pagines", 1))
    all_cids = []
    for p in range(1, pags + 1):
        page_data = fetch_json("https://api.3cat.cat/videos", params={"programatv_id": program_id, "pagina": p, "items_pagina": 100})
        items = page_data["resposta"]["items"]["item"]
        if isinstance(items, dict): items = [items]
        all_cids += [{"id": i["id"], "tcap": i.get("capitol_temporada", "0")} for i in items]
    return all_cids

def api_extract_media_urls(id_cap):
    try:
        data = fetch_json("https://api.3cat.cat/pvideo/media.jsp", params={"media": "video", "idint": id_cap})
        info = {"programa": data["informacio"]["programa"], "title": data["informacio"]["titol"], 
                "temporada": data["informacio"].get("temporada", {}).get("idName", "0")[7:] or "0",
                "mp4s": [], "vtts": []}
        for entry in data.get("media", {}).get("url", []):
            if "mp4" in entry.get("file", "").lower():
                info["mp4s"].append({"label": entry.get("label", "mp4"), "url": entry["file"]})
        for sub in data.get("subtitols", []):
            info["vtts"].append({"label": sub.get("text", "vtt"), "url": sub["url"]})
        return info
    except: return None

def build_manifest(cids, workers=3):
    items = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(api_extract_media_urls, c["id"]) for c in cids]
        for i, f in enumerate(as_completed(futures)):
            res = f.result()
            if res:
                tcap = cids[i]["tcap"]
                safe_name = f"{res['programa']} - {res['temporada']}x{int(tcap):02d} - {res['title']}"
                for mp in res["mp4s"]:
                    items.append({"program": res["programa"], "temporada": res["temporada"], "temporada_capitol": tcap,
                                  "title": res["title"], "name": f"{safe_name} - {mp['label']}", 
                                  "quality": mp["label"], "link": mp["url"], "file_name": mp["url"].split("/")[-1], "type": "mp4"})
                for vt in res["vtts"]:
                    items.append({"program": res["programa"], "temporada": res["temporada"], "temporada_capitol": tcap,
                                  "title": res["title"], "name": f"{safe_name} - {vt['label']}", 
                                  "quality": vt["label"], "link": vt["url"], "file_name": vt["url"].split("/")[-1], "type": "vtt"})
    return {"items": items}

def download_chunked_with_callback(url, dst, desc, progress_queue=None):
    tmp = dst + ".part"
    progress_queue.put({"type": "start", "filename": desc})
    try:
        with SESSION.get(url, stream=True, timeout=20) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk); downloaded += len(chunk)
                    if total and progress_queue: progress_queue.put({"type": "update", "filename": desc, "progress": downloaded/total})
        os.replace(tmp, dst)
        progress_queue.put({"type": "complete", "filename": desc})
        return True
    except: return False

def download_with_aria2(url, dst, desc, progress_queue=None):
    cmd = ["aria2c", "--dir", os.path.dirname(dst), "--out", os.path.basename(dst), url]
    try: subprocess.check_call(cmd); return True
    except: return False

if __name__ == "__main__":
    app = TV3_GUI()
    app.mainloop()