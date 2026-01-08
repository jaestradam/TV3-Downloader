# 3Cat CLI Downloader

Este script es una herramienta avanzada y automatizada para descargar contenidos (vídeos y subtítulos) de la plataforma 3Cat / TV3. Ha evolucionado desde un simple extractor basado en scraping hasta una herramienta profesional con soporte para concurrencia, gestión de caché, reanudación de descargas y autogestión de dependencias.

## 🚀 Características Principales
+    Autoinstalación: El script detecta si faltan librerías (requests, tqdm) e intenta instalarlas automáticamente.
+    API Oficial: Utiliza la API de 3Cat para obtener metadatos precisos (Temporadas, Capítulos, Títulos).
+    Descarga Concurrente: Utiliza múltiples hilos para acelerar tanto la obtención de enlaces como la descarga de archivos.
+    Sistema de Resume: Soporta la reanudación de descargas interrumpidas mediante archivos .part y cabeceras HTTP Range.
+    Caché Local: Guarda la información de los capítulos en archivos JSON locales para evitar peticiones innecesarias a la API.
+    Integración con aria2: Si tienes aria2c instalado, el script puede delegarle las descargas para obtener la máxima velocidad posible.

## 🛠️ Requisitos e Instalación
+    Python 3.7 o superior.
+    Dependencias: Se instalan solas al ejecutar el script por primera vez.
+    Aria2 (Opcional): Si deseas usar el motor de descarga externo, asegúrate de tenerlo en tu PATH.


### Clonar el repositorio
```
git clone https://github.com/tu-usuario/tv3-downloader.git
cd tv3-downloader
```

## 📖 Manual de Uso

La sintaxis básica es:

>python tv3_cli.py "nombre-del-programa" [argumentos]

Argumentos del CLI
| Argumento        | Descripción           | Valor por defecto  |
| ---------------- | --------------------- | ------------------ |
| programa      | (Obligatorio) El nombonic del programa (ej: dr-slump, plats-bruts). | - |
| --csv | Nombre del archivo CSV de salida con todos los enlaces. | links-fitxers.csv |
| --manifest | Nombre del archivo JSON con los metadatos completos. | manifest.json |
| --workers | Número de hilos simultáneos para descarga y API. | 8 |
| --pagesize | Número de capítulos a pedir por página a la API. | 100 |
| --quality | Filtrar por calidad: 720p o 480p. | Todas |
| --no-vtt | Si se activa, no descargará los archivos de subtítulos. | False |
| --only-list | Solo genera el CSV/Manifest, no inicia la descarga. | False |
| --use-aria2 | Utiliza el motor aria2c para las descargas. | False |
| --resume | Reanuda descargas detectando archivos .part. | False |
| --output | Carpeta raíz donde se guardarán los archivos. | .\\. |
| --debug | Muestra logs detallados de red y errores. | False |

### Ejemplo de uso avanzado:

Descargar el programa "Dr. Slump" en 720p, usando 12 hilos, guardando todo en una carpeta llamada "Series" y activando la reanudación automática:
Bash

>python tv3_cli.py dr-slump --quality 720p --workers 12 --output "./Series" --resume

##📂 Estructura de Salida
El script organiza los archivos de forma inteligente:
+    Videos: [Output]/Nombre Programa/Nombre Programa - 1x01 - Titulo.mp4
+    Subtítulos: [Output]/Nombre Programa/Nombre Programa - 1x01 - Titulo.vtt
+    Metadata: Se crea una carpeta cache/ con las respuestas de la API para acelerar futuras ejecuciones.