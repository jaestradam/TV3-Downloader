#!/usr/bin/env python3
"""
tv3_gui.py - Interfaz gráfica para TV3 GUI Downloader
Versión con Vista Previa de Manifest
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
import tkinter as tk
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
# Config / Logging
# ----------------------------
LOGFILE = "tv3_gui_debug.log"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("TV3")
file_handler = logging.FileHandler(LOGFILE, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
logger.addHandler(file_handler)

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

def resource_path(relative):
    try:
        base_path = sys._MEIPASS   # PyInstaller
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative)

class QueueLogHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        msg = self.format(record)
        self.log_queue.put(("log", msg))

# Configuración de CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class CTkToolTip:
    def __init__(self, widget, text, delay=400, wrap=260):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wrap = wrap
        self.tipwindow = None
        self.id = None

        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, event=None):
        self.id = self.widget.after(self.delay, self._show)

    def _show(self):
        if self.tipwindow or not self.text:
            return

        tw = self.tipwindow = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)

        frame = ctk.CTkFrame(tw, corner_radius=8)
        frame.pack()

        label = ctk.CTkLabel(
            frame,
            text=self.text,
            justify="left",
            wraplength=self.wrap,
            font=ctk.CTkFont(size=12)
        )
        label.pack(padx=10, pady=6)

        tw.update_idletasks()

        tip_w = tw.winfo_width()
        tip_h = tw.winfo_height()

        wx = self.widget.winfo_rootx()
        wy = self.widget.winfo_rooty()
        ww = self.widget.winfo_width()
        wh = self.widget.winfo_height()

        screen_w = tw.winfo_screenwidth()
        screen_h = tw.winfo_screenheight()

        x = wx + ww + 10
        y = wy + (wh // 2) - (tip_h // 3)

        if x + tip_w > screen_w:
            x = wx - tip_w - 10

        if y < 0:
            y = 10

        if y + tip_h > screen_h:
            y = screen_h - tip_h - 10

        tw.geometry(f"+{x}+{y}")

    def _hide(self, event=None):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None
        if self.tipwindow:
            self.tipwindow.destroy()
            self.tipwindow = None

class DownloadStatsPopup(ctk.CTkToplevel):
    """Ventana popup para mostrar estadísticas de descarga"""
    
    def __init__(self, parent, stats):
        super().__init__(parent)
        
        self.title("📊 Estadísticas de Descarga")
        self.geometry("500x650")  # ← Aumentado de 600 a 650
        self.resizable(False, False)
        
        # Centrar en la pantalla
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.winfo_screenheight() // 2) - (650 // 2)  # ← Actualizado
        self.geometry(f"+{x}+{y}")
        
        # Hacer modal
        self.transient(parent)
        self.grab_set()
        
        # Configurar contenido
        self.create_widgets(stats)
        
        # Foco
        self.focus()
    
    def create_widgets(self, stats):
        """Crear widgets del popup"""
        # Frame principal con padding
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # ===== HEADER =====
        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 15))
        
        # Determinar emoji según resultado
        if stats['failed'] == 0 and stats['completed'] > 0:
            emoji = "🎉"
            title_text = "¡Descarga Completada!"
            title_color = ("green", "lightgreen")
        elif stats['failed'] > 0 and stats['completed'] > 0:
            emoji = "⚠️"
            title_text = "Descarga Completada con Errores"
            title_color = ("orange", "yellow")
        elif stats['failed'] > 0 and stats['completed'] == 0:
            emoji = "❌"
            title_text = "Descarga Fallida"
            title_color = ("red", "lightcoral")
        else:
            emoji = "ℹ️"
            title_text = "Proceso Finalizado"
            title_color = ("gray", "lightgray")
        
        title_label = ctk.CTkLabel(
            header_frame,
            text=f"{emoji} {title_text}",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=title_color
        )
        title_label.pack()
        
        # Separador
        separator1 = ctk.CTkFrame(main_frame, height=2, fg_color=("gray70", "gray30"))
        separator1.pack(fill="x", pady=(0, 15))
        
        # ===== ESTADÍSTICAS PRINCIPALES =====
        stats_frame = ctk.CTkFrame(main_frame, corner_radius=10, fg_color=("gray90", "gray17"))
        stats_frame.pack(fill="x", pady=(0, 15))
        
        # Grid de estadísticas
        stats_grid = ctk.CTkFrame(stats_frame, fg_color="transparent")
        stats_grid.pack(fill="x", padx=20, pady=20)
        
        # Función helper para crear stat box
        def create_stat_box(parent, row, col, icon, label, value, color):
            box = ctk.CTkFrame(parent, fg_color="transparent")
            box.grid(row=row, column=col, padx=10, pady=10, sticky="ew")
            
            icon_label = ctk.CTkLabel(box, text=icon, font=ctk.CTkFont(size=32))
            icon_label.pack()
            
            value_label = ctk.CTkLabel(
                box,
                text=str(value),
                font=ctk.CTkFont(size=28, weight="bold"),
                text_color=color
            )
            value_label.pack()
            
            label_text = ctk.CTkLabel(
                box,
                text=label,
                font=ctk.CTkFont(size=12),
                text_color=("gray50", "gray60")
            )
            label_text.pack()
        
        # Configurar grid
        stats_grid.grid_columnconfigure(0, weight=1)
        stats_grid.grid_columnconfigure(1, weight=1)
        
        # Estadísticas principales
        create_stat_box(stats_grid, 0, 0, "✅", "Completados", stats['completed'], ("green", "lightgreen"))
        create_stat_box(stats_grid, 0, 1, "❌", "Fallidos", stats['failed'], ("red", "lightcoral"))
        
        if stats.get('skipped', 0) > 0:
            create_stat_box(stats_grid, 1, 0, "⏭️", "Ya existían", stats['skipped'], ("blue", "lightblue"))
        
        create_stat_box(stats_grid, 1, 1, "💾", "Tamaño Total", stats['total_size'], ("purple", "violet"))
        
        # ===== DETALLES =====
        details_frame = ctk.CTkFrame(main_frame, corner_radius=10, fg_color=("gray90", "gray17"))
        details_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        details_label = ctk.CTkLabel(
            details_frame,
            text="📋 Detalles",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w"
        )
        details_label.pack(fill="x", padx=15, pady=(15, 10))
        
        # Lista de detalles
        details_text = ctk.CTkTextbox(
            details_frame,
            height=120,  # ← Reducido de 150 a 120
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word"
        )
        details_text.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        # Construir texto de detalles
        details_content = []
        details_content.append(f"🕐 Tiempo total: {stats['duration']}")
        details_content.append(f"📁 Carpeta: {stats['folder']}")
        
        if stats['completed'] > 0:
            details_content.append(f"\n✅ Archivos descargados correctamente: {stats['completed']}")
        
        if stats['failed'] > 0:
            details_content.append(f"\n❌ Archivos con errores: {stats['failed']}")
            if stats.get('failed_list'):
                details_content.append("\nArchivos fallidos:")
                for i, failed_file in enumerate(stats['failed_list'][:5], 1):
                    details_content.append(f"  {i}. {failed_file}")
                if len(stats['failed_list']) > 5:
                    details_content.append(f"  ... y {len(stats['failed_list']) - 5} más")
        
        if stats.get('skipped', 0) > 0:
            details_content.append(f"\n⏭️ Archivos que ya existían: {stats['skipped']}")
        
        details_text.insert("1.0", "\n".join(details_content))
        details_text.configure(state="disabled")
        
        # Separador
        separator2 = ctk.CTkFrame(main_frame, height=2, fg_color=("gray70", "gray30"))
        separator2.pack(fill="x", pady=(0, 15))
        
        # ===== BOTONES =====
        # Frame para botones con altura fija
        buttons_container = ctk.CTkFrame(main_frame, fg_color="transparent", height=45)
        buttons_container.pack(fill="x", pady=(0, 0))
        buttons_container.pack_propagate(False)  # ← IMPORTANTE: Evita que se colapse
        
        buttons_frame = ctk.CTkFrame(buttons_container, fg_color="transparent")
        buttons_frame.pack(fill="both", expand=True)
        
        # Botón para abrir carpeta
        open_folder_btn = ctk.CTkButton(
            buttons_frame,
            text="📂 Abrir Carpeta",
            command=lambda: self.open_folder(stats['folder']),
            height=40,
            font=ctk.CTkFont(size=13),
            fg_color=("peru", "chocolate"),
            hover_color=("chocolate", "peru")
        )
        open_folder_btn.pack(side="left", expand=True, fill="both", padx=(0, 5))
        
        # Botón cerrar
        close_btn = ctk.CTkButton(
            buttons_frame,
            text="✓ Cerrar",
            command=self.destroy,
            height=40,
            font=ctk.CTkFont(size=13),
            fg_color=("green", "darkgreen"),
            hover_color=("darkgreen", "green")
        )
        close_btn.pack(side="left", expand=True, fill="both", padx=(5, 0))
    
    def open_folder(self, folder_path):
        """Abrir la carpeta de descargas"""
        try:
            if os.path.exists(folder_path):
                if sys.platform == 'win32':
                    os.startfile(folder_path)
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', folder_path])
                else:
                    subprocess.Popen(['xdg-open', folder_path])
                # Cerrar el popup después de abrir la carpeta
                self.destroy()
            else:
                messagebox.showwarning(
                    "Carpeta no encontrada", 
                    f"La carpeta no existe:\n{folder_path}",
                    parent=self
                )
        except Exception as e:
            messagebox.showerror(
                "Error", 
                f"No se pudo abrir la carpeta:\n{str(e)}",
                parent=self
            )

class TV3_GUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.iconbitmap(resource_path("3catEM.ico"))

        # Configuración de la ventana
        self.title("TV3 GUI Downloader")
        self.geometry("1100x900")
        
        # Queue para comunicación entre threads
        self.log_queue = queue.Queue()
        self.progress_queue = queue.Queue()
        self.file_progress_queue = queue.Queue(maxsize=200)
        
        # Variables
        self.program_info = None
        self.manifest_data = None
        self.is_downloading = False
        self.download_thread = None
        self.available_qualities = set()
        self.active_downloads = {}
        
        # Variables para la tabla
        self.tree_items = {}  # {iid: item_data}
        self.all_items = []  # Lista completa de items sin filtrar
        self.sort_column = None
        self.sort_reverse = False
        
        # Crear interfaz
        self.create_widgets()
        
        # Redirigir stdout y stderr a la GUI
        sys.stdout = StdoutRedirector(self.log_queue)
        sys.stderr = StdoutRedirector(self.log_queue)
        
        # Iniciar actualización de logs y progreso
        self.update_logs()
        self.update_progress()
        self.update_file_progress()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
    def show_stats_popup(self, stats):
        """Mostrar popup con estadísticas de descarga"""
        try:
            popup = DownloadStatsPopup(self, stats)
            popup.focus()
        except Exception as e:
            logger.error(f"Error mostrando popup de estadísticas: {e}")
            # Fallback a messagebox simple
            message = (
                f"✅ Descargados: {stats['completed']}\n"
                f"❌ Fallidos: {stats['failed']}\n"
                f"💾 Tamaño: {stats['total_size']}\n"
                f"🕐 Tiempo: {stats['duration']}"
            )
            messagebox.showinfo("Descarga Completada", message)

    def on_closing(self):
        """Manejar el cierre de la ventana"""
        if self.is_downloading:
            result = messagebox.askyesno(
                "Descarga en curso",
                "Hay una descarga en curso. ¿Estás seguro de que quieres salir?\n\nLos archivos parciales se guardarán y podrás reanudar más tarde.",
                icon='warning'
            )
            if not result:
                return
    
        # Limpiar recursos
        try:
            SESSION.close()
        except:
            pass
    
        self.destroy()

    def create_widgets(self):
        # ===== 1. TOP HEADER (FIJO) =====
        self.top_header = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray90", "gray20"))
        self.top_header.pack(side="top", fill="x", padx=0, pady=0)
    
        title_label = ctk.CTkLabel(
            self.top_header,
            text="🎬 TV3 GUI Downloader",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(pady=15)

        help_btn = ctk.CTkButton(
            self.top_header,
            text="❓",
            width=30,
            height=30,
            corner_radius=15,
            command=self.show_help,
            #fg_color="blue",
            border_width=0
        )
        help_btn.pack(side="right", padx=15)

        self.status_bar = ctk.CTkFrame(self, height=25, corner_radius=0, fg_color=("gray80", "gray25"))
        self.status_bar.pack(side="bottom", fill="x")

        self.status_label = ctk.CTkLabel(
            self.status_bar,
            text="📊 Listo | 0 archivos | 0 B",
            font=ctk.CTkFont(size=11),
            anchor="w"
        )
        self.status_label.pack(side="left", padx=10)

        self.version_label = ctk.CTkLabel(
            self.status_bar,
            text="v1.0 GUI",
            font=ctk.CTkFont(size=10),
            text_color=("gray50", "gray60")
        )
        self.version_label.pack(side="right", padx=10)

        # ===== 2. CENTER BODY (SCROLLABLE) - AHORA INCLUYE TODO =====
#        self.main_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.main_scroll = ctk.CTkFrame(self, fg_color="transparent")

        self.main_scroll.pack(side="top", fill="both", expand=True, padx=0, pady=0)
    
        # Frame interno para márgenes
        content_frame = ctk.CTkFrame(self.main_scroll, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # TABS - AHORA CON 4 PESTAÑAS
        self.tabs = ctk.CTkTabview(
            content_frame,
            width=1000,
            height=600
        )
        self.tabs.pack(fill="both", expand=True)

        tab_config = self.tabs.add("⚙️ Configuración")
        tab_preview = self.tabs.add("📋 Lista capítulos a descargar")
        tab_progress = self.tabs.add("📊 Progreso")  # ← NUEVA PESTAÑA
        tab_logs = self.tabs.add("📜 Logs")

        # ========================================
        # TAB 1: CONFIGURACIÓN
        # ========================================
        config_frame = ctk.CTkFrame(tab_config, corner_radius=10)
        config_frame.pack(fill="x", pady=20)
    
        ctk.CTkLabel(config_frame, text="⚙️ Configuración", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=15, pady=10)
    
        # Búsqueda
        input_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        input_frame.pack(fill="x", padx=15, pady=5)
    
        ctk.CTkLabel(input_frame, text="Programa:", width=80, anchor="w").pack(side="left")
        infoNombonic = ctk.CTkLabel(input_frame, text="ℹ️", cursor="hand2")
        infoNombonic.pack(side="left", padx=(0, 15))
        CTkToolTip(infoNombonic, "El nombre del programa se obtiene de la URL de 3cat.\nPor ejemplo, para Dr.Slump: https://www.3cat.cat/3cat/dr-slump/ tenemos que poner '''dr-slump'''.\nPara Plats Bruts: https://www.3cat.cat/3cat/plats-bruts/ tenemos que poner plats-bruts.")
        self.program_entry = ctk.CTkEntry(input_frame, placeholder_text="ej: dr-slump")
        self.program_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.program_entry.bind("<Return>", lambda e: self.search_program())
    
        self.search_btn = ctk.CTkButton(input_frame, text="🔍 Buscar", width=100, command=self.search_program)
        self.search_btn.pack(side="left")
    
        self.info_label = ctk.CTkLabel(config_frame, text="", text_color=("gray50", "gray60"), anchor="w")
        self.info_label.pack(fill="x", padx=15, pady=2)

        # Opciones Grid
        opts_grid = ctk.CTkFrame(config_frame, fg_color="transparent")
        opts_grid.pack(fill="x", padx=15, pady=10)
    
        # Calidad
        q_frame = ctk.CTkFrame(opts_grid, fg_color="transparent")
        q_frame.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(q_frame, text="Calidad:", width=60, anchor="w").pack(side="left")
        self.quality_var = ctk.StringVar(value="Todas")
        self.quality_combo = ctk.CTkComboBox(q_frame, values=["Todas"], variable=self.quality_var, width=140, state="disabled", command=self.on_quality_change)
        self.quality_combo.pack(side="left")

        # Subtitulos
        s_frame = ctk.CTkFrame(opts_grid, fg_color="transparent")
        s_frame.grid(row=0, column=1, sticky="w", padx=20)
        ctk.CTkLabel(s_frame, text="Subtitulos:", width=80, anchor="w").pack(side="left")
        self.vttlang_var = ctk.StringVar(value="Todos")
        self.vttlang_combo = ctk.CTkComboBox(s_frame, values=["Todos"], variable=self.vttlang_var, width=140, state="disabled", command=self.on_vttlang_change)
        self.vttlang_combo.pack(side="left")

        # Workers
        w_frame = ctk.CTkFrame(opts_grid, fg_color="transparent")
        w_frame.grid(row=0, column=2, sticky="w", padx=20)
        ctk.CTkLabel(w_frame, text="Workers:", width=60, anchor="w").pack(side="left")
        self.workers_var = ctk.IntVar(value=3)
        self.workers_slider = ctk.CTkSlider(w_frame, from_=1, to=10, number_of_steps=9, variable=self.workers_var, width=100)
        self.workers_slider.pack(side="left", padx=5)
        self.workers_label = ctk.CTkLabel(w_frame, text="3", width=20)
        self.workers_label.pack(side="left")
        self.workers_slider.configure(command=lambda v: self.workers_label.configure(text=str(int(v))))
        infoWorkers = ctk.CTkLabel(w_frame, text="ℹ️", cursor="hand2")
        infoWorkers.pack(side="left")
        CTkToolTip(infoWorkers, "Número de conexiones en paralelo para agilizar descargas. Si la descarga falla, reducir el número de descargas paralelas configuradas.")

        # Checks
        check_frame = ctk.CTkFrame(opts_grid, fg_color="transparent")
        check_frame.grid(row=0, column=3, sticky="w", padx=20)
        self.aria2_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(check_frame, text="Usar aria2c", variable=self.aria2_var).pack(side="left")
        infoAria2c = ctk.CTkLabel(check_frame, text="ℹ️", cursor="hand2")
        infoAria2c.pack(side="left", padx=(0, 15))
        CTkToolTip(infoAria2c, "Descarga más rápida usando múltiples conexiones.")
        self.resume_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(check_frame, text="Modo Only Resume", variable=self.resume_var).pack(side="left")
        infoResume = ctk.CTkLabel(check_frame, text="ℹ️", cursor="hand2")
        infoResume.pack(side="left", padx=(0, 15))
        CTkToolTip(infoResume, "Sólo descarga .part pendientes de descarga. No usar si se quiere descargar nuevos capítulos.")

        # Carpeta Output
        out_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        out_frame.pack(fill="x", padx=15, pady=10)
        ctk.CTkLabel(out_frame, text="Guardar en:", width=80, anchor="w").pack(side="left")
        self.output_entry = ctk.CTkEntry(out_frame)
        self.output_entry.insert(0, os.path.join(os.getcwd(), "downloads"))
        self.output_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.browse_btn = ctk.CTkButton(out_frame, text="📁", width=40, command=self.browse_folder)
        self.browse_btn.pack(side="left")
        infoOutput = ctk.CTkLabel(out_frame, text="ℹ️", cursor="hand2")
        infoOutput.pack(side="left", padx=(15, 0))
        CTkToolTip(infoOutput, "Dentro de la carpeta indicada se generará otra carpeta con el nombre de la serie/programa a descargar.")

        # Botón Acción
        act_frame = ctk.CTkFrame(config_frame, fg_color="transparent")
        act_frame.pack(fill="x", padx=15, pady=(5, 15))
        self.download_btn = ctk.CTkButton(
            act_frame, 
            text="⬇️ Descargar Seleccionados", 
            command=self.start_download, 
            height=40, 
            fg_color=("green", "darkgreen"), 
            hover_color=("darkgreen", "green"),
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.download_btn.pack(fill="x")

        # ========================================
        # TAB 2: VISTA PREVIA
        # ========================================
        self.preview_frame = ctk.CTkFrame(tab_preview, corner_radius=10)
        self.preview_frame.pack(fill="both", expand=True, pady=20)
    
        # Header Preview
        preview_header = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        preview_header.pack(fill="x", padx=15, pady=10)
    
        ctk.CTkLabel(
            preview_header, 
            text="📋 Vista Previa de Capítulos", 
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(side="left")
    
        # Controles de selección
        self.preview_controls_container = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        self.preview_controls_container.pack(fill="x", padx=15, pady=(0, 10))

        # Fila 1: Botones de selección
        controls_frame = ctk.CTkFrame(self.preview_controls_container, fg_color="transparent")
        controls_frame.pack(fill="x", padx=15, pady=(0, 10))
    
        ctk.CTkButton(controls_frame, text="✓ Todos", width=100, command=self.select_all).pack(side="left", padx=5)
        ctk.CTkButton(controls_frame, text="✓ Filtrados", width=100, command=self.select_filter).pack(side="left", padx=5)
        ctk.CTkButton(controls_frame, text="✗ Ninguno", width=100, command=self.deselect_all).pack(side="left", padx=5)
        ctk.CTkButton(controls_frame, text="✗ Filtrados", width=100, command=self.deselect_filter).pack(side="left", padx=5)
        ctk.CTkButton(controls_frame, text="🔄 Invertir", width=100, command=self.invert_selection).pack(side="left", padx=5)
    
        # Botón para obtener tamaños
        self.fetch_sizes_btn = ctk.CTkButton(
            controls_frame, 
            text="📏 Obtener Tamaños", 
            width=140, 
            command=self.fetch_file_sizes,
            fg_color=("blue", "darkblue")
        )
        self.fetch_sizes_btn.pack(side="left", padx=5)
    
        self.selection_info = ctk.CTkLabel(controls_frame, text="Seleccionados: 0/0", font=ctk.CTkFont(size=12))
        self.selection_info.pack(side="right", padx=15)
    
        # Fila 2: Filtro de búsqueda
        filter_frame = ctk.CTkFrame(self.preview_controls_container, fg_color="transparent")
        filter_frame.pack(fill="x", padx=15, pady=(0, 10))
    
        ctk.CTkLabel(filter_frame, text="🔍 Filtrar:", width=60, anchor="w").pack(side="left", padx=(0, 5))
        self.filter_entry = ctk.CTkEntry(filter_frame, placeholder_text="Buscar por título, temporada, capítulo...")
        self.filter_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.filter_entry.bind("<KeyRelease>", lambda e: self.apply_filter())
    
        ctk.CTkButton(filter_frame, text="✖ Limpiar", width=80, command=self.clear_filter).pack(side="left", padx=5)
    
        # Tabla
        self.preview_table_container = ctk.CTkFrame(self.preview_controls_container, fg_color="transparent")
        self.preview_table_container.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        # Crear Treeview con estilo personalizado
        style = ttk.Style()
        style.theme_use("default")
    
        # Configurar colores para modo oscuro
        style.configure("Treeview",
            background="gray10", #("gray95", "gray10")
            foreground="white",
            fieldbackground="gray10",
            borderwidth=0,
            font=('Segoe UI', 10)
        )
        style.configure("Treeview.Heading",
            background="#333333",
            foreground="white",
            borderwidth=1,
            relief="flat",
            font=('Segoe UI', 10, 'bold')
        )
        style.map("Treeview",
            background=[('selected', '#1f538d')],
            foreground=[('selected', 'white')]
        )
    
        # Frame para tabla y scrollbar
        table_frame = tk.Frame(self.preview_table_container, bg="#2b2b2b")
        table_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
    
        # Scrollbars
        vsb = ctk.CTkScrollbar(
            table_frame,
            orientation="vertical",
            width=16,
            fg_color="transparent",
            button_color="#444444",
            button_hover_color="#666666"
        )

        hsb = ctk.CTkScrollbar(
            table_frame,
            orientation="horizontal",
            height=16,
            fg_color="transparent",
            button_color="#444444",
            button_hover_color="#666666"
        )

        # Treeview
        self.tree = ttk.Treeview(
            table_frame,
            columns=("sel", "temp", "cap", "titulo", "calidad", "tipo", "tamaño"),
            show="headings",
            height=15,
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )
    
        vsb.configure(command=self.tree.yview)
        hsb.configure(command=self.tree.xview)
    
        # Configurar columnas
        self.tree.heading("sel", text="✓", command=lambda: self.sort_by_column("sel"))
        self.tree.heading("temp", text="Temp", command=lambda: self.sort_by_column("temp"))
        self.tree.heading("cap", text="Cap", command=lambda: self.sort_by_column("cap"))
        self.tree.heading("titulo", text="Título", command=lambda: self.sort_by_column("titulo"))
        self.tree.heading("calidad", text="Calidad", command=lambda: self.sort_by_column("calidad"))
        self.tree.heading("tipo", text="Tipo", command=lambda: self.sort_by_column("tipo"))
        self.tree.heading("tamaño", text="Tamaño", command=lambda: self.sort_by_column("tamaño"))
    
        self.tree.column("sel", width=40, anchor="center")
        self.tree.column("temp", width=60, anchor="center")
        self.tree.column("cap", width=60, anchor="center")
        self.tree.column("titulo", width=400, anchor="w")
        self.tree.column("calidad", width=100, anchor="center")
        self.tree.column("tipo", width=60, anchor="center")
        self.tree.column("tamaño", width=100, anchor="e")
    
        # Empaquetar
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
    
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
    
        # Bind para toggle selection
        self.tree.bind("<Double-1>", self.toggle_item_selection)
        self.tree.bind("<space>", self.toggle_item_selection)

        # ========================================
        # TAB 3: PROGRESO (ANTES ERA FOOTER)
        # ========================================
        progress_main_frame = ctk.CTkFrame(tab_progress, corner_radius=10)
        progress_main_frame.pack(fill="both", expand=True, pady=20)

        # Contenedor interno del progreso
        progress_container = ctk.CTkFrame(progress_main_frame, fg_color="transparent")
        progress_container.pack(fill="both", expand=True, padx=20, pady=15)

        # Título Sección Progreso
        prog_header = ctk.CTkFrame(progress_container, fg_color="transparent")
        prog_header.pack(fill="x", pady=(0, 15))
        ctk.CTkLabel(
            prog_header, 
            text="📊 Estado y Progreso", 
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(side="left")

        # Info de estado
        self.progress_info = ctk.CTkLabel(
            progress_container,
            text="Estado: Esperando órdenes...",
            anchor="w",
            font=ctk.CTkFont(size=13)
        )
        self.progress_info.pack(fill="x", pady=(0, 10))

        # Barra de progreso global
        self.progress_bar = ctk.CTkProgressBar(progress_container, height=20)
        self.progress_bar.pack(fill="x", pady=(0, 20))
        self.progress_bar.set(0)

        # Lista de descargas activas
        self.downloads_frame = ctk.CTkScrollableFrame(
            progress_container,
            height=400,  # Más altura al estar en una pestaña
            fg_color=("gray95", "gray10"),
            label_text="⚡ Descargas Activas"
        )
        self.downloads_frame.pack(fill="both", expand=True, pady=(5, 0))
    
        self.no_downloads_label = ctk.CTkLabel(
            self.downloads_frame,
            text="No hay descargas activas",
            text_color=("gray50", "gray60"),
            font=ctk.CTkFont(size=13)
        )
        self.no_downloads_label.pack(pady=40)

        # ========================================
        # TAB 4: LOGS
        # ========================================
        self.log_frame = ctk.CTkFrame(tab_logs, corner_radius=10)
        self.log_frame.pack(fill="both", expand=True, pady=20)
    
        # Header Logs
        log_header = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=15, pady=10)
    
        ctk.CTkLabel(
            log_header, 
            text="📋 Registro de actividad", 
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(side="left")
    
        # Text widget
        self.log_text_container = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        self.log_text_container.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.log_text = ctk.CTkTextbox(
            self.log_text_container, 
            height=400,
            wrap="word", 
            font=ctk.CTkFont(family="Consolas", size=11)
        )
        self.log_text.pack(fill="both", expand=True)
    
        self.add_log("✅ Interfaz cargada con Vista Previa")
        self.add_log("ℹ️ Busca un programa para ver los capítulos disponibles")

    def show_help(self):
        """Mostrar ventana de ayuda"""
        help_window = ctk.CTkToplevel(self)
        help_window.title("Ayuda - TV3 GUI Downloader")
        help_window.geometry("600x500")
        help_window.transient(self)
        help_window.grab_set()
    
        # Contenido
        text = ctk.CTkTextbox(help_window, wrap="word", font=ctk.CTkFont(size=12))
        text.pack(fill="both", expand=True, padx=20, pady=20)
    
        help_text = """
