"""
run_analysis.py
---------------
Llama a la Claude API con web_search habilitado, usando prompt_llm.md
como instrucción base, y guarda el reporte en la carpeta /reportes.
"""

import anthropic
import datetime
import pathlib
import sys
import time

# ── Configuración ──────────────────────────────────────────────────────────────

PROMPT_FILE = pathlib.Path("prompt_llm.md")
REPORTES_DIR = pathlib.Path("reportes")
MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 4096

# Zona horaria de referencia para el encabezado del reporte
TZ_LABEL = "ET (Eastern Time, Nueva York)"

# ── Helpers ────────────────────────────────────────────────────────────────────

def leer_prompt() -> str:
    if not PROMPT_FILE.exists():
        print(f"❌ No se encontró {PROMPT_FILE}. Verificá la estructura del repo.")
        sys.exit(1)
    return PROMPT_FILE.read_text(encoding="utf-8")


def construir_mensaje(prompt_base: str, fecha: str) -> str:
    return f"""{prompt_base}

---

## INSTRUCCIONES DE EJECUCIÓN PARA HOY

- Fecha de hoy: {fecha}
- Zona horaria de referencia: {TZ_LABEL}
- El mercado de Nueva York ya cerró. Usá datos del cierre de hoy.
- Buscá información actualizada en la web antes de responder.
- Ejecutá el análisis completo de todos los instrumentos de la watchlist.
- Producí el reporte con el formato de salida definido en este prompt.
"""


def extraer_texto(response: anthropic.types.Message) -> str:
    partes = [block.text for block in response.content if block.type == "text"]
    if not partes:
        print("⚠️  La respuesta no contiene bloques de texto.")
        return ""
    return "\n".join(partes)


def guardar_reporte(contenido: str, fecha: str) -> pathlib.Path:
    REPORTES_DIR.mkdir(exist_ok=True)
    nombre = REPORTES_DIR / f"reporte_{fecha}.md"
    nombre.write_text(contenido, encoding="utf-8")
    return nombre


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    hoy = datetime.date.today()
    fecha_str = hoy.strftime("%Y-%m-%d")
    fecha_legible = hoy.strftime("%d de %B de %Y")

    print(f"🚀 Iniciando análisis diario — {fecha_legible}")

    # Leer prompt base
    prompt_base = leer_prompt()
    print(f"✅ Prompt cargado desde {PROMPT_FILE} ({len(prompt_base):,} caracteres)")

    # Construir mensaje completo
    mensaje = construir_mensaje(prompt_base, fecha_legible)

    # Llamar a la API
    client = anthropic.Anthropic()  # Lee ANTHROPIC_API_KEY del entorno automáticamente

    print("⏳ Llamando a Claude API con web_search...")
    inicio = time.time()

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            tools=[
                {
                    "type": "web_search_20250305",
                    "name": "web_search",
                }
            ],
            messages=[
                {"role": "user", "content": mensaje}
            ],
        )
    except anthropic.APIConnectionError:
        print("❌ Error de conexión con la API de Anthropic.")
        sys.exit(1)
    except anthropic.RateLimitError:
        print("❌ Rate limit alcanzado. Intentá de nuevo en unos minutos.")
        sys.exit(1)
    except anthropic.APIStatusError as e:
        print(f"❌ Error de API: {e.status_code} — {e.message}")
        sys.exit(1)

    elapsed = time.time() - inicio
    print(f"✅ Respuesta recibida en {elapsed:.1f}s")
    print(f"   Tokens usados — input: {response.usage.input_tokens:,} | output: {response.usage.output_tokens:,}")

    # Extraer y guardar el reporte
    contenido = extraer_texto(response)
    if not contenido:
        print("❌ No se pudo extraer contenido del reporte.")
        sys.exit(1)

    ruta = guardar_reporte(contenido, fecha_str)
    print(f"💾 Reporte guardado en: {ruta}")
    print("✅ Análisis completado.")


if __name__ == "__main__":
    main()
