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


def recopilar_contexto_macro(fecha: str) -> str:
    """Busca solo el contexto macroeconómico."""
    print("🔍 Buscando datos de mercado macro con DuckDuckGo...")
    bloques = [f"# Datos de mercado recopilados — {fecha}\n"]
    with DDGS() as ddgs:
        try:
            macro = ddgs.text("S&P 500 market today Wall Street", max_results=3)
            macro_txt = "\n".join(h.get("body", "") for h in macro)
            bloques.append(f"## Contexto macro\n{macro_txt}\n")
            time.sleep(0.5)
        except Exception as e:
            bloques.append(f"## Contexto macro\n[Error: {e}]\n")
    return "\n".join(bloques)


def recopilar_contexto_tickers(tickers: list) -> str:
    """Busca datos solo para un subgrupo de tickers."""
    bloques = []
    with DDGS() as ddgs:
        for ticker in tickers:
            print(f"   ↳ {ticker}...")
            datos = buscar_ticker(ddgs, ticker)
            bloques.append(f"## {ticker}\n{datos}\n")
    return "\n".join(bloques)


# ── Llamada a Groq ─────────────────────────────────────────────────────────────

def generar_analisis_parcial(client: Groq, prompt_base: str, contexto_macro: str, contexto_tickers: str, fecha: str, tickers_chunk: list) -> str:
    """Genera el análisis solo para un grupo de acciones (evita límite de tokens)."""
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

{contexto_macro}

{contexto_tickers}

---

## INSTRUCCIÓN FINAL (PROCESAMIENTO EN BLOQUES)

- Fecha del reporte: {fecha}
- ESTA ES UNA EJECUCIÓN PARCIAL. Solo debes analizar los siguientes instrumentos: {', '.join(tickers_chunk)}.
- Ignora el resto de los instrumentos de la watchlist.
- Genera SOLO la sección "## 📊 ANÁLISIS POR INSTRUMENTO" para estos {len(tickers_chunk)} tickers, sin incluir la introducción macro, alertas prioritarias, resumen ejecutivo ni disclaimer.
- Usa exactamente el formato indicado para cada ticker.
"""

    print(f"🤖 Enviando análisis parcial a Groq para {', '.join(tickers_chunk)}...")
    inicio = time.time()
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=2048, # Límite menor para reportes parciales
        temperature=TEMPERATURA,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
    )
    elapsed = time.time() - inicio
    uso = response.usage
    print(f"✅ Respuesta parcial recibida en {elapsed:.1f}s")
    print(f"   Tokens — prompt: {uso.prompt_tokens:,} | completion: {uso.completion_tokens:,} | total: {uso.total_tokens:,}")

    return response.choices[0].message.content


def _extraer_seccion_formato(prompt_base: str) -> str:
    """Extrae solo la sección de formato de salida del prompt base para reducir tokens."""
    # Busca el bloque de formato de salida para no enviar todo el prompt en la síntesis
    marcadores = ["## FORMATO DEL REPORTE DE SALIDA", "## FORMATO DE SALIDA", "## Formato de salida", "# FORMATO", "## OUTPUT", "## SALIDA"]
    for marcador in marcadores:
        idx = prompt_base.find(marcador)
        if idx != -1:
            return prompt_base[idx:]
    # Si no encuentra un marcador, devuelve los últimos 3000 caracteres (sección de formato suele estar al final)
    return prompt_base[-3000:]


def generar_reporte_final(client: Groq, prompt_base: str, contexto_macro: str, analisis_previo: str, fecha: str) -> str:
    """Toma los análisis parciales y genera la síntesis final del reporte completo."""
    system_prompt = (
        "Eres un analista financiero senior especializado en Wall Street. "
        "Respondés siempre en español y seguís estrictamente las instrucciones."
    )

    # Usar solo la sección de formato para reducir tokens de prompt
    formato_salida = _extraer_seccion_formato(prompt_base)
    # Limitar contexto macro a los primeros 1500 caracteres para ahorrar tokens
    contexto_macro_corto = contexto_macro[:1500] + "..." if len(contexto_macro) > 1500 else contexto_macro

    user_message = f"""## INSTRUCCIONES DE FORMATO Y SALIDA

