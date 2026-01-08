#!/usr/bin/env python3
"""
tv3_gui.py - Interfaz gráfica para TV3 GUI Downloader
Requiere: customtkinter, pillow (además de las dependencias del script original)
Instalación: pip install customtkinter pillow
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import queue
import sys
import os
from datetime import datetime
import json
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# Importar el script original (asumiendo que está en el mismo directorio)
try:
    from tv3_cli import (
        obtener_program_info,
        obtener_ids_capitulos,
        build_links_csv,
        logger,
        safe_filename,
        ensure_folder,
        download_chunked,
        download_with_aria2,
        SESSION
    )
except ImportError:
    print("Error: No se puede importar tv3_cli.py")
    print("Asegúrate de que tv3_cli.py está en el mismo directorio")
    sys.exit(1)

# Configuración de CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class LogHandler:
    """Manejador de logs para capturar y mostrar en la GUI"""
    def __init__(self, text_widget, log_queue):
        self.text_widget = text_widget
        self.log_queue = log_queue
    
    def write(self, message):
        if message.strip():
            self.log_queue.put(("log", message))
    
    def flush(self):
        pass


class TV3_GUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Configuración de la ventana
        self.title("TV3 GUI Downloader")
        self.geometry("900x750")
        
        # Queue para comunicación entre threads
        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        
        # Variables
        self.program_info = None
        self.is_downloading = False
        self.download_thread = None
        self.available_qualities = set()  # Para almacenar calidades disponibles
        
        # Crear interfaz
        self.create_widgets()
        
        # Iniciar actualización de logs y progreso
        self.update_logs()
        self.update_progress()
        
    def create_widgets(self):
        """Crear todos los widgets de la interfaz"""
        
        # ===== HEADER =====
        header_frame = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray90", "gray20"))
        header_frame.pack(fill="x", padx=0, pady=0)
        
        title_label = ctk.CTkLabel(
            header_frame,
            text="🎬 TV3 GUI Downloader",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=15)
        
        # ===== FRAME PRINCIPAL =====
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # ===== SECCIÓN: CONFIGURACIÓN =====
        config_frame = ctk.CTkFrame(main_frame)
        config_frame.pack(fill="x", pady=(0, 10))
        
        config_label = ctk.CTkLabel(
            config_frame,
            text="⚙️ Configuración",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        config_label.pack(anchor="w", padx=15, pady=(15, 10))
        
        # Programa
        program_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        program_frame.pack(fill="x", padx=15, pady=5)
        
        ctk.CTkLabel(program_frame, text="Programa:", width=100, anchor="w").pack(side="left")
        self.program_entry = ctk.CTkEntry(program_frame, placeholder_text="ej: dr-slump")
        self.program_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.search_btn = ctk.CTkButton(
            program_frame,
            text="🔍 Buscar",
            width=100,
            command=self.search_program
        )
        self.search_btn.pack(side="left")
        
        # Info del programa
        self.info_label = ctk.CTkLabel(
            config_frame,
            text="",
            text_color=("gray50", "gray60"),
            anchor="w"
        )
        self.info_label.pack(fill="x", padx=15, pady=5)
        
        # Grid para opciones
        options_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        options_frame.pack(fill="x", padx=15, pady=10)
        
        # Calidad
        quality_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        quality_frame.grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=5)
        
        ctk.CTkLabel(quality_frame, text="Calidad:", width=100, anchor="w").pack(side="left")
        self.quality_var = ctk.StringVar(value="Todas")
        self.quality_combo = ctk.CTkComboBox(
            quality_frame,
            values=["Todas"],
            variable=self.quality_var,
            width=150,
            state="disabled"  # Deshabilitado hasta que se genere la lista
        )
        self.quality_combo.pack(side="left")
        
        # Workers
        workers_frame = ctk.CTkFrame(options_frame, fg_color="transparent")
        workers_frame.grid(row=0, column=1, sticky="ew", pady=5)
        
        ctk.CTkLabel(workers_frame, text="Workers:", width=100, anchor="w").pack(side="left")
        self.workers_var = ctk.IntVar(value=6)
        self.workers_slider = ctk.CTkSlider(
            workers_frame,
            from_=1,
            to=12,
            number_of_steps=11,
            variable=self.workers_var,
            width=150
        )
        self.workers_slider.pack(side="left", padx=(0, 10))
        self.workers_label = ctk.CTkLabel(workers_frame, text="6", width=30)
        self.workers_label.pack(side="left")
        
        self.workers_slider.configure(command=lambda v: self.workers_label.configure(text=str(int(v))))
        
        options_frame.columnconfigure(0, weight=1)
        options_frame.columnconfigure(1, weight=1)
        
        # Checkboxes
        check_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        check_frame.pack(fill="x", padx=15, pady=5)
        
        self.vtt_var = ctk.BooleanVar(value=True)
        self.vtt_check = ctk.CTkCheckBox(check_frame, text="Descargar subtítulos", variable=self.vtt_var)
        self.vtt_check.pack(side="left", padx=(0, 20))
        
        self.aria2_var = ctk.BooleanVar(value=False)
        self.aria2_check = ctk.CTkCheckBox(check_frame, text="Usar aria2c", variable=self.aria2_var)
        self.aria2_check.pack(side="left", padx=(0, 20))
        
        self.resume_var = ctk.BooleanVar(value=False)
        self.resume_check = ctk.CTkCheckBox(check_frame, text="Modo resume", variable=self.resume_var)
        self.resume_check.pack(side="left")
        
        # Carpeta de salida
        output_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        output_frame.pack(fill="x", padx=15, pady=10)
        
        ctk.CTkLabel(output_frame, text="Carpeta:", width=100, anchor="w").pack(side="left")
        self.output_entry = ctk.CTkEntry(output_frame, placeholder_text="Ruta de descarga")
        self.output_entry.insert(0, os.path.join(os.getcwd(), "downloads"))
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.browse_btn = ctk.CTkButton(
            output_frame,
            text="📁 Seleccionar",
            width=120,
            command=self.browse_folder
        )
        self.browse_btn.pack(side="left")
        
        # Botones de acción
        action_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        action_frame.pack(fill="x", padx=15, pady=(10, 15))
        
        self.list_btn = ctk.CTkButton(
            action_frame,
            text="📋 Generar Lista",
            command=self.generate_list,
            height=40
        )
        self.list_btn.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.download_btn = ctk.CTkButton(
            action_frame,
            text="⬇️ Descargar Todo",
            command=self.start_download,
            height=40,
            fg_color=("green", "darkgreen"),
            hover_color=("darkgreen", "green")
        )
        self.download_btn.pack(side="left", fill="x", expand=True)
        
        # ===== SECCIÓN: PROGRESO =====
        progress_frame = ctk.CTkFrame(main_frame)
        progress_frame.pack(fill="x", pady=(0, 10))
        
        progress_label = ctk.CTkLabel(
            progress_frame,
            text="📊 Progreso",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        progress_label.pack(anchor="w", padx=15, pady=(15, 10))
        
        # Barra de progreso
        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.pack(fill="x", padx=15, pady=5)
        self.progress_bar.set(0)
        
        # Info de progreso
        self.progress_info = ctk.CTkLabel(
            progress_frame,
            text="Estado: Esperando...",
            anchor="w"
        )
        self.progress_info.pack(fill="x", padx=15, pady=(5, 15))
        
        # ===== SECCIÓN: LOGS =====
        log_frame = ctk.CTkFrame(main_frame)
        log_frame.pack(fill="both", expand=True)
        
        log_label = ctk.CTkLabel(
            log_frame,
            text="📝 Registro de actividad",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        log_label.pack(anchor="w", padx=15, pady=(15, 10))
        
        # Text widget para logs
        self.log_text = ctk.CTkTextbox(log_frame, height=200, wrap="word")
        self.log_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        self.add_log("✅ Aplicación iniciada correctamente")
        self.add_log("💡 Introduce el nombre del programa (nombonic) y pulsa 'Buscar'")
    
    def add_log(self, message):
        """Añadir mensaje al log"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
    
    def update_logs(self):
        """Actualizar logs desde la queue"""
        try:
            while True:
                msg_type, message = self.log_queue.get_nowait()
                if msg_type == "log":
                    self.add_log(message.strip())
        except queue.Empty:
            pass
        
        self.after(100, self.update_logs)
    
    def update_progress(self):
        """Actualizar barra de progreso desde la queue"""
        try:
            while True:
                progress_data = self.progress_queue.get_nowait()
                
                if progress_data["type"] == "progress":
                    value = progress_data["value"]
                    self.progress_bar.set(value)
                
                elif progress_data["type"] == "info":
                    self.progress_info.configure(text=progress_data["text"])
                
                elif progress_data["type"] == "complete":
                    self.progress_bar.set(1.0)
                    self.progress_info.configure(text="✅ Proceso completado")
                    self.is_downloading = False
                    self.enable_controls()
                
                elif progress_data["type"] == "error":
                    self.progress_info.configure(text=f"❌ Error: {progress_data['text']}")
                    self.is_downloading = False
                    self.enable_controls()
        
        except queue.Empty:
            pass
        
        self.after(100, self.update_progress)
    
    def browse_folder(self):
        """Abrir diálogo para seleccionar carpeta"""
        folder = filedialog.askdirectory(title="Seleccionar carpeta de descarga")
        if folder:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, folder)
    
    def disable_controls(self):
        """Deshabilitar controles durante operaciones"""
        self.search_btn.configure(state="disabled")
        self.list_btn.configure(state="disabled")
        self.download_btn.configure(state="disabled")
        self.program_entry.configure(state="disabled")
    
    def enable_controls(self):
        """Habilitar controles"""
        self.search_btn.configure(state="normal")
        self.list_btn.configure(state="normal")
        self.download_btn.configure(state="normal")
        self.program_entry.configure(state="normal")
    
    def search_program(self):
        """Buscar información del programa"""
        program_name = self.program_entry.get().strip()
        
        if not program_name:
            messagebox.showwarning("Advertencia", "Introduce el nombre del programa")
            return
        
        self.disable_controls()
        self.add_log(f"🔍 Buscando programa: {program_name}")
        
        def search_thread():
            try:
                info = obtener_program_info(program_name)
                self.program_info = info
                
                self.log_queue.put(("log", f"✅ Programa encontrado: {info.get('titol')}"))
                self.log_queue.put(("log", f"📺 ID: {info.get('id')}"))
                
                # Actualizar label de info
                self.after(0, lambda: self.info_label.configure(
                    text=f"📺 {info.get('titol')} (ID: {info.get('id')})",
                    text_color=("green", "lightgreen")
                ))
                
            except Exception as e:
                self.log_queue.put(("log", f"❌ Error: {str(e)}"))
                self.program_info = None
                self.after(0, lambda: self.info_label.configure(
                    text="❌ Programa no encontrado",
                    text_color=("red", "lightcoral")
                ))
            finally:
                self.after(0, self.enable_controls)
        
        threading.Thread(target=search_thread, daemon=True).start()
    
    def generate_list(self):
        """Generar CSV y manifest sin descargar"""
        if not self.program_info:
            messagebox.showwarning("Advertencia", "Primero busca un programa")
            return
        
        self.disable_controls()
        self.add_log("📋 Generando lista de capítulos...")
        self.progress_info.configure(text="Estado: Extrayendo capítulos...")
        
        def generate_thread():
            try:
                program_id = self.program_info.get("id")
                workers = self.workers_var.get()
                quality = self.quality_var.get()
                include_vtt = self.vtt_var.get()
                
                quality_filter = "" if quality == "Todas" else quality
                
                self.log_queue.put(("log", "🔄 Obteniendo IDs de capítulos..."))
                cids = obtener_ids_capitulos(program_id, items_pagina=100, workers=workers)
                
                self.log_queue.put(("log", f"📊 Total capítulos encontrados: {len(cids)}"))
                self.log_queue.put(("log", "📝 Extrayendo metadatos..."))
                
                csv_path, manifest_path, total = build_links_csv(
                    cids,
                    output_csv="links-fitxers.csv",
                    manifest_path="manifest.json",
                    workers=workers,
                    include_vtt=include_vtt,
                    quality_filter=quality_filter
                )
                
                self.log_queue.put(("log", f"✅ CSV generado: {csv_path}"))
                self.log_queue.put(("log", f"✅ Manifest generado: {manifest_path}"))
                self.log_queue.put(("log", f"📊 Total archivos: {total}"))
                
                # Extraer calidades disponibles del manifest
                self.extract_available_qualities(manifest_path)
                
                self.progress_queue.put({"type": "info", "text": f"✅ Lista generada: {total} archivos"})
                
            except Exception as e:
                self.log_queue.put(("log", f"❌ Error generando lista: {str(e)}"))
                self.progress_queue.put({"type": "error", "text": str(e)})
            finally:
                self.after(0, self.enable_controls)
        
        threading.Thread(target=generate_thread, daemon=True).start()
    
    def extract_available_qualities(self, manifest_path):
        """Extraer calidades disponibles del manifest y actualizar el combobox"""
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            
            qualities = set()
            for item in manifest.get("items", []):
                if item.get("type") == "mp4":
                    quality = item.get("quality", "")
                    if quality:
                        qualities.add(quality)
            
            self.available_qualities = qualities
            
            # Actualizar el combobox en el hilo principal
            self.after(0, self.update_quality_selector, qualities)
            
        except Exception as e:
            self.log_queue.put(("log", f"⚠️ No se pudieron extraer las calidades: {str(e)}"))
    
    def update_quality_selector(self, qualities):
        """Actualizar el selector de calidad con las opciones disponibles"""
        if qualities:
            # Ordenar calidades de manera inteligente (mayor a menor)
            sorted_qualities = sorted(
                qualities,
                key=lambda x: int(''.join(filter(str.isdigit, x))) if any(c.isdigit() for c in x) else 0,
                reverse=True
            )
            
            quality_list = ["Todas"] + sorted_qualities
            self.quality_combo.configure(values=quality_list, state="normal")
            self.quality_var.set("Todas")
            
            self.add_log(f"🎬 Calidades disponibles: {', '.join(sorted_qualities)}")
        else:
            self.quality_combo.configure(values=["Todas"], state="normal")
            self.add_log("⚠️ No se encontraron calidades específicas")
    
    def start_download(self):
        """Iniciar descarga de archivos"""
        if not self.program_info:
            messagebox.showwarning("Advertencia", "Primero busca un programa")
            return
        
        if not os.path.exists("links-fitxers.csv"):
            response = messagebox.askyesno(
                "Lista no encontrada",
                "No se encontró la lista de archivos. ¿Quieres generarla primero?"
            )
            if response:
                self.generate_and_download()
            return
        
        self.is_downloading = True
        self.disable_controls()
        self.add_log("⬇️ Iniciando descarga...")
        self.progress_bar.set(0)
        self.progress_info.configure(text="Estado: Descargando...")
        
        def download_thread():
            try:
                output_folder = self.output_entry.get()
                workers = self.workers_var.get()
                use_aria2 = self.aria2_var.get()
                resume = self.resume_var.get()
                
                # Cargar manifest para saber total de archivos
                with open("manifest.json", "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                total_files = len(manifest.get("items", []))
                
                self.log_queue.put(("log", f"📦 Total archivos a descargar: {total_files}"))
                
                # Usar función personalizada con progreso
                self.download_from_csv_with_progress(
                    "links-fitxers.csv",
                    self.program_info.get("titol"),
                    total_files,
                    videos_folder=output_folder,
                    max_workers=workers,
                    use_aria2=use_aria2,
                    resume=resume
                )
                
                self.progress_queue.put({"type": "complete", "text": ""})
                self.log_queue.put(("log", "🎉 ¡Descarga completada!"))
                
            except Exception as e:
                self.log_queue.put(("log", f"❌ Error en descarga: {str(e)}"))
                self.progress_queue.put({"type": "error", "text": str(e)})
            finally:
                self.is_downloading = False
                self.after(0, self.enable_controls)
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    def download_from_csv_with_progress(self, csv_path, program_name, total_files, videos_folder="downloads", 
                                        subtitols_folder="downloads", max_workers=6, use_aria2=False, resume=True):
        """
        Versión personalizada de download_from_csv con actualizaciones de progreso para la GUI
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
        tasks = []
        for row in rows:
            link = row["Link"].strip()
            fname = row["File Name"].strip()
            program = safe_filename(row["Program"])
            folder = os.path.join(base_folder, program)
            ensure_folder(folder)
            final_name = f"{row['Name']}.{fname.split('.')[-1]}"
            dst = os.path.join(folder, safe_filename(final_name))
            tmp = dst + ".part"

            # Resume-only mode
            if resume:
                if not os.path.exists(tmp):
                    logger.debug("Skipping %s: no existe %s (resume-only)", dst, os.path.basename(tmp))
                    continue
                method_use_aria2 = False
            else:
                if os.path.exists(dst):
                    logger.info("Skip %s, ya existe", dst)
                    continue
                method_use_aria2 = bool(use_aria2)

            desc_name = os.path.basename(dst)
            tasks.append({"link": link, "dst": dst, "desc": desc_name, "use_aria2": method_use_aria2})

        if not tasks:
            logger.info("No hay tareas para procesar")
            self.log_queue.put(("log", "ℹ️ No hay archivos pendientes de descarga"))
            return

        logger.info("Tareas a ejecutar: %s", len(tasks))
        total_tasks = len(tasks)
        completed_tasks = 0

        # Ejecutar descargas paralelas con actualización de progreso
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {}
            for t in tasks:
                if t["use_aria2"]:
                    fut = ex.submit(download_with_aria2, t["link"], t["dst"])
                else:
                    fut = ex.submit(download_chunked, t["link"], t["dst"], t["desc"], 4, 30, not resume)
                futures[fut] = t["dst"]

            for future in as_completed(futures):
                dst = futures[future]
                try:
                    res = future.result()
                    if res:
                        logger.debug("Guardado: %s", res)
                        completed_tasks += 1
                        
                        # Actualizar progreso en GUI
                        progress_value = completed_tasks / total_tasks
                        self.progress_queue.put({
                            "type": "progress",
                            "value": progress_value
                        })
                        self.progress_queue.put({
                            "type": "info",
                            "text": f"Descargando: {completed_tasks}/{total_tasks} archivos ({int(progress_value * 100)}%)"
                        })
                        
                        # Log cada 5 archivos o al completar
                        if completed_tasks % 5 == 0 or completed_tasks == total_tasks:
                            self.log_queue.put(("log", f"📥 Progreso: {completed_tasks}/{total_tasks} archivos descargados"))
                    else:
                        logger.warning("No guardado: %s", dst)
                        self.log_queue.put(("log", f"⚠️ Fallo al descargar: {os.path.basename(dst)}"))
                except Exception as e:
                    logger.error("Error en descarga: %s (%s)", dst, e)
                    self.log_queue.put(("log", f"❌ Error: {os.path.basename(dst)} - {str(e)}"))

        logger.info("Descargas finalizadas.")

        # Estadísticas finales
        total_downloaded = sum(1 for t in tasks if os.path.exists(t["dst"]))
        total_failed = total_tasks - total_downloaded
        size_bytes = sum(os.path.getsize(t["dst"]) for t in tasks if os.path.exists(t["dst"]))
        size_mb = size_bytes / (1024*1024)

        self.log_queue.put(("log", "===== Estadísticas finales ====="))
        self.log_queue.put(("log", f"Total archivos intentados: {total_tasks}"))
        self.log_queue.put(("log", f"Archivos descargados: {total_downloaded}"))
        self.log_queue.put(("log", f"Archivos fallidos: {total_failed}"))
        self.log_queue.put(("log", f"Tamaño total: {size_mb:.2f} MB"))
        self.log_queue.put(("log", "================================"))
    
    def generate_and_download(self):
        """Generar lista y luego descargar"""
        self.disable_controls()
        
        def full_process():
            try:
                # Primero generar
                program_id = self.program_info.get("id")
                workers = self.workers_var.get()
                quality = self.quality_var.get()
                include_vtt = self.vtt_var.get()
                
                quality_filter = "" if quality == "Todas" else quality
                
                self.log_queue.put(("log", "🔄 Paso 1/2: Generando lista..."))
                cids = obtener_ids_capitulos(program_id, items_pagina=100, workers=workers)
                
                csv_path, manifest_path, total = build_links_csv(
                    cids,
                    output_csv="links-fitxers.csv",
                    manifest_path="manifest.json",
                    workers=workers,
                    include_vtt=include_vtt,
                    quality_filter=quality_filter
                )
                
                self.log_queue.put(("log", "✅ Lista generada correctamente"))
                self.log_queue.put(("log", "🔄 Paso 2/2: Descargando archivos..."))
                
                # Extraer calidades antes de descargar
                self.extract_available_qualities(manifest_path)
                
                # Luego descargar
                output_folder = self.output_entry.get()
                use_aria2 = self.aria2_var.get()
                resume = self.resume_var.get()
                
                self.download_from_csv_with_progress(
                    csv_path,
                    self.program_info.get("titol"),
                    total,
                    videos_folder=output_folder,
                    max_workers=workers,
                    use_aria2=use_aria2,
                    resume=resume
                )
                
                self.progress_queue.put({"type": "complete", "text": ""})
                self.log_queue.put(("log", "🎉 ¡Proceso completo finalizado!"))
                
            except Exception as e:
                self.log_queue.put(("log", f"❌ Error: {str(e)}"))
                self.progress_queue.put({"type": "error", "text": str(e)})
            finally:
                self.after(0, self.enable_controls)
        
        threading.Thread(target=full_process, daemon=True).start()


def main():
    """Función principal"""
    app = TV3_GUI()
    app.mainloop()


if __name__ == "__main__":
    main()
