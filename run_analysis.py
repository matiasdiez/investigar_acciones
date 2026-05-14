"""
run_analysis.py
---------------
Genera el reporte diario de acciones usando:
  - Groq API (gratuito) con el modelo llama-3.3-70b
  - DuckDuckGo Search (gratuito, sin API key) para datos actualizados

Flujo:
  1. Para cada ticker (en bloques de 3), busca noticias y datos del día en DuckDuckGo
  2. Envía cada bloque a Groq para generar el análisis por instrumento
  3. Python ensambla el reporte final directamente (sin un llamado de síntesis extra)
  4. Groq genera solo 3 secciones cortas: contexto macro, alertas y resumen ejecutivo
  5. Guarda el reporte en /reportes/reporte_YYYY-MM-DD.md
"""

import datetime
import os
import pathlib
import sys
import time

from groq import Groq
from ddgs import DDGS

# ── Configuración ──────────────────────────────────────────────────────────────

PROMPT_FILE   = pathlib.Path("prompt_llm.md")
REPORTES_DIR  = pathlib.Path("reportes")
MODEL         = "llama-3.3-70b-versatile"
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

    if not resultados:
        print(f"   ⚠️  Sin resultados de búsqueda para {ticker}")
        return "Sin resultados de búsqueda."
    return "\n\n".join(resultados)


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


# ── Llamadas a Groq ────────────────────────────────────────────────────────────

def _llamar_groq(client: Groq, system: str, user: str, max_tokens: int, etiqueta: str) -> str:
    """Wrapper genérico para llamadas a Groq con logging de tokens."""
    inicio = time.time()
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=max_tokens,
        temperature=TEMPERATURA,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    elapsed = time.time() - inicio
    uso = response.usage
    print(f"✅ {etiqueta} recibido en {elapsed:.1f}s")
    print(f"   Tokens — prompt: {uso.prompt_tokens:,} | completion: {uso.completion_tokens:,} | total: {uso.total_tokens:,}")
    return response.choices[0].message.content


def _extraer_instrucciones_analisis(prompt_base: str) -> str:
    """Extrae solo las instrucciones de análisis (Pasos 1–7) sin el bloque de formato de salida.
    Esto evita que el modelo genere el header completo del reporte en los análisis parciales."""
    marcador_formato = "## FORMATO DEL REPORTE DE SALIDA"
    idx = prompt_base.find(marcador_formato)
    if idx != -1:
        return prompt_base[:idx].strip()
    return prompt_base


def generar_analisis_parcial(client: Groq, prompt_base: str, contexto_macro: str, contexto_tickers: str, fecha: str, tickers_chunk: list) -> str:
    """Genera el análisis solo para un grupo de acciones (evita límite de tokens)."""
    system_prompt = (
        "Eres un analista financiero senior especializado en Wall Street. "
        "Seguís estrictamente el protocolo de análisis definido por el usuario. "
        "Respondés siempre en español. "
        "Nunca inventás datos: si no encontrás información concreta en el contexto provisto, "
        "indicalo explícitamente con '⚠️ Dato no disponible'."
    )

    # Solo pasar instrucciones de análisis, NO el bloque de formato de salida
    # Esto evita que el modelo genere el header completo del reporte
    instrucciones = _extraer_instrucciones_analisis(prompt_base)

    user_message = f"""{instrucciones}

---

## CONTEXTO DE MERCADO RECOPILADO HOY ({fecha})

{contexto_macro}

{contexto_tickers}

---

## INSTRUCCIÓN FINAL (PROCESAMIENTO EN BLOQUES)

- Fecha del reporte: {fecha}
- ESTA ES UNA EJECUCIÓN PARCIAL. Solo debes analizar los siguientes instrumentos: {', '.join(tickers_chunk)}.
- Ignora el resto de los instrumentos de la watchlist.
- Genera SOLO los bloques de análisis para estos {len(tickers_chunk)} tickers.
- Comenzá directamente con "### {tickers_chunk[0]} —" sin ningún encabezado previo.
- No incluyas introducción macro, alertas prioritarias, resumen ejecutivo, disclaimer ni el header del reporte.
- Usá exactamente el formato de análisis por instrumento indicado arriba para cada ticker.
"""

    print(f"🤖 Enviando análisis parcial a Groq para {', '.join(tickers_chunk)}...")
    return _llamar_groq(client, system_prompt, user_message, max_tokens=2048, etiqueta="Análisis parcial")


def generar_contexto_macro_texto(client: Groq, contexto_raw: str, fecha: str) -> str:
    """Genera el párrafo de contexto macro (sección pequeña, ~200 tokens de completion)."""
    system_prompt = (
        "Eres un analista financiero senior. Respondés siempre en español. "
        "Nunca inventás datos: usá solo la información provista."
    )
    user_message = f"""Con base en los siguientes datos de mercado del día, redactá un párrafo conciso de 3 a 5 oraciones 
para la sección "## 🌍 CONTEXTO MACRO DEL DÍA" del reporte. 
Incluí performance del S&P 500 / SPY, tasas, dólar y cualquier dato macro relevante.
No uses encabezados, solo el texto del párrafo.

DATOS:
{contexto_raw[:2000]}

Fecha: {fecha}
"""
    print("🤖 Generando contexto macro...")
    return _llamar_groq(client, system_prompt, user_message, max_tokens=400, etiqueta="Contexto macro")


