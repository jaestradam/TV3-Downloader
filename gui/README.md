# 3Cat GUI Downloader

[![License: MIT](https://img.shields.io/github/license/jaestradam/tv3-downloader)](https://opensource.org/licenses/MIT)

Este proyecto es una interfaz gráfica (GUI) avanzada para la descarga masiva de contenidos (vídeos y subtítulos) de la plataforma **3Cat / TV3**. Basada en el motor de `tv3_cli.py` e independiente de éste, esta aplicación ofrece una experiencia de usuario intuitiva con potentes herramientas de filtrado, previsualización interactiva y soporte multi-idioma verificado.

## 🚀 Características Principales

+ **Interfaz Moderna:** Desarrollada con `customtkinter` para un diseño oscuro, elegante y funcional.
+ **Vista Previa de Capítulos:** Tabla interactiva (`Treeview`) que permite visualizar temporadas, títulos y calidades antes de descargar.
+ **Soporte Multi-idioma (i18n):** Traducida a más de 14 idiomas (ES, CA, EN, FR, DE, IT, PT, PL, KO, JA, ZH, RU, TR, HI) con gestión dinámica mediante `TranslationManager`.
+ **Validación de Integridad:** El sistema verifica automáticamente la salud de los archivos de traducción al arrancar para evitar errores de ejecución.
+ **Estimación de Tamaño:** Realiza peticiones `HEAD` paralelas para calcular el peso total de la descarga seleccionada sin descargar los archivos.
+ **Descarga Concurrente Avanzada:** Seguimiento en tiempo real con una barra de progreso global y barras individuales para cada descarga activa.
+ **Filtrado Inteligente:** Motor de búsqueda con **debounce** (300ms) y filtros cruzados por calidad de vídeo e idioma de subtítulos.
+ **Estadísticas Finales:** Resumen detallado al completar las tareas, incluyendo tiempo total, archivos fallidos y acceso directo a la carpeta.

## 🛠️ Requisitos e Instalación

+ **Python 3.7** o superior.
+ **Librerías necesarias:** `customtkinter`, `pillow`, `requests`, `tqdm`.
+ **Aria2 (Opcional):** Para descargas aceleradas mediante el motor externo `aria2c`.

### Instalación de dependencias
```bash
pip install customtkinter pillow requests tqdm
```

### Ejecución
Asegúrate de tener la carpeta `translations/` en el mismo directorio que el ejecutable principal. Si intentas lanzar código inicial (commits 1 a 6, debes tener `tv3_cli.py` también en la misma carpeta)
```bash
python tv3_gui.py
```

## 📖 Guía de Uso

La aplicación se organiza en cuatro secciones principales:

1.  **⚙️ Configuración:** Introduce el `nombonic` del programa (ej: `dr-slump`), selecciona la calidad deseada y el número de hilos (*workers*).
2.  **📋 Lista de Capítulos:** Previsualiza el contenido encontrado. Puedes usar el buscador para filtrar capítulos específicos y marcarlos manualmente para la descarga.
3.  **📊 Progreso:** Monitoriza el estado de las descargas activas y la velocidad de cada archivo de forma individual.
4.  **📜 Logs:** Registro detallado de actividad y red para depuración de posibles errores.

> **Tip:** Puedes usar el botón **"Obtener Tamaños"** para saber cuánto espacio en disco ocupará tu selección antes de iniciar el proceso.

## 📂 Estructura de Salida

La aplicación organiza los archivos de forma inteligente para mantener tu biblioteca ordenada:

+ **Vídeos:** `[Carpeta]/Nombre Serie/Nombre Serie - 1x01 - Título - Calidad.mp4`
+ **Subtítulos:** `[Carpeta]/Nombre Serie/Nombre Serie - 1x01 - Título - Idioma.vtt`
+ **Caché:** Se genera una carpeta `cache/` con metadatos JSON para acelerar búsquedas futuras.

---

## ⚖️ Licencia y Aviso Legal

Este proyecto está bajo la **Licencia MIT**.

**IMPORTANTE:** Esta herramienta ha sido creada exclusivamente con fines educativos y de investigación. El autor no se hace responsable del uso de este software para la descarga de contenido protegido por derechos de autor que infrinja los Términos de Servicio de la plataforma 3Cat. El uso de este software es responsabilidad única y exclusiva del usuario final.

***

**Nota técnica:** El sistema de traducción es robusto; si falta un archivo `.json` o hay errores en las etiquetas, la aplicación utilizará el español como idioma de respaldo (*fallback*) garantizando que nunca se bloquee la interfaz.