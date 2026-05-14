"""
run_analysis.py
---------------
Genera el reporte diario de acciones usando:
  - Groq API (gratuito) con el modelo llama-3.3-70b
  - DuckDuckGo Search (gratuito, sin API key) para datos actualizados

Flujo:
  1. Para cada ticker, busca noticias y datos del día en DuckDuckGo
  2. Consolida los resultados en un contexto estructurado
  3. Envía el contexto + prompt_llm.md a Groq para generar el reporte
  4. Guarda el reporte en /reportes/reporte_YYYY-MM-DD.md
"""

import datetime
import os
import pathlib
import sys
import time

from groq import Groq
from duckduckgo_search import DDGS

# ── Configuración ──────────────────────────────────────────────────────────────

PROMPT_FILE   = pathlib.Path("prompt_llm.md")
REPORTES_DIR  = pathlib.Path("reportes")
MODEL         = "llama-3.3-70b-versatile"
MAX_TOKENS    = 4096
TEMPERATURA   = 0.2   # Bajo para maximizar precisión en análisis financiero

WATCHLIST = ["AAPL", "AMZN", "BIOX", "BRK.B", "GLD", "KO", "NVDA", "SPY", "XLU"]

# Búsquedas por ticker: qué consultar en DuckDuckGo
QUERIES_POR_TICKER = [
    "{ticker} stock price today",
    "{ticker} stock news today",
    "{ticker} analyst rating target price 2026",
]

# Para GLD también buscar fuentes especializadas en oro
QUERIES_EXTRA_GLD = [
    "gold price today spot XAU USD",
    "Jesse Colombo gold analysis 2026",
    "GLD ETF flows institutional 2026",
]

# ── Búsqueda web ───────────────────────────────────────────────────────────────

def buscar_ticker(ddgs: DDGS, ticker: str) -> str:
    """Busca noticias y datos de mercado para un ticker. Retorna texto consolidado."""
    resultados = []
    queries = [q.format(ticker=ticker) for q in QUERIES_POR_TICKER]

    if ticker == "GLD":
        queries += QUERIES_EXTRA_GLD

    for query in queries:
        try:
            hits = ddgs.text(query, max_results=3)
            for hit in hits:
                resultados.append(
                    f"[{hit.get('title', '')}]\n{hit.get('body', '')}\nFuente: {hit.get('href', '')}"
                )
            time.sleep(0.5)  # Pausa entre búsquedas para no saturar
        except Exception as e:
            resultados.append(f"[Error en búsqueda '{query}': {e}]")

    return "\n\n".join(resultados) if resultados else "Sin resultados."


def recopilar_contexto_mercado(fecha: str) -> str:
    """Ejecuta todas las búsquedas y arma el bloque de contexto para el LLM."""
    print("🔍 Buscando datos de mercado con DuckDuckGo...")
    bloques = [f"# Datos de mercado recopilados — {fecha}\n"]

    with DDGS() as ddgs:
        # Contexto macro general
        print("   ↳ Contexto macro del día...")
        try:
            macro = ddgs.text("S&P 500 market today Wall Street", max_results=3)
            macro_txt = "\n".join(h.get("body", "") for h in macro)
            bloques.append(f"## Contexto macro\n{macro_txt}\n")
            time.sleep(0.5)
        except Exception as e:
            bloques.append(f"## Contexto macro\n[Error: {e}]\n")

        # Datos por ticker
        for ticker in WATCHLIST:
            print(f"   ↳ {ticker}...")
            datos = buscar_ticker(ddgs, ticker)
            bloques.append(f"## {ticker}\n{datos}\n")

    return "\n".join(bloques)


# ── Llamada a Groq ─────────────────────────────────────────────────────────────

def generar_reporte(client: Groq, prompt_base: str, contexto: str, fecha: str) -> str:
    """Envía el prompt + contexto a Groq y retorna el reporte generado."""

    system_prompt = (
        "Eres un analista financiero senior especializado en Wall Street. "
        "Seguís estrictamente el protocolo de análisis definido por el usuario. "
        "Respondés siempre en español. "
        "Nunca inventás datos: si no encontrás información concreta en el contexto provisto, "
        "indicalo explícitamente con '⚠️ Dato no disponible'."
    )

    user_message = f"""{prompt_base}

---

## CONTEXTO DE MERCADO RECOPILADO HOY ({fecha})

A continuación se incluyen los datos de mercado obtenidos de búsquedas web
realizadas hoy. Usá esta información como base principal para el análisis.
Podés complementar con tu conocimiento hasta tu fecha de corte, pero priorizá
siempre los datos del contexto cuando haya diferencias.

{contexto}

---

## INSTRUCCIÓN FINAL

- Fecha del reporte: {fecha}
- Ejecutá el análisis completo de todos los instrumentos de la watchlist.
- Producí el reporte con exactamente el formato de salida definido en el prompt.
- Si algún dato no está disponible en el contexto, marcalo con ⚠️ en lugar de inventarlo.
"""

    print(f"🤖 Enviando análisis a Groq ({MODEL})...")
    inicio = time.time()

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURA,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
    )

    elapsed = time.time() - inicio
    uso = response.usage
    print(f"✅ Respuesta recibida en {elapsed:.1f}s")
    print(f"   Tokens — prompt: {uso.prompt_tokens:,} | completion: {uso.completion_tokens:,} | total: {uso.total_tokens:,}")

    return response.choices[0].message.content


# ── Persistencia ───────────────────────────────────────────────────────────────

def guardar_reporte(contenido: str, fecha: str) -> pathlib.Path:
    REPORTES_DIR.mkdir(exist_ok=True)
    ruta = REPORTES_DIR / f"reporte_{fecha}.md"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    hoy         = datetime.date.today()
    fecha_str   = hoy.strftime("%Y-%m-%d")
    fecha_leg   = hoy.strftime("%d de %B de %Y")

    print(f"\n🚀 Iniciando análisis diario — {fecha_leg}")
    print("=" * 55)

    # Verificar API key
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        print("❌ Variable de entorno GROQ_API_KEY no encontrada.")
        sys.exit(1)

    # Leer prompt base
    if not PROMPT_FILE.exists():
        print(f"❌ No se encontró {PROMPT_FILE}.")
        sys.exit(1)
    prompt_base = PROMPT_FILE.read_text(encoding="utf-8")
    print(f"✅ Prompt cargado ({len(prompt_base):,} caracteres)")

    # Recopilar contexto de mercado con DuckDuckGo
    contexto = recopilar_contexto_mercado(fecha_leg)
    print(f"✅ Contexto recopilado ({len(contexto):,} caracteres)")

    # Generar reporte con Groq
    client  = Groq(api_key=api_key)
    reporte = generar_reporte(client, prompt_base, contexto, fecha_leg)

    # Guardar
    ruta = guardar_reporte(reporte, fecha_str)
    print(f"💾 Reporte guardado en: {ruta}")
    print("=" * 55)
    print("✅ Análisis completado.\n")


if __name__ == "__main__":
    main()