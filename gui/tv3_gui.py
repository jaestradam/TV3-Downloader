#!/usr/bin/env python3
"""
tv3_gui.py - Interfaz gráfica para TV3 GUI Downloader
Requiere: customtkinter, pillow
Instalación: pip install customtkinter pillow

Comunicación con tv3_cli.py mediante subprocess (CLI)
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import threading
import queue
import sys
import os
from datetime import datetime
import json
import subprocess
import re

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
        
        # Variables
        self.program_info = None
        self.is_processing = False
        self.process_thread = None
        self.available_qualities = set()
        self.current_process = None
        
        # Verificar que tv3_cli.py existe
        if not os.path.exists("tv3_cli.py"):
            messagebox.showerror(
                "Error",
                "No se encuentra tv3_cli.py en el directorio actual.\n"
                "Asegúrate de que ambos archivos están en el mismo directorio."
            )
            sys.exit(1)
        
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
                    self.is_processing = False
                    self.enable_controls()
                
                elif progress_data["type"] == "error":
                    self.progress_info.configure(text=f"❌ Error: {progress_data['text']}")
                    self.is_processing = False
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
    
    def run_tv3_command(self, args):
        """Ejecutar comando tv3_cli.py mediante subprocess"""
        cmd = [sys.executable, "tv3_cli.py"] + args
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
    
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
                # Ejecutar con --only-list para solo validar el programa
                process = self.run_tv3_command([program_name, "--only-list"])
                
                program_found = False
                program_id = None
                program_title = None
                
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self.log_queue.put(("log", line))
                        
                        # Buscar info del programa en la salida
                        if "Programa:" in line:
                            # Formato: "Programa: Título  id=123"
                            match = re.search(r'Programa:\s*(.+?)\s+id=(\d+)', line)
                            if match:
                                program_title = match.group(1).strip()
                                program_id = match.group(2).strip()
                                program_found = True
                
                process.wait()
                
                if program_found and program_id:
                    self.program_info = {
                        "id": program_id,
                        "titol": program_title,
                        "nombonic": program_name
                    }
                    
                    self.log_queue.put(("log", f"✅ Programa encontrado: {program_title}"))
                    
                    self.after(0, lambda: self.info_label.configure(
                        text=f"📺 {program_title} (ID: {program_id})",
                        text_color=("green", "lightgreen")
                    ))
                else:
                    self.log_queue.put(("log", "❌ Programa no encontrado"))
                    self.program_info = None
                    self.after(0, lambda: self.info_label.configure(
                        text="❌ Programa no encontrado",
                        text_color=("red", "lightcoral")
                    ))
                
            except Exception as e:
                self.log_queue.put(("log", f"❌ Error: {str(e)}"))
                self.program_info = None
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
        self.progress_bar.set(0)
        
        def generate_thread():
            try:
                program_name = self.program_info.get("nombonic")
                workers = str(self.workers_var.get())
                quality = self.quality_var.get()
                
                # Construir argumentos
                args = [
                    program_name,
                    "--only-list",
                    "--workers", workers
                ]
                
                if quality != "Todas":
                    args.extend(["--quality", quality])
                
                if not self.vtt_var.get():
                    args.append("--no-vtt")
                
                # Ejecutar proceso
                process = self.run_tv3_command(args)
                
                total_chapters = 0
                total_files = 0
                
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self.log_queue.put(("log", line))
                        
                        # Detectar progreso
                        if "Total capítulos:" in line or "Total capítulos encontrados:" in line:
                            match = re.search(r'(\d+)', line)
                            if match:
                                total_chapters = int(match.group(1))
                        
                        if "CSV generado:" in line or "filas:" in line:
                            match = re.search(r'filas:\s*(\d+)', line)
                            if match:
                                total_files = int(match.group(1))
                
                process.wait()
                
                if process.returncode == 0:
                    self.log_queue.put(("log", "✅ Lista generada correctamente"))
                    self.progress_queue.put({
                        "type": "info",
                        "text": f"✅ Lista generada: {total_files} archivos"
                    })
                    
                    # Extraer calidades disponibles
                    self.extract_available_qualities("manifest.json")
                else:
                    self.log_queue.put(("log", "❌ Error generando lista"))
                    self.progress_queue.put({"type": "error", "text": "Error generando lista"})
                
            except Exception as e:
                self.log_queue.put(("log", f"❌ Error: {str(e)}"))
                self.progress_queue.put({"type": "error", "text": str(e)})
            finally:
                self.after(0, self.enable_controls)
        
        threading.Thread(target=generate_thread, daemon=True).start()
    
    def extract_available_qualities(self, manifest_path):
        """Extraer calidades disponibles del manifest y actualizar el combobox"""
        try:
            if not os.path.exists(manifest_path):
                return
            
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
        
        self.is_processing = True
        self.disable_controls()
        self.add_log("⬇️ Iniciando descarga...")
        self.progress_bar.set(0)
        self.progress_info.configure(text="Estado: Descargando...")
        
        def download_thread():
            try:
                program_name = self.program_info.get("nombonic")
                output_folder = self.output_entry.get()
                workers = str(self.workers_var.get())
                quality = self.quality_var.get()
                
                # Construir argumentos
                args = [
                    program_name,
                    "--workers", workers,
                    "--output", output_folder
                ]
                
                if quality != "Todas":
                    args.extend(["--quality", quality])
                
                if not self.vtt_var.get():
                    args.append("--no-vtt")
                
                if self.aria2_var.get():
                    args.append("--aria2")
                
                if self.resume_var.get():
                    args.append("--resume")
                
                # Cargar manifest para calcular progreso
                total_files = 0
                if os.path.exists("manifest.json"):
                    with open("manifest.json", "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                        total_files = len(manifest.get("items", []))
                
                self.log_queue.put(("log", f"📦 Total archivos en manifest: {total_files}"))
                
                # Ejecutar proceso
                process = self.run_tv3_command(args)
                
                downloaded_count = 0
                
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self.log_queue.put(("log", line))
                        
                        # Detectar archivos completados
                        if "Guardado:" in line or "descargados correctamente:" in line:
                            match = re.search(r'descargados correctamente:\s*(\d+)', line)
                            if match:
                                downloaded_count = int(match.group(1))
                            else:
                                downloaded_count += 1
                            
                            if total_files > 0:
                                progress = downloaded_count / total_files
                                self.progress_queue.put({
                                    "type": "progress",
                                    "value": min(progress, 0.99)
                                })
                                self.progress_queue.put({
                                    "type": "info",
                                    "text": f"Descargando: {downloaded_count}/{total_files} archivos ({int(progress * 100)}%)"
                                })
                
                process.wait()
                
                if process.returncode == 0:
                    self.progress_queue.put({"type": "complete", "text": ""})
                    self.log_queue.put(("log", "🎉 ¡Descarga completada!"))
                else:
                    self.progress_queue.put({"type": "error", "text": "Error en descarga"})
                
            except Exception as e:
                self.log_queue.put(("log", f"❌ Error en descarga: {str(e)}"))
                self.progress_queue.put({"type": "error", "text": str(e)})
            finally:
                self.is_processing = False
                self.after(0, self.enable_controls)
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    def generate_and_download(self):
        """Generar lista y luego descargar"""
        self.disable_controls()
        self.progress_bar.set(0)
        
        def full_process():
            try:
                program_name = self.program_info.get("nombonic")
                output_folder = self.output_entry.get()
                workers = str(self.workers_var.get())
                quality = self.quality_var.get()
                
                # Construir argumentos
                args = [
                    program_name,
                    "--workers", workers,
                    "--output", output_folder
                ]
                
                if quality != "Todas":
                    args.extend(["--quality", quality])
                
                if not self.vtt_var.get():
                    args.append("--no-vtt")
                
                if self.aria2_var.get():
                    args.append("--aria2")
                
                if self.resume_var.get():
                    args.append("--resume")
                
                self.log_queue.put(("log", "🔄 Generando lista y descargando..."))
                self.progress_queue.put({"type": "info", "text": "Estado: Generando lista..."})
                
                # Ejecutar proceso completo
                process = self.run_tv3_command(args)
                
                total_files = 0
                downloaded_count = 0
                generating = True
                
                for line in process.stdout:
                    line = line.strip()
                    if line:
                        self.log_queue.put(("log", line))
                        
                        # Detectar fase de generación completada
                        if "CSV generado:" in line or "Iniciando descargas:" in line:
                            generating = False
                            self.progress_queue.put({"type": "info", "text": "Estado: Descargando..."})
                        
                        # Extraer total de archivos
                        if "Iniciando descargas:" in line or "archivos (manifiesto)" in line:
                            match = re.search(r'(\d+)\s+archivos', line)
                            if match:
                                total_files = int(match.group(1))
                        
                        # Detectar progreso de descarga
                        if not generating and ("Guardado:" in line or "descargados correctamente:" in line):
                            match = re.search(r'descargados correctamente:\s*(\d+)', line)
                            if match:
                                downloaded_count = int(match.group(1))
                            else:
                                downloaded_count += 1
                            
                            if total_files > 0:
                                progress = downloaded_count / total_files
                                self.progress_queue.put({
                                    "type": "progress",
                                    "value": min(progress, 0.99)
                                })
                                self.progress_queue.put({
                                    "type": "info",
                                    "text": f"Descargando: {downloaded_count}/{total_files} archivos ({int(progress * 100)}%)"
                                })
                
                process.wait()
                
                # Extraer calidades si se generó la lista
                if os.path.exists("manifest.json"):
                    self.extract_available_qualities("manifest.json")
                
                if process.returncode == 0:
                    self.progress_queue.put({"type": "complete", "text": ""})
                    self.log_queue.put(("log", "🎉 ¡Proceso completo finalizado!"))
                else:
                    self.progress_queue.put({"type": "error", "text": "Error en el proceso"})
                
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