{formato_salida}

---

## CONTEXTO MACRO RESUMIDO ({fecha})

{contexto_macro_corto}

---

## ANÁLISIS PREVIO POR INSTRUMENTO

Los siguientes análisis fueron generados previamente para cada instrumento de la watchlist:

{analisis_previo}

---

## INSTRUCCIÓN FINAL (SÍNTESIS COMPLETA)

- Fecha del reporte: {fecha}
- Basado en el "Contexto Macro" y el "Análisis previo", tu tarea es generar las secciones restantes del reporte y unificar todo.
- Genera el reporte COMPLETO con el formato exacto de salida indicado arriba.
- Para la sección "## 📊 ANÁLISIS POR INSTRUMENTO", copia y adapta levemente la información que se te proveyó en el Análisis Previo (debes incluir la información de todos los {len(WATCHLIST)} instrumentos analizados).
- Extrae el veredicto de cada instrumento del Análisis Previo para construir el Resumen Ejecutivo.
"""

    print(f"🤖 Enviando síntesis final a Groq ({MODEL})...")
    inicio = time.time()
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=3500,  # Reducido de 4096 para dejar margen al prompt
        temperature=TEMPERATURA,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
    )
    elapsed = time.time() - inicio
    uso = response.usage
    print(f"✅ Reporte final recibido en {elapsed:.1f}s")
    print(f"   Tokens — prompt: {uso.prompt_tokens:,} | completion: {uso.completion_tokens:,} | total: {uso.total_tokens:,}")

    return response.choices[0].message.content


# ── Persistencia ───────────────────────────────────────────────────────────────

def guardar_reporte(contenido: str, fecha: str) -> pathlib.Path:
    REPORTES_DIR.mkdir(exist_ok=True)
    ruta = REPORTES_DIR / f"reporte_{fecha}.md"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


# ── Main ───────────────────────────────────────────────────────────────────────

def chunk_list(lista, n):
    for i in range(0, len(lista), n):
        yield lista[i:i + n]


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

    # 1. Recopilar contexto macro
    contexto_macro = recopilar_contexto_macro(fecha_leg)

    client = Groq(api_key=api_key)
    analisis_parciales = []

    # 2. Procesar en bloques para evitar Rate Limits
    # Separar watchlist en bloques de 3
    chunks = list(chunk_list(WATCHLIST, 3))
    for i, chunk in enumerate(chunks):
        print(f"\n📦 Procesando bloque {i+1}/{len(chunks)}: {', '.join(chunk)}")
        contexto_chunk = recopilar_contexto_tickers(chunk)
        
        reporte_parcial = generar_analisis_parcial(
            client, prompt_base, contexto_macro, contexto_chunk, fecha_leg, chunk
        )
        analisis_parciales.append(reporte_parcial)
        
        # Pausa de 60 segundos entre llamados a la API de Groq para evitar Rate Limit (TPM)
        if i < len(chunks) - 1:
            print("⏳ Pausa de 60s para resetear los tokens de Groq (TPM limit)...")
            time.sleep(60)

    # 3. Síntesis final
    print("\n⏳ Pausa de 60s antes de la síntesis final...")
    time.sleep(60)
    
    analisis_unidos = "\n\n".join(analisis_parciales)
    reporte_final = generar_reporte_final(client, prompt_base, contexto_macro, analisis_unidos, fecha_leg)

    # 4. Guardar
    ruta = guardar_reporte(reporte_final, fecha_str)
    print(f"\n💾 Reporte guardado en: {ruta}")
    print("=" * 55)
    print("✅ Análisis completado.\n")


if __name__ == "__main__":
    main()