🎬 TV3 GUI DOWNLOADER - GUÍA RÁPIDA

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 CÓMO OBTENER EL NOMBRE DEL PROGRAMA:

1. Ve a https://www.3cat.cat/
2. Busca tu programa/serie favorita
3. Copia el nombre de la URL después de "/3cat/"
   
   Ejemplos:
   • https://www.3cat.cat/3cat/dr-slump/ → "dr-slump"
   • https://www.3cat.cat/3cat/plats-bruts/ → "plats-bruts"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚙️ OPCIONES:

• Calidad: Selecciona la resolución del vídeo
• Subtítulos: Elige el idioma de subtítulos
• Workers: Número de descargas simultáneas (más = más rápido)
• aria2c: Descarga ultra-rápida (requiere tener aria2c instalado)
• Only Resume: Solo continúa descargas interrumpidas

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⌨️ ATAJOS DE TECLADO:

• Ctrl+A: Seleccionar todos
• Ctrl+D: Deseleccionar todos
• Ctrl+I: Invertir selección
• Ctrl+F: Buscar/Filtrar
• F5: Refrescar programa actual
• Enter: Buscar programa (en el campo de búsqueda)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 CONSEJOS:

• Usa "Obtener Tamaños" para ver el espacio necesario
• Filtra por temporada/capítulo para descargas específicas
• Los archivos .part se pueden reanudar activando "Only Resume"
• Si falla la descarga, reduce el número de Workers

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📧 ¿Problemas? Revisa los logs en la pestaña correspondiente.
"""
    
        text.insert("1.0", help_text)
        text.configure(state="disabled")
    
        # Botón cerrar
        close_btn = ctk.CTkButton(
            help_window,
            text="Cerrar",
            command=help_window.destroy,
            width=100
        )
        close_btn.pack(pady=(0, 20))

    def populate_tree(self):
        """Poblar la tabla con los items del manifest"""
        # Limpiar tabla
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree_items.clear()
        
        if not self.manifest_data:
            return
        
        items = self.manifest_data.get("items", [])
        
        # Guardar todos los items
        self.all_items = []
        
        for idx, item in enumerate(items):
            item_data = {
                "temp": item.get("temporada", "?"),
                "cap": item.get("temporada_capitol", "?"),
                "titulo": item.get("title", "Sin título"),
                "calidad": item.get("quality", "?"),
                "tipo": item.get("type", "?").upper(),
                "tamaño": "?",
                "tamaño_bytes": 0,
                "item": item,
                "selected": True
            }
            self.all_items.append(item_data)
        
        # Aplicar filtro (inicialmente muestra todo)
        self.apply_filter()
        
        self.add_log(f"📊 Cargados {len(items)} elementos en la vista previa")
    
    def apply_filter(self):
        """Aplicar filtro de búsqueda a la tabla"""
        # Limpiar tabla
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.tree_items.clear()
        
        # Obtener texto de filtro
        filter_text = self.filter_entry.get().lower().strip()
        
        # Filtrar items
        filtered_items = []
        for item_data in self.all_items:
            if not filter_text:
                filtered_items.append(item_data)
            else:
                # Buscar en varios campos
                searchable = f"{item_data['temp']} {item_data['cap']} {item_data['titulo']} {item_data['calidad']} {item_data['tipo']}".lower()
                if filter_text in searchable:
                    filtered_items.append(item_data)
        
        # Ordenar si hay columna activa
        if self.sort_column:
            filtered_items = self.sort_items(filtered_items, self.sort_column, self.sort_reverse)
        
        # Insertar items filtrados
        for item_data in filtered_items:
            iid = self.tree.insert("", "end", values=(
                "✓" if item_data["selected"] else "",
                item_data["temp"],
                item_data["cap"],
                item_data["titulo"],
                item_data["calidad"],
                item_data["tipo"],
                item_data["tamaño"]
            ))
            
            # Guardar referencia
            self.tree_items[iid] = item_data
        
        self.update_selection_info()
    
    def clear_filter(self):
        """Limpiar el filtro de búsqueda"""
        self.filter_entry.delete(0, "end")
        self.apply_filter()
    
    def sort_by_column(self, column):
        """Ordenar tabla por columna"""
        # Si es la misma columna, invertir orden
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False
        
        # Actualizar headers para mostrar indicador de orden
        for col in ("sel", "temp", "cap", "titulo", "calidad", "tipo", "tamaño"):
            text = {
                "sel": "✓",
                "temp": "Temp",
                "cap": "Cap",
                "titulo": "Título",
                "calidad": "Calidad",
                "tipo": "Tipo",
                "tamaño": "Tamaño"
            }[col]
            
            if col == column:
                indicator = " ▼" if self.sort_reverse else " ▲"
                text += indicator
            
            self.tree.heading(col, text=text)
        
        # Reaplicar filtro (que incluye el ordenamiento)
        self.apply_filter()
    
    def sort_items(self, items, column, reverse):
        """Ordenar lista de items por columna"""
        def get_sort_key(item_data):
            if column == "sel":
                return item_data["selected"]
            elif column == "temp":
                try:
                    return int(item_data["temp"])
                except:
                    return 0
            elif column == "cap":
                try:
                    return int(item_data["cap"])
                except:
                    return 0
            elif column == "titulo":
                return item_data["titulo"].lower()
            elif column == "calidad":
                return item_data["calidad"].lower()
            elif column == "tipo":
                return item_data["tipo"]
            elif column == "tamaño":
                return item_data["tamaño_bytes"]
            return ""
        
        return sorted(items, key=get_sort_key, reverse=reverse)
    
    def fetch_file_sizes(self):
        """Obtener tamaños de archivos mediante HEAD requests"""
        if not self.all_items:
            messagebox.showwarning("Advertencia", "No hay archivos cargados")
            return
        
        self.fetch_sizes_btn.configure(state="disabled", text="⏳ Obteniendo...")
        self.add_log("📏 Iniciando obtención de tamaños...")
        
        def fetch_thread():
            try:
                total = len(self.all_items)
                processed = 0
                workers = self.workers_var.get()
                
                def fetch_size(item_data):
                    nonlocal processed
                    try:
                        url = item_data["item"]["link"]
                        # Intentar HEAD primero
                        response = SESSION.head(url, timeout=10, allow_redirects=True)
                        size = int(response.headers.get("Content-Length", 0))
                        
                        # Si HEAD devuelve 0 o falla, intentar GET parcial (para VTT)
                        if size == 0:
                            # Hacer GET con Range para obtener solo los headers
                            response = SESSION.get(
                                url, 
                                timeout=10, 
                                allow_redirects=True,
                                stream=True
                            )
                            size = int(response.headers.get("Content-Length", 0))
                            
                            # Si aún es 0, descargar el contenido y medir
                            if size == 0:
                                content = response.content
                                size = len(content)
                        # Actualizar item_data
                        item_data["tamaño_bytes"] = size
                        item_data["tamaño"] = format_size(size)
                        
                        processed += 1
                        if processed % 10 == 0:
                            self.log_queue.put(("log", f"📏 Procesados {processed}/{total} archivos..."))
                        
                        return True
                    except Exception as e:
                        item_data["tamaño"] = "Error"
                        item_data["tamaño_bytes"] = 0
                        processed += 1
                        logger.debug(f"Error obteniendo tamaño de {url}: {e}")
                        return False
                
                # Usar ThreadPoolExecutor para paralelizar
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futures = [ex.submit(fetch_size, item_data) for item_data in self.all_items]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except:
                            pass
                
                # Calcular tamaño total
                total_bytes = sum(item["tamaño_bytes"] for item in self.all_items)
                total_selected_bytes = sum(
                    item["tamaño_bytes"] for item in self.all_items if item["selected"]
                )
                
                self.log_queue.put(("log", f"✅ Tamaños obtenidos: Total {format_size(total_bytes)}"))
                self.log_queue.put(("log", f"📦 Seleccionados: {format_size(total_selected_bytes)}"))
                
                # Actualizar tabla
                self.after(0, self.apply_filter)
                self.after(0, lambda: self.fetch_sizes_btn.configure(state="normal", text="📏 Obtener Tamaños"))
                
            except Exception as e:
                self.log_queue.put(("log", f"❌ Error obteniendo tamaños: {str(e)}"))
                self.after(0, lambda: self.fetch_sizes_btn.configure(state="normal", text="📏 Obtener Tamaños"))
        
        threading.Thread(target=fetch_thread, daemon=True).start()

    def toggle_item_selection(self, event=None):
        """Toggle selección de un item"""
        selection = self.tree.selection()
        if not selection:
            return
        
        for iid in selection:
            if iid in self.tree_items:
                # Toggle estado
                current = self.tree_items[iid]["selected"]
                self.tree_items[iid]["selected"] = not current
                
                # Actualizar visual
                values = list(self.tree.item(iid)["values"])
                values[0] = "✓" if not current else ""
                self.tree.item(iid, values=values)
        
        self.update_selection_info()

    def select_all(self):
        """Seleccionar todos los items"""
        for item_data in self.all_items:
            item_data["selected"] = True
        self.apply_filter()

    def select_filter(self):
        """Seleccionar los items filtrados"""
        for iid, item_data in self.tree_items.items():
            item_data["selected"] = True
        self.apply_filter()
    
    def deselect_all(self):
        """Deseleccionar todos los items"""
        for item_data in self.all_items:
            item_data["selected"] = False
        self.apply_filter()

    def deselect_filter(self):
        """Deseleccionar los items filtrados"""
        for iid, item_data in self.tree_items.items():
            item_data["selected"] = False
        self.apply_filter()
    
    def invert_selection(self):
        """Invertir selección"""
        for item_data in self.all_items:
            item_data["selected"] = not item_data["selected"]
        self.apply_filter()

    def update_selection_info(self):
        total = len(self.all_items)
        selected = sum(1 for item in self.all_items if item["selected"])
        total_size = sum(item["tamaño_bytes"] for item in self.all_items if item["selected"])
    
        # Actualizar info de selección
        if total_size > 0:
            self.selection_info.configure(
                text=f"Seleccionados: {selected}/{total} ({format_size(total_size)})"
            )
            # NUEVO: Actualizar barra de estado
            self.status_label.configure(
                text=f"📊 {selected} seleccionados de {total} | {format_size(total_size)}"
            )
        else:
            self.selection_info.configure(text=f"Seleccionados: {selected}/{total}")
            self.status_label.configure(text=f"📊 {selected} seleccionados de {total} | 0 B")

    def get_selected_items(self):
        """Obtener lista de items seleccionados"""
        return [item["item"] for item in self.all_items if item["selected"]]

    def add_log(self, message):
        """Añadir mensaje al log y autoscroll"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
    
    def update_logs(self):
        try:
            while True:
                msg_type, message = self.log_queue.get_nowait()
                if msg_type == "log":
                    self.add_log(message.strip())
        except queue.Empty:
            pass
        self.after(100, self.update_logs)
    
    def update_progress(self):
        try:
            while True:
                progress_data = self.progress_queue.get_nowait()
                if progress_data["type"] == "progress":
                    self.progress_bar.set(progress_data["value"])
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
        try:
            while True:
                file_data = self.file_progress_queue.get_nowait()
                if file_data["type"] == "start":
                    self.add_active_download(file_data["filename"])
                elif file_data["type"] == "update":
                    self.update_active_download(file_data["filename"], file_data["progress"])
                elif file_data["type"] == "complete":
                    self.remove_active_download(file_data["filename"])
                elif file_data["type"] == "error":
                    self.remove_active_download(file_data["filename"], error=True)
        except queue.Empty:
            pass
        self.after(50, self.update_file_progress)
    
    def add_active_download(self, filename):
        if filename in self.active_downloads: return
        if self.no_downloads_label.winfo_exists(): self.no_downloads_label.pack_forget()
        
        file_frame = ctk.CTkFrame(self.downloads_frame, fg_color="transparent")
        file_frame.pack(fill="x", padx=5, pady=2)
        
        display_name = filename if len(filename) <= 50 else filename[:47] + "..."
        name_label = ctk.CTkLabel(file_frame, text=f"📥 {display_name}", anchor="w", font=ctk.CTkFont(size=11))
        name_label.pack(fill="x")
        
        progress_bar = ctk.CTkProgressBar(file_frame, height=6)
        progress_bar.pack(fill="x", pady=(2, 0))
        progress_bar.set(0)
        
        self.active_downloads[filename] = {"frame": file_frame, "label": name_label, "bar": progress_bar}
    
    def update_active_download(self, filename, progress):
        if filename in self.active_downloads:
            self.active_downloads[filename]["bar"].set(progress)
    
    def remove_active_download(self, filename, error=False):
        if filename in self.active_downloads:
            self.active_downloads[filename]["frame"].destroy()
            del self.active_downloads[filename]
        if len(self.active_downloads) == 0:
            self.no_downloads_label.pack(pady=10)
    
    def clear_active_downloads(self):
        for filename in list(self.active_downloads.keys()):
            self.remove_active_download(filename)
    
    def browse_folder(self):
        folder = filedialog.askdirectory(title="Seleccionar carpeta de descarga")
        if folder:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, folder)
    
    def disable_controls(self):
        self.search_btn.configure(state="disabled")
        self.download_btn.configure(state="disabled")
        self.program_entry.configure(state="disabled")
    
    def enable_controls(self):
        self.search_btn.configure(state="normal")
        self.download_btn.configure(state="normal")
        self.program_entry.configure(state="normal")
    
    def search_program(self):
        program_name = self.program_entry.get().strip()
        if not program_name:
            messagebox.showwarning("Advertencia", "Introduce el nombre del programa")
            return
        
        self.disable_controls()

        self.search_btn.configure(text="⏳ Buscando...")

        self.add_log(f"🔍 Buscando programa: {program_name}")
        self.progress_info.configure(text="Estado: Buscando programa y generando manifest...")
        
        def search_thread():
            try:
                # Obtener info del programa
                info = obtener_program_info(program_name)
                self.program_info = info
                self.log_queue.put(("log", f"✅ Programa encontrado: {info.get('titol')}"))
                self.log_queue.put(("log", f"📺 ID: {info.get('id')}"))
                
                # Generar manifest automáticamente
                self.log_queue.put(("log", "📄 Obteniendo capítulos y generando manifest..."))
                program_id = info.get("id")
                workers = self.workers_var.get()
                
                cids = obtener_ids_capitulos(program_id, items_pagina=100, workers=workers)
                self.log_queue.put(("log", f"📊 Total capítulos encontrados: {len(cids)}"))
                
                manifest_path = "manifest.json"
                self.manifest_data = build_manifest(cids, manifest_path, workers=workers)

                diffitems = self.manifest_data.get("items", [])
                video=0
                subt=0
                for item in diffitems:
                    if item.get("type") == "mp4":
                        video=video+1
                    if item.get("type") == "vtt":
                        subt=subt+1

                self.log_queue.put(("log", f"✅ Manifest generado: {len(self.manifest_data.get('items', []))} archivos: {video} videos - {subt} subtitulos"))

                # Extraer calidades disponibles
                self.extract_available_qualities()
                self.extract_available_vttlangs()
                
                # Poblar la tabla
                self.after(0, self.populate_tree)
                
                self.after(0, lambda: self.info_label.configure(
                    text=f"📺 {info.get('titol')} - {len(self.manifest_data.get('items', []))} archivos disponibles: {video} videos - {subt} subtitulos", 
                    text_color=("green", "lightgreen")
                ))
                self.progress_queue.put({"type": "info", "text": "✅ Programa cargado y listo para descargar"})
                self.after(0, lambda: self.search_btn.configure(text="🔍 Buscar"))
            except Exception as e:
                self.log_queue.put(("log", f"❌ Error: {str(e)}"))
                self.program_info = None
                self.manifest_data = None
                self.after(0, lambda: self.info_label.configure(text="❌ Programa no encontrado", text_color=("red", "lightcoral")))
                self.progress_queue.put({"type": "error", "text": str(e)})
                self.after(0, lambda: self.search_btn.configure(text="🔍 Buscar"))
            finally:
                self.after(0, self.enable_controls)
        
        threading.Thread(target=search_thread, daemon=True).start()
    
    def extract_available_qualities(self):
        """Extraer calidades disponibles del manifest en memoria"""
        try:
            if not self.manifest_data:
                return
            
            qualities = set()
            for item in self.manifest_data.get("items", []):
                if item.get("type") == "mp4":
                    quality = item.get("quality", "")
                    if quality:
                        qualities.add(quality)
            
            self.available_qualities = qualities
            self.after(0, self.update_quality_selector, qualities)
        except Exception as e:
            self.log_queue.put(("log", f"⚠️ No se pudieron extraer las calidades: {str(e)}"))
    
    def update_quality_selector(self, qualities):
        if qualities:
            sorted_qualities = sorted(
                qualities, 
                key=lambda x: int(''.join(filter(str.isdigit, x))) if any(c.isdigit() for c in x) else 0, 
                reverse=True
            )
            quality_list = ["Todas"] + ["Ninguna (No Video)"] + sorted_qualities
            self.quality_combo.configure(values=quality_list, state="normal")
            self.quality_var.set("Todas")
            self.add_log(f"🎬 Calidades disponibles: {', '.join(sorted_qualities)}")
        else:
            self.quality_combo.configure(values=["Todas"], state="normal")
            self.add_log("⚠️ No se encontraron calidades específicas")
    
    def extract_available_vttlangs(self):
        """Extraer idiomas de subtítulos disponibles"""
        try:
            if not self.manifest_data:
                return
            
            vttlangs = set()
            for item in self.manifest_data.get("items", []):
                if item.get("type") == "vtt":
                    vttlang = item.get("quality", "")
                    if vttlang:
                        vttlangs.add(vttlang)
            
            self.available_vttlangs = vttlangs
            self.after(0, self.update_vttlang_selector, vttlangs)
        except Exception as e:
            self.log_queue.put(("log", f"⚠️ No se pudieron extraer los idiomas: {str(e)}"))
    
    def update_vttlang_selector(self, vttlangs):
        if vttlangs:
            sorted_vttlangs = sorted(
                vttlangs, 
                key=lambda x: int(''.join(filter(str.isdigit, x))) if any(c.isdigit() for c in x) else 0, 
                reverse=True
            )
            vttlang_list = ["Todos"] + ["Ninguno (No Subs)"] + sorted_vttlangs
            self.vttlang_combo.configure(values=vttlang_list, state="normal")
            self.vttlang_var.set("Todos")
            self.add_log(f"🎬 Subtítulos disponibles: {', '.join(sorted_vttlangs)}")
        else:
            self.vttlang_combo.configure(values=["Todos"], state="normal")
            self.add_log("⚠️ No se encontraron subtítulos específicos")
    
    def on_quality_change(self, choice):
        """Aplicar filtro de calidad automáticamente"""
        self.apply_quality_subtitle_filters()
    
    def on_vttlang_change(self, choice):
        """Aplicar filtro de subtítulos automáticamente"""
        self.apply_quality_subtitle_filters()
    
    def apply_quality_subtitle_filters(self):
        """Aplicar filtros de calidad y subtítulos a la selección"""
        if not self.all_items:
            return
        
        quality_filter = self.quality_var.get()
        vttlang_filter = self.vttlang_var.get()
        
        # Log de la acción
        filters_applied = []
        if quality_filter != "Todas":
            filters_applied.append(f"Calidad: {quality_filter}")
        if vttlang_filter != "Todos":
            filters_applied.append(f"Subtítulos: {vttlang_filter}")
        
        if filters_applied:
            self.add_log(f"🔧 Aplicando filtros: {', '.join(filters_applied)}")
        
        # Aplicar filtros a todos los items
        for item_data in self.all_items:
            item_type = item_data["tipo"]
            item_quality = item_data["calidad"]
            
            should_select = True
            
            # Filtro de calidad (solo para MP4)
            if item_type == "MP4":
                if quality_filter == "Ninguna (No Video)":
                    should_select = False
                elif quality_filter != "Todas" and quality_filter not in item_quality:
                    should_select = False
            
            # Filtro de subtítulos (solo para VTT)
            if item_type == "VTT":
                if vttlang_filter == "Ninguno (No Subs)":
                    should_select = False
                elif vttlang_filter != "Todos" and vttlang_filter not in item_quality:
                    should_select = False
            
            # Actualizar selección
            item_data["selected"] = should_select
        
        # Actualizar la vista
        self.apply_filter()
        
        # Contar seleccionados
        selected_count = sum(1 for item in self.all_items if item["selected"])
        self.add_log(f"✓ Filtros aplicados: {selected_count} elementos seleccionados")
    def start_download(self):
        if not self.program_info or not self.manifest_data:
            messagebox.showwarning("Advertencia", "Primero busca un programa")
            return
        
        # Obtener items seleccionados
        selected_items = self.get_selected_items()
        
        if not selected_items:
            messagebox.showwarning("Advertencia", "No has seleccionado ningún elemento para descargar")
            return
        
        self.is_downloading = True
        self.disable_controls()
        self.add_log(f"⬇️ Iniciando descarga de {len(selected_items)} elementos...")
        self.progress_bar.set(0)
        self.progress_info.configure(text="Estado: Descargando...")
        
        def download_thread():
            try:
                output_folder = self.output_entry.get()
                workers = self.workers_var.get()
                use_aria2 = self.aria2_var.get()
                resume = self.resume_var.get()
                
                total_files = len(selected_items)
                self.log_queue.put(("log", f"📦 Total archivos a descargar: {total_files}"))
                
                self.download_from_manifest(
                    selected_items, 
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
    
    def download_from_manifest(self, items, program_name, total_files, videos_folder="downloads", max_workers=6, use_aria2=False, resume=True):
        base_folder = videos_folder
        ensure_folder(base_folder)
    
        # Tiempo de inicio
        start_time = time.time()
    
        tasks = []
        skipped = 0
    
        for item in items:
            link = item["link"]
            program = safe_filename(item["program"])
            folder = os.path.join(base_folder, program)
            ensure_folder(folder)
        
            name = item["name"]
            file_ext = item["file_name"].split('.')[-1]
            final_name = f"{name}.{file_ext}"
            dst = os.path.join(folder, safe_filename(final_name))
            tmp = dst + ".part"
        
            if resume:
                if not os.path.exists(tmp):
                    continue
                method_use_aria2 = False
            else:
                if os.path.exists(dst):
                    skipped += 1
                    continue
                method_use_aria2 = bool(use_aria2)
        
            desc_name = os.path.basename(dst)
            tasks.append({
                "link": link, 
                "dst": dst, 
                "desc": desc_name, 
                "use_aria2": method_use_aria2,
                "folder": folder  # Guardar carpeta de destino
            })
    
        if skipped > 0:
            self.log_queue.put(("log", f"⏭️ {skipped} archivos ya descargados (omitidos)"))
    
        if not tasks:
            self.log_queue.put(("log", "ℹ️ No hay archivos pendientes de descarga"))
            self.progress_queue.put({"type": "complete", "text": ""})
            return
    
        self.log_queue.put(("log", f"🔄 Procesando {len(tasks)} archivos..."))
    
        total_tasks = len(tasks)
        completed_tasks = 0
        failed_tasks = []
        destination_folder = tasks[0]["folder"] if tasks else base_folder
    
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {}
            for t in tasks:
                if t["use_aria2"]:
                    fut = ex.submit(download_with_aria2, t["link"], t["dst"])
                else:
                    fut = ex.submit(download_chunked_with_callback, t["link"], t["dst"], t["desc"], 4, 30, not resume, self.file_progress_queue)
                futures[fut] = t
        
            for future in as_completed(futures):
                task = futures[future]
                filename = task["desc"]
                try:
                    res = future.result()
                    if res:
                        completed_tasks += 1
                        self.log_queue.put(("log", f"✅ Descargado: {filename}"))
                    else:
                        failed_tasks.append(filename)
                        self.log_queue.put(("log", f"⚠️ Fallo al descargar: {filename}"))
                
                    # Actualizar progreso
                    progress_value = (completed_tasks + len(failed_tasks)) / total_tasks
                    self.progress_queue.put({"type": "progress", "value": progress_value})
                    self.progress_queue.put({
                        "type": "info", 
                        "text": f"Descargando: {completed_tasks}/{total_tasks} completados, {len(failed_tasks)} fallidos ({int(progress_value * 100)}%)"
                    })
                except Exception as e:
                    failed_tasks.append(filename)
                    self.log_queue.put(("log", f"❌ Error: {filename} - {str(e)}"))
    
        # Calcular tiempo total
        end_time = time.time()
        duration_seconds = int(end_time - start_time)
        duration_str = f"{duration_seconds // 60}m {duration_seconds % 60}s"
    
        # Estadísticas finales
        total_downloaded = sum(1 for t in tasks if os.path.exists(t["dst"]))
        size_bytes = sum(os.path.getsize(t["dst"]) for t in tasks if os.path.exists(t["dst"]))
    
        # Logs (como antes)
        self.log_queue.put(("log", "=" * 50))
        self.log_queue.put(("log", "📊 ESTADÍSTICAS FINALES"))
        self.log_queue.put(("log", "=" * 50))
        self.log_queue.put(("log", f"✅ Descargados exitosamente: {total_downloaded}"))
        self.log_queue.put(("log", f"❌ Fallidos: {len(failed_tasks)}"))
        if skipped > 0:
            self.log_queue.put(("log", f"⏭️ Ya existían: {skipped}"))
        self.log_queue.put(("log", f"💾 Tamaño total: {size_bytes / (1024*1024):.2f} MB"))
        self.log_queue.put(("log", f"🕐 Tiempo total: {duration_str}"))
    
        if failed_tasks:
            self.log_queue.put(("log", ""))
            self.log_queue.put(("log", "⚠️ Archivos fallidos:"))
            for failed_file in failed_tasks[:10]:
                self.log_queue.put(("log", f"  - {failed_file}"))
            if len(failed_tasks) > 10:
                self.log_queue.put(("log", f"  ... y {len(failed_tasks) - 10} más"))
    
        self.log_queue.put(("log", "=" * 50))
    
        # NUEVO: Preparar estadísticas para el popup
        stats = {
            'completed': total_downloaded,
            'failed': len(failed_tasks),
            'skipped': skipped,
            'total_size': format_size(size_bytes),
            'duration': duration_str,
            'folder': destination_folder,
            'failed_list': failed_tasks
        }
    
        # NUEVO: Mostrar popup con estadísticas
        self.after(500, lambda: self.show_stats_popup(stats))


# ----------------------------
# Utilities
# ----------------------------
def format_size(bytes_size):
    """Formatear tamaño en bytes a formato legible"""
    if bytes_size == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(bytes_size)
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    else:
        return f"{size:.2f} {units[unit_index]}"

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
    
    def fetch_page(page):
        attempts = 0
        while attempts <= max_retries:
            attempts += 1
            try:
                params = {"items_pagina": items_pagina, "ordre": orden, "programatv_id": programatv_id, "pagina": page, "tipus_contingut": "PPD"}
                d = fetch_json("https://api.3cat.cat/videos", params=params)
                item_list = d["resposta"]["items"]["item"]
                if isinstance(item_list, dict):
                    item_list = [item_list]
                ids_local = [i["id"] for i in item_list if "id" in i]
                tcap_local = [i["capitol_temporada"] for i in item_list if "capitol_temporada" in i]
                return ids_local, tcap_local
            except Exception as e:
                time.sleep(1 * attempts)
        return [], []

    all_ids, all_tcaps = [], []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetch_page, p): p for p in range(1, pags+1)}
        for future in as_completed(futures):
            try:
                ids, tcaps = future.result()
                all_ids.extend(ids)
                all_tcaps.extend(tcaps)
            except Exception:
                pass
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
            if not isinstance(entry, dict):
                continue
            mp4 = entry.get("file")
            label = entry.get("label") or entry.get("quality") or entry.get("descripcio") or ""
            if mp4 and ("mp4" in mp4.lower()):
                mp4s.append({"label": label or "mp4", "url": mp4})
        vfiles = data.get("subtitols", []) or []
        if isinstance(vfiles, dict):
            vfiles = [vfiles]
        vtts = []
        for entry in vfiles:
            if not isinstance(entry, dict):
                continue
            vtt = entry.get("url")
            label = entry.get("text") or entry.get("lang") or ""
            if vtt and (".vtt" in vtt.lower() or "vtt" in vtt.lower()):
                vtts.append({"label": label or "vtt", "url": vtt})
        info["mp4s"] = mp4s
        info["vtts"] = vtts
        cache_set(id_cap, info)
        return info
    except Exception as e:
        return None

