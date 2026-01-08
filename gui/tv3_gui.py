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
import re
import time
import os
from datetime import datetime
import json
import csv
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# Importar el script original (asumiendo que está en el mismo directorio)
try:
    from tv3_cli import (
        logger,
        SESSION
    )
except ImportError:
    print("Error: No se puede importar tv3_cli.py")
    print("Asegúrate de que tv3_cli.py está en el mismo directorio")
    sys.exit(1)

# Configuración de CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class TV3_GUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Configuración de la ventana
        self.title("TV3 GUI Downloader")
        self.geometry("900x750")
        
        # Queue para comunicación entre threads
        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.file_progress_queue = queue.Queue()
        
        # Variables
        self.program_info = None
        self.is_downloading = False
        self.download_thread = None
        self.available_qualities = set()
        self.active_downloads = {}  # {filename: progress_bar_widget}
        
        # Crear interfaz
        self.create_widgets()
        
        # Iniciar actualización de logs y progreso
        self.update_logs()
        self.update_progress()
        self.update_file_progress()
        
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
            state="disabled"
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
        
        # Barra de progreso global
        self.progress_bar = ctk.CTkProgressBar(progress_frame)
        self.progress_bar.pack(fill="x", padx=15, pady=5)
        self.progress_bar.set(0)
        
        # Info de progreso global
        self.progress_info = ctk.CTkLabel(
            progress_frame,
            text="Estado: Esperando...",
            anchor="w"
        )
        self.progress_info.pack(fill="x", padx=15, pady=(5, 10))
        
        # Separador
        separator = ctk.CTkFrame(progress_frame, height=2, fg_color=("gray70", "gray30"))
        separator.pack(fill="x", padx=15, pady=5)
        
        # Label para descargas activas
        active_label = ctk.CTkLabel(
            progress_frame,
            text="⚡ Descargas activas",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        active_label.pack(anchor="w", padx=15, pady=(10, 5))
        
        # Frame scrollable para barras de progreso individuales
        self.downloads_frame = ctk.CTkScrollableFrame(
            progress_frame,
            height=120,
            fg_color=("gray95", "gray15")
        )
        self.downloads_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        # Placeholder cuando no hay descargas
        self.no_downloads_label = ctk.CTkLabel(
            self.downloads_frame,
            text="No hay descargas activas",
            text_color=("gray50", "gray60")
        )
        self.no_downloads_label.pack(pady=20)
        
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
                    self.clear_active_downloads()
                    self.enable_controls()
                
                elif progress_data["type"] == "error":
                    self.progress_info.configure(text=f"❌ Error: {progress_data['text']}")
                    self.is_downloading = False
                    self.clear_active_downloads()
                    self.enable_controls()
        
        except queue.Empty:
            pass
        
        self.after(100, self.update_progress)
    
    def update_file_progress(self):
        """Actualizar barras de progreso individuales de archivos"""
        try:
            while True:
                file_data = self.file_progress_queue.get_nowait()
                
                if file_data["type"] == "start":
                    # Iniciar nueva descarga
                    filename = file_data["filename"]
                    self.add_active_download(filename)
                
                elif file_data["type"] == "update":
                    # Actualizar progreso de descarga
                    filename = file_data["filename"]
                    progress = file_data["progress"]
                    self.update_active_download(filename, progress)
                
                elif file_data["type"] == "complete":
                    # Completar descarga
                    filename = file_data["filename"]
                    self.remove_active_download(filename)
                
                elif file_data["type"] == "error":
                    # Error en descarga
                    filename = file_data["filename"]
                    self.remove_active_download(filename, error=True)
        
        except queue.Empty:
            pass
        
        self.after(50, self.update_file_progress)
    
    def add_active_download(self, filename):
        """Añadir una nueva barra de progreso para un archivo"""
        if filename in self.active_downloads:
            return
        
        # Ocultar placeholder si existe
        if self.no_downloads_label.winfo_exists():
            self.no_downloads_label.pack_forget()
        
        # Crear frame para este archivo
        file_frame = ctk.CTkFrame(self.downloads_frame, fg_color="transparent")
        file_frame.pack(fill="x", padx=5, pady=5)
        
        # Label con nombre del archivo (truncado si es muy largo)
        display_name = filename if len(filename) <= 50 else filename[:47] + "..."
        name_label = ctk.CTkLabel(
            file_frame,
            text=f"📥 {display_name}",
            anchor="w",
            font=ctk.CTkFont(size=11)
        )
        name_label.pack(fill="x")
        
        # Barra de progreso
        progress_bar = ctk.CTkProgressBar(file_frame, height=8)
        progress_bar.pack(fill="x", pady=(2, 0))
        progress_bar.set(0)
        
        # Guardar referencias
        self.active_downloads[filename] = {
            "frame": file_frame,
            "label": name_label,
            "bar": progress_bar
        }
    
    def update_active_download(self, filename, progress):
        """Actualizar el progreso de un archivo específico"""
        if filename in self.active_downloads:
            bar = self.active_downloads[filename]["bar"]
            bar.set(progress)
    
    def remove_active_download(self, filename, error=False):
        """Eliminar la barra de progreso de un archivo completado"""
        if filename in self.active_downloads:
            frame = self.active_downloads[filename]["frame"]
            frame.destroy()
            del self.active_downloads[filename]
        
        # Mostrar placeholder si no hay más descargas
        if len(self.active_downloads) == 0:
            self.no_downloads_label.pack(pady=20)
    
    def clear_active_downloads(self):
        """Limpiar todas las barras de progreso activas"""
        for filename in list(self.active_downloads.keys()):
            self.remove_active_download(filename)
    
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
            self.after(0, self.update_quality_selector, qualities)
            
        except Exception as e:
            self.log_queue.put(("log", f"⚠️ No se pudieron extraer las calidades: {str(e)}"))
    
    def update_quality_selector(self, qualities):
        """Actualizar el selector de calidad con las opciones disponibles"""
        if qualities:
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
                
                with open("manifest.json", "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                total_files = len(manifest.get("items", []))
                
                self.log_queue.put(("log", f"📦 Total archivos a descargar: {total_files}"))
                
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
                    fut = ex.submit(
                        download_chunked_with_callback,
                        t["link"],
                        t["dst"],
                        t["desc"],
                        4,
                        30,
                        not resume,
                        self.file_progress_queue
                    )
                futures[fut] = t

            for future in as_completed(futures):
                task = futures[future]
                dst = task["dst"]
                filename = task["desc"]
                
                try:
                    res = future.result()
                    if res:
                        logger.debug("Guardado: %s", res)
                        completed_tasks += 1
                        
                        # Log en tiempo real
                        self.log_queue.put(("log", f"✅ Descargado: {filename}"))
                        
                        # Actualizar progreso global en GUI
                        progress_value = completed_tasks / total_tasks
                        self.progress_queue.put({
                            "type": "progress",
                            "value": progress_value
                        })
                        self.progress_queue.put({
                            "type": "info",
                            "text": f"Descargando: {completed_tasks}/{total_tasks} archivos ({int(progress_value * 100)}%)"
                        })
                    else:
                        logger.warning("No guardado: %s", dst)
                        self.log_queue.put(("log", f"⚠️ Fallo al descargar: {filename}"))
                except Exception as e:
                    logger.error("Error en descarga: %s (%s)", dst, e)
                    self.log_queue.put(("log", f"❌ Error: {filename} - {str(e)}"))

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
                
                self.extract_available_qualities(manifest_path)
                
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


# ----------------------------
# Utilities (fuera de la clase)
# ----------------------------
def ensure_folder(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def safe_filename(name):
    name = re.sub(r'[\\/:"*?<>|]+', '-', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def fetch_json(url, params=None, timeout=20):
    r = SESSION.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()

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
                tcap_local = [i["capitol_temporada"] for i in item_list if "capitol_temporada" in i]
                return ids_local, tcap_local
            except Exception as e:
                logger.debug("fetch_page(%s) error (attempt %s): %s", page, attempts, e)
                time.sleep(1 * attempts)
        logger.error("Página %s falló tras %s intentos", page, max_retries)
        return [], []

    all_ids = []
    all_tcaps = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_page, p): p for p in range(1, pags+1)}
        for future in as_completed(futures):
            page = futures[future]
            try:
                ids, tcaps = future.result()
                logger.info("Página %s -> %s ids", page, len(ids))
                all_ids.extend(ids)
                all_tcaps.extend(tcaps)
            except Exception as e:
                logger.error("Error página %s: %s", page, e)

    logger.info("Total capítulos: %s", len(all_ids))
    return [{"id": id, "tcap": tcap} for id, tcap in zip(all_ids, all_tcaps)]

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
        info["temporada"] = data.get("informacio", {}).get("temporada", {}).get("idName", "0")[7:] or "0"
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

def build_links_csv(cids, output_csv="links-fitxers.csv", manifest_path="manifest.json", workers=8, retry_failed=2, include_vtt=True, quality_filter=""):
    ensure_folder("cache")
    rows = []
    failed = []

    def worker(cid):
        attempts = 0
        while attempts <= retry_failed:
            attempts += 1
            res = api_extract_media_urls(cid["id"])
            if res:
                break
            logger.warning("Retry media id=%s attempt=%s", cid["id"], attempts)
            time.sleep(1 * attempts)
        if not res:
            failed.append(cid)
            return []
        program = safe_filename(res["programa"])
        title = safe_filename(res["title"])
        safe_title = safe_filename(res["title"]).split("-", 1)[1].strip() if "-" in safe_filename(res["title"]) else safe_filename(res["title"])
        capitol = res.get("capitol", str(res["id"]))
        temporada = res.get("temporada")
        tcap = cid["tcap"]
        safe_name = f"{program} - {int(temporada)}x{int(tcap):02d} - {safe_title}"
        local = []
        for mp in res["mp4s"]:
            if quality_filter and quality_filter not in mp["label"]:
                continue
            fname = mp["url"].split("/")[-1]
            local.append([capitol, program, temporada, tcap, title, safe_name, mp["label"], mp["url"], fname, "mp4"])
        if include_vtt:
            for vt in res["vtts"]:
                fname = vt["url"].split("/")[-1]
                local.append([capitol, program, temporada, tcap, title, safe_name, vt["label"], vt["url"], fname, "vtt"])
        return local

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(worker, cid): cid for cid in cids}
        with tqdm(total=len(futures), desc="Extrayendo capítulos", unit="cap", disable=not sys.stdout.isatty()) as p:
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

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Capitol", "Program", "Temporada", "TempCap", "Title", "Name", "Quality", "Link", "File Name", "Type"])
        writer.writerows(rows_sorted)

    manifest = {"generated_at": time.time(), "items": []}
    for r in rows_sorted:
        manifest["items"].append({
            "capitol": r[0],
            "program": r[1],
            "temporada": r[2],
            "temporada_capitol": r[3],
            "title": r[4],
            "name": r[5],
            "quality": r[6],
            "link": r[7],
            "file_name": r[8],
            "type": r[9]
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
                if "Range" in headers:
                    if r.status_code == 206:
                        mode = "ab"
                    elif r.status_code == 416:
                        os.replace(tmp, dst)
                        return dst
                    else:
                        logger.warning("Servidor ignoró Range para %s, reiniciando descarga", dst)
                        existing = 0
                        headers.pop("Range", None)
                        mode = "wb"
                else:
                    mode = "wb"

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
                    mininterval=0.1,
                    disable=not sys.stdout.isatty()
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

def download_chunked_with_callback(url, dst, desc_name, max_retries=4, timeout=30, use_range=True, progress_queue=None):
    """Versión de download_chunked que reporta progreso a la GUI"""
    ensure_folder(os.path.dirname(dst))
    tmp = dst + ".part"
    existing = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    headers = {}
    
    filename = os.path.basename(dst)

    if use_range and existing > 0:
        headers["Range"] = f"bytes={existing}-"

    backoff = 1
    last_exc = None
    
    # Notificar inicio de descarga
    if progress_queue:
        progress_queue.put({"type": "start", "filename": filename})

    for attempt in range(1, max_retries + 1):
        try:
            with SESSION.get(url, stream=True, timeout=timeout, headers=headers) as r:
                if "Range" in headers:
                    if r.status_code == 206:
                        mode = "ab"
                    elif r.status_code == 416:
                        os.replace(tmp, dst)
                        if progress_queue:
                            progress_queue.put({"type": "complete", "filename": filename})
                        return dst
                    else:
                        logger.warning("Servidor ignoró Range para %s, reiniciando descarga", dst)
                        existing = 0
                        headers.pop("Range", None)
                        mode = "wb"
                else:
                    mode = "wb"

                r.raise_for_status()

                total = r.headers.get("Content-Length")
                total = int(total) if total else None
                total_bytes = (existing + total) if total and mode == "ab" else total
                
                downloaded = existing if mode == "ab" else 0

                with open(tmp, mode) as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Actualizar progreso cada cierto número de chunks
                            if total_bytes and progress_queue:
                                progress = downloaded / total_bytes
                                progress_queue.put({
                                    "type": "update",
                                    "filename": filename,
                                    "progress": progress
                                })

                os.replace(tmp, dst)
                
                # Notificar completado
                if progress_queue:
                    progress_queue.put({"type": "complete", "filename": filename})
                
                return dst

        except Exception as e:
            last_exc = e
            logger.debug("download attempt %s failed for %s: %s", attempt, url, e)
            time.sleep(backoff)
            backoff *= 2

    logger.error("Failed download %s after %s attempts: %s", url, max_retries, last_exc)
    
    # Notificar error
    if progress_queue:
        progress_queue.put({"type": "error", "filename": filename})
    
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


def main():
    """Función principal"""
    app = TV3_GUI()
    app.mainloop()


if __name__ == "__main__":
    main()