def generar_alertas(client: Groq, analisis_unidos: str, fecha: str) -> str:
    """Genera las alertas prioritarias (sección pequeña, ~150 tokens de completion)."""
    system_prompt = (
        "Eres un analista financiero senior. Respondés siempre en español. "
        "Nunca inventás datos: usá solo la información provista."
    )
    # Resumir análisis para no exceder el límite: extraer solo los veredictos
    lineas_veredicto = [l for l in analisis_unidos.split("\n") if "Veredicto" in l or "Razón:" in l or "### " in l]
    resumen_veredictos = "\n".join(lineas_veredicto[:60])  # Máximo 60 líneas

    user_message = f"""Con base en los siguientes veredictos y análisis, listá las 3 a 5 alertas más urgentes o relevantes del día.
Formato: numeradas del 1 al 5, con emoji 🔴/🟢/🟡 según impacto, ticker en mayúsculas y descripción breve en una línea.
No incluyas encabezados, solo la lista.

VEREDICTOS:
{resumen_veredictos}

Fecha: {fecha}
"""
    print("🤖 Generando alertas prioritarias...")
    return _llamar_groq(client, system_prompt, user_message, max_tokens=300, etiqueta="Alertas")


def generar_resumen_ejecutivo(client: Groq, analisis_unidos: str, fecha: str) -> str:
    """Genera la tabla del resumen ejecutivo (sección pequeña, ~200 tokens de completion)."""
    system_prompt = (
        "Eres un analista financiero senior. Respondés siempre en español. "
        "Nunca inventás datos: usá solo la información provista."
    )
    # Extraer solo líneas relevantes para el resumen
    lineas_relevantes = [l for l in analisis_unidos.split("\n") 
                         if "### " in l or "Precio actual" in l or "Variación diaria" in l 
                         or "Veredicto" in l or "Razón:" in l]
    resumen = "\n".join(lineas_relevantes[:80])

    user_message = f"""Con base en el siguiente análisis, generá la tabla del Resumen Ejecutivo.
La tabla debe tener exactamente estas columnas: Ticker | Precio | Var. Diaria | Veredicto | Catalizador Principal
Incluí una fila por cada uno de los 9 tickers: AAPL, AMZN, BIOX, BRK.B, GLD, KO, NVDA, SPY, XLU.
Usá los emojis de veredicto: 🟢 Mantener / 🔴 Reducir / 🔵 Acumular / ⚪ Observar.
Si no tenés el dato exacto de precio o variación, usá "⚠️ N/D".
Devolvé SOLO la tabla markdown, sin texto adicional.

ANÁLISIS:
{resumen}

Fecha: {fecha}
"""
    print("🤖 Generando resumen ejecutivo...")
    return _llamar_groq(client, system_prompt, user_message, max_tokens=400, etiqueta="Resumen ejecutivo")


# ── Ensamblado del reporte ─────────────────────────────────────────────────────

def ensamblar_reporte(fecha_leg: str, contexto_macro_texto: str, alertas: str, analisis_unidos: str, resumen_ejecutivo: str) -> str:
    """Ensambla el reporte final en Python, sin depender de Groq para el formato completo."""
    disclaimer = (
        "Este reporte es generado por un modelo de lenguaje con fines informativos y educativos.\n"
        "No constituye asesoramiento financiero. Consultá a un asesor matriculado antes de invertir."
    )

    return f"""# 📈 Daily Stock Report — {fecha_leg}
Mercado de referencia: Wall Street (NYSE / NASDAQ)

---

## 🌍 CONTEXTO MACRO DEL DÍA
{contexto_macro_texto}

---

## ⚡ ALERTAS PRIORITARIAS
{alertas}

---

## 📊 ANÁLISIS POR INSTRUMENTO

{analisis_unidos}

---

## 📌 RESUMEN EJECUTIVO

{resumen_ejecutivo}

---

## ⚠️ DISCLAIMER
{disclaimer}
"""


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

    # 1. Recopilar contexto macro (solo búsqueda web, sin Groq todavía)
    contexto_macro_raw = recopilar_contexto_macro(fecha_leg)

    client = Groq(api_key=api_key)
    analisis_parciales = []

    # 2. Procesar en bloques de 3 tickers para evitar Rate Limits
    chunks = list(chunk_list(WATCHLIST, 3))
    for i, chunk in enumerate(chunks):
        print(f"\n📦 Procesando bloque {i+1}/{len(chunks)}: {', '.join(chunk)}")
        contexto_chunk = recopilar_contexto_tickers(chunk)

        reporte_parcial = generar_analisis_parcial(
            client, prompt_base, contexto_macro_raw, contexto_chunk, fecha_leg, chunk
        )
        analisis_parciales.append(reporte_parcial)

        # Pausa de 60 segundos entre llamados a la API de Groq para evitar Rate Limit (TPM)
        if i < len(chunks) - 1:
            print("⏳ Pausa de 60s para resetear los tokens de Groq (TPM limit)...")
            time.sleep(60)

    analisis_unidos = "\n\n---\n\n".join(analisis_parciales)

    # 3. Generar las 3 secciones cortas (cada una en llamado separado con pausa)
    print("\n⏳ Pausa de 60s antes de las secciones finales...")
    time.sleep(60)
    contexto_macro_texto = generar_contexto_macro_texto(client, contexto_macro_raw, fecha_leg)

    print("⏳ Pausa de 30s...")
    time.sleep(30)
    alertas = generar_alertas(client, analisis_unidos, fecha_leg)

    print("⏳ Pausa de 30s...")
    time.sleep(30)
    resumen_ejecutivo = generar_resumen_ejecutivo(client, analisis_unidos, fecha_leg)

    # 4. Ensamblar reporte en Python (sin llamado adicional a Groq)
    reporte_final = ensamblar_reporte(fecha_leg, contexto_macro_texto, alertas, analisis_unidos, resumen_ejecutivo)

    # 5. Guardar
    ruta = guardar_reporte(reporte_final, fecha_str)
    print(f"\n💾 Reporte guardado en: {ruta}")
    print("=" * 55)
    print("✅ Análisis completado.\n")


if __name__ == "__main__":
    main()