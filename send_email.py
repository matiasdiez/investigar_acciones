"""
send_email.py
-------------
Lee el reporte más reciente de /reportes y lo envía por email
via Gmail SMTP. Las credenciales se leen desde variables de entorno.

Variables de entorno requeridas:
  EMAIL_SENDER     — tu dirección Gmail (ej: tumail@gmail.com)
  EMAIL_PASSWORD   — App Password de Google (no tu contraseña real)
  EMAIL_RECIPIENT  — destinatario (puede ser el mismo sender u otro)
"""

import datetime
import os
import pathlib
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# ── Configuración ──────────────────────────────────────────────────────────────

REPORTES_DIR = pathlib.Path("reportes")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# ── Helpers ────────────────────────────────────────────────────────────────────

def obtener_credenciales() -> tuple[str, str, str]:
    sender = os.environ.get("EMAIL_SENDER", "").strip()
    password = os.environ.get("EMAIL_PASSWORD", "").strip()
    recipient = os.environ.get("EMAIL_RECIPIENT", "").strip()

    faltantes = [k for k, v in {
        "EMAIL_SENDER": sender,
        "EMAIL_PASSWORD": password,
        "EMAIL_RECIPIENT": recipient,
    }.items() if not v]

    if faltantes:
        print(f"❌ Variables de entorno faltantes: {', '.join(faltantes)}")
        sys.exit(1)

    return sender, password, recipient


def obtener_reporte_mas_reciente() -> pathlib.Path:
    reportes = sorted(REPORTES_DIR.glob("reporte_*.md"), reverse=True)
    if not reportes:
        print(f"❌ No se encontraron reportes en {REPORTES_DIR}/")
        sys.exit(1)
    return reportes[0]


def markdown_a_html(texto: str) -> str:
    """
    Conversión mínima de Markdown a HTML para el cuerpo del email.
    Para producción, podés usar la librería `markdown` (pip install markdown).
    """
    try:
        import markdown
        return markdown.markdown(texto, extensions=["tables", "fenced_code"])
    except ImportError:
        # Fallback: envolver en <pre> si markdown no está instalado
        texto_escapado = texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"<pre style='font-family: monospace; font-size: 13px;'>{texto_escapado}</pre>"


def construir_email(
    sender: str,
    recipient: str,
    fecha: str,
    contenido_md: str,
    ruta_adjunto: pathlib.Path,
) -> MIMEMultipart:

    msg = MIMEMultipart("alternative")
    msg["From"] = f"Stock Research Bot <{sender}>"
    msg["To"] = recipient
    msg["Subject"] = f"📈 Daily Stock Report — {fecha}"

    # Cuerpo en texto plano (fallback)
    texto_plano = f"Reporte diario de acciones — {fecha}\n\n{contenido_md}"
    msg.attach(MIMEText(texto_plano, "plain", "utf-8"))

    # Cuerpo en HTML con estilos mínimos
    html_body = f"""
    <html>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                   max-width: 860px; margin: auto; padding: 24px; color: #1a1a1a;">
        <div style="background: #f0f4ff; border-left: 4px solid #3b6dd6;
                    padding: 16px 20px; border-radius: 6px; margin-bottom: 24px;">
          <h2 style="margin: 0 0 4px;">📈 Daily Stock Report</h2>
          <p style="margin: 0; color: #555; font-size: 14px;">{fecha} · Wall Street (NYSE / NASDAQ)</p>
        </div>
        <div style="line-height: 1.7; font-size: 15px;">
          {markdown_a_html(contenido_md)}
        </div>
        <hr style="border: none; border-top: 1px solid #e0e0e0; margin: 32px 0;">
        <p style="color: #999; font-size: 12px;">
          Generado automáticamente por GitHub Actions · Solo para fines informativos ·
          No constituye asesoramiento financiero.
        </p>
      </body>
    </html>
    """
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Adjunto: el archivo .md original
    with open(ruta_adjunto, "rb") as f:
        adjunto = MIMEBase("application", "octet-stream")
        adjunto.set_payload(f.read())
    encoders.encode_base64(adjunto)
    adjunto.add_header(
        "Content-Disposition",
        f"attachment; filename={ruta_adjunto.name}"
    )
    msg.attach(adjunto)

    return msg


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    hoy = datetime.date.today()
    fecha_legible = hoy.strftime("%d de %B de %Y")

    print(f"📧 Preparando envío de email — {fecha_legible}")

    sender, password, recipient = obtener_credenciales()
    ruta_reporte = obtener_reporte_mas_reciente()
    contenido = ruta_reporte.read_text(encoding="utf-8")

    print(f"📄 Reporte a enviar: {ruta_reporte.name} ({len(contenido):,} caracteres)")

    msg = construir_email(sender, recipient, fecha_legible, contenido, ruta_reporte)

    print(f"🔌 Conectando a {SMTP_HOST}:{SMTP_PORT}...")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        print("❌ Error de autenticación. Verificá EMAIL_SENDER y EMAIL_PASSWORD.")
        print("   Asegurate de usar un App Password de Google, no tu contraseña real.")
        sys.exit(1)
    except smtplib.SMTPException as e:
        print(f"❌ Error SMTP: {e}")
        sys.exit(1)

    print(f"✅ Email enviado a {recipient}")


if __name__ == "__main__":
    main()