def build_manifest(cids, manifest_path="manifest.json", workers=8, retry_failed=2):
    """Genera el manifest sin crear CSV"""
    ensure_folder("cache")
    failed = []
    manifest_items = []
    
    def worker(cid):
        attempts = 0
        while attempts <= retry_failed:
            attempts += 1
            res = api_extract_media_urls(cid["id"])
            if res:
                break
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
            fname = mp["url"].split("/")[-1]
            local.append({
                "capitol": capitol,
                "program": program,
                "temporada": temporada,
                "temporada_capitol": tcap,
                "title": title,
                "name": f"{safe_name} - {mp['label']}",
                "quality": mp["label"],
                "link": mp["url"],
                "file_name": fname,
                "type": "mp4"
            })
        
        for vt in res["vtts"]:
            fname = vt["url"].split("/")[-1]
            local.append({
                "capitol": capitol,
                "program": program,
                "temporada": temporada,
                "temporada_capitol": tcap,
                "title": title,
                "name": f"{safe_name} - {vt['label']}",
                "quality": vt["label"],
                "link": vt["url"],
                "file_name": fname,
                "type": "vtt"
            })
        
        return local

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(worker, cid): cid for cid in cids}
        for future in as_completed(futures):
            try:
                chapter_items = future.result()
                manifest_items.extend(chapter_items)
            except Exception:
                failed.append(futures[future])

    def safe_int(x):
        try:
            return int(x)
        except:
            return 0
    
    manifest_items_sorted = sorted(manifest_items, key=lambda r: safe_int(r["capitol"]))

    manifest = {
        "generated_at": time.time(),
        "items": manifest_items_sorted
    }
    
    with open(manifest_path, "w", encoding="utf-8") as mf:
        json.dump(manifest, mf, ensure_ascii=False, indent=2)

    return manifest

