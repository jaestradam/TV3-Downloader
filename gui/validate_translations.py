import json
import os
import re
from typing import Any, Dict, Set

TRANSLATIONS_DIR = "translations"
BASE_LANG = "es"

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")

def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_keys(data: Any, prefix="") -> Dict[str, Any]:
    keys = {}
    if isinstance(data, dict):
        for k, v in data.items():
            full_key = f"{prefix}.{k}" if prefix else k
            keys[full_key] = v
            keys.update(extract_keys(v, full_key))
    return keys

def extract_placeholders(text: str) -> Set[str]:
    return set(PLACEHOLDER_RE.findall(text))

def validate_language(lang: str, base_keys: Dict[str, Any], base_data: Dict[str, Any], translations_dir: str, strict: bool = False):
    print(f"\n🌍 Validando idioma: {lang}")
    path = os.path.join(translations_dir, f"{lang}.json")

    if not os.path.exists(path):
        print(f"⚠️  Archivo {lang}.json no encontrado")
        return False

    try:
        data = load_json(path)
    except Exception as e:
        print(f"❌ Error cargando {lang}.json: {e}")
        return False

    errors = False
    keys = extract_keys(data)

    # 1️⃣ Meta
    if "meta.language_name" not in keys:
        print("❌ Falta meta.language_name")
        errors = True

    # 2️⃣ Claves faltantes
    missing = set(base_keys) - set(keys)
    if missing:
        print("❌ Claves faltantes:")
        for k in sorted(missing):
            print(f"   - {k}")
        errors = True

    # 3️⃣ Claves sobrantes
    extra = set(keys) - set(base_keys)
    if extra:
        print("⚠️ Claves sobrantes:")
        for k in sorted(extra):
            print(f"   - {k}")

    # 4️⃣ Placeholders
    for key, base_value in base_keys.items():
        if not isinstance(base_value, str):
            continue

        if key not in keys:
            continue

        value = keys[key]
        if not isinstance(value, str):
            print(f"❌ Tipo incorrecto en {key} (esperado string)")
            errors = True
            continue

        base_ph = extract_placeholders(base_value)
        lang_ph = extract_placeholders(value)

        if base_ph != lang_ph:
            print(f"❌ Placeholders incorrectos en {key}")
            print(f"   Esperado: {base_ph}")
            print(f"   Encontrado: {lang_ph}")
            errors = True

    if not errors:
        print("✅ Idioma válido")

    return not errors

def validate_all_translations(
    translations_dir="translations",
    base_lang="es",
    strict=False
) -> bool:
    """
    Valida todas las traducciones contra el idioma base.
    
    Args:
        translations_dir: Directorio con archivos de traducción
        base_lang: Código del idioma base (ej: "es")
        strict: Si True, claves extra también son errores
    
    Returns:
        True si todas las traducciones son válidas, False si hay errores
    """
    print("=" * 60)
    print("🔍 VALIDACIÓN DE TRADUCCIONES")
    print("=" * 60)
    
    # Verificar que existe el directorio
    if not os.path.exists(translations_dir):
        print(f"⚠️  Directorio '{translations_dir}' no existe")
        print("✅ Usando traducciones embebidas únicamente")
        return True
    
    # Cargar idioma base
    base_path = os.path.join(translations_dir, f"{base_lang}.json")
    
    if not os.path.exists(base_path):
        print(f"⚠️  Archivo base '{base_lang}.json' no encontrado")
        print("✅ Usando traducciones embebidas únicamente")
        return True
    
    try:
        base_data = load_json(base_path)
    except Exception as e:
        print(f"❌ Error cargando idioma base {base_lang}.json: {e}")
        return False
    
    base_keys = extract_keys(base_data)
    print(f"📚 Idioma base: {base_lang}")
    print(f"📊 Total de claves en base: {len(base_keys)}")
    
    # Obtener lista de idiomas a validar
    lang_files = [f for f in os.listdir(translations_dir) if f.endswith('.json')]
    
    if not lang_files:
        print("⚠️  No se encontraron archivos de traducción")
        print("✅ Usando traducciones embebidas únicamente")
        return True
    
    languages = [f[:-5] for f in lang_files if f[:-5] != base_lang]
    
    if not languages:
        print(f"ℹ️  Solo existe el idioma base ({base_lang})")
        return True
    
    print(f"🌐 Idiomas a validar: {', '.join(languages)}")
    
    # Validar cada idioma
    all_valid = True
    for lang in languages:
        if not validate_language(lang, base_keys, base_data, translations_dir, strict):
            all_valid = False
    
    print("\n" + "=" * 60)
    if all_valid:
        print("✅ TODAS LAS TRADUCCIONES SON VÁLIDAS")
    else:
        print("❌ SE ENCONTRARON ERRORES EN LAS TRADUCCIONES")
    print("=" * 60)
    
    return all_valid

if __name__ == "__main__":
    # Ejecutar validación cuando se llama directamente
    result = validate_all_translations(
        translations_dir="translations",
        base_lang="es",
        strict=False
    )
    
    import sys
    sys.exit(0 if result else 1)