def download_chunked_with_callback(url, dst, desc_name, max_retries=4, timeout=30, use_range=True, progress_queue=None):
    ensure_folder(os.path.dirname(dst))
    tmp = dst + ".part"
    existing = os.path.getsize(tmp) if os.path.exists(tmp) else 0
    headers = {}
    filename = os.path.basename(dst)
    if use_range and existing > 0:
        headers["Range"] = f"bytes={existing}-"
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
                    last_update = 0.0
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            now = time.time()
                            if total_bytes and progress_queue and (now - last_update) >= 0.1:
                                progress_queue.put_nowait({"type": "update", "filename": filename, "progress": downloaded / total_bytes})
                                last_update = now
                os.replace(tmp, dst)
                if progress_queue:
                    progress_queue.put({"type": "complete", "filename": filename})
                return dst
        except Exception as e:
            time.sleep(1)
            
    if progress_queue:
        progress_queue.put({"type": "error", "filename": filename})
    return None

def download_with_aria2(url, dst, aria2c_bin="aria2c"):
    ensure_folder(os.path.dirname(dst))
    cmd = [aria2c_bin, "--file-allocation=none", "--max-connection-per-server=4", "--split=4", "--continue=true", "--dir", os.path.dirname(dst), "--out", os.path.basename(dst), url]
    try:
        subprocess.check_call(cmd)
        return dst
    except Exception:
        return None

class StdoutRedirector:
    def __init__(self, log_queue):
        self.log_queue = log_queue
        handler = QueueLogHandler(self.log_queue)
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    def write(self, message):
        if message.strip():
            self.log_queue.put(("log", message.rstrip()))

    def flush(self):
        pass

def main():
    app = TV3_GUI()
    app.mainloop()

if __name__ == "__main__":
    main()
                