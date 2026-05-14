# ⚙️ Setup — Daily Stock Report con GitHub Actions

Guía paso a paso para dejar el sistema funcionando en menos de 15 minutos.

---

## Estructura del repositorio

```
📂 tu-repo/
├── .github/
│   └── workflows/
│       └── daily_stock_report.yml   ← El scheduler de GitHub Actions
├── reportes/                        ← Acá se guardan los reportes generados
│   └── reporte_YYYY-MM-DD.md
├── prompt_llm.md                    ← El prompt para Claude (de tu sistema)
├── guia_usuario.md                  ← Tu guía de configuración
├── run_analysis.py                  ← Genera el reporte via Claude API
├── send_email.py                    ← Envía el reporte por email
├── requirements.txt                 ← Dependencias Python
└── README_setup.md                  ← Este archivo
```

---

## Paso 1 — Crear el repositorio en GitHub

1. Creá un repositorio nuevo en [github.com](https://github.com/new).
2. Puede ser **privado** (recomendado, ya que contiene tu watchlist).
3. Subí todos los archivos de este proyecto al repositorio.

```bash
git init
git add .
git commit -m "Initial setup — Daily Stock Research"
git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
git push -u origin main
```

---

## Paso 2 — Configurar los Secrets

Los Secrets son variables de entorno cifradas que GitHub Actions usa en el workflow. Nunca quedan expuestas en el código.

**Cómo agregarlos:**
1. Abrí tu repo en GitHub.
2. Ir a **Settings → Secrets and variables → Actions → New repository secret**.
3. Agregá los siguientes:

| Secret name        | Valor                                          |
|--------------------|------------------------------------------------|
| `ANTHROPIC_API_KEY`| Tu API key de [console.anthropic.com](https://console.anthropic.com) |
| `EMAIL_SENDER`     | Tu dirección Gmail (ej: `tumail@gmail.com`)    |
| `EMAIL_PASSWORD`   | App Password de Google (ver Paso 3)            |
| `EMAIL_RECIPIENT`  | El email que recibirá el reporte               |

> `EMAIL_SENDER` y `EMAIL_RECIPIENT` pueden ser la misma dirección si te lo enviás a vos mismo.

---

## Paso 3 — Crear un App Password de Gmail

Gmail no permite usar tu contraseña real en scripts. Necesitás un **App Password**:

1. Ir a [myaccount.google.com/security](https://myaccount.google.com/security).
2. Activar **Verificación en dos pasos** (si no la tenés).
3. Ir a [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
4. Crear una nueva contraseña de aplicación:
   - Nombre: `Stock Research Bot` (o el que quieras)
5. Copiá la clave de 16 caracteres generada.
6. Pegala como valor del Secret `EMAIL_PASSWORD` en GitHub.

> ⚠️ Este App Password es distinto a tu contraseña de Gmail. Es seguro usarlo en scripts.

---

## Paso 4 — Verificar el schedule

El workflow está configurado para correr de lunes a viernes a las **21:00 ET** (mercado cerrado).

```yaml
# En .github/workflows/daily_stock_report.yml
schedule:
  - cron: "0 1 * * 2-6"   # 01:00 UTC = 21:00 ET (UTC-4 en verano)
```

**Referencia de zonas horarias:**

| Hora deseada (ET) | Cron en UTC        |
|--------------------|--------------------|
| 17:00 ET (cierre)  | `0 21 * * 1-5`     |
| 18:00 ET           | `0 22 * * 1-5`     |
| 21:00 ET           | `0 1 * * 2-6`      |

> Usá [crontab.guru](https://crontab.guru) para verificar expresiones cron.

---

## Paso 5 — Correr el workflow manualmente (para testear)

Antes de esperar al primer disparo automático, podés testear manualmente:

1. Ir a tu repo → pestaña **Actions**.
2. Seleccionar **📈 Daily Stock Report** en el panel izquierdo.
3. Click en **Run workflow** → seleccionar si querés enviar email → **Run workflow**.
4. Seguí el progreso en tiempo real en la pestaña Actions.

---

## Descargar un reporte generado

Los reportes se guardan en la carpeta `reportes/` del repo y se pueden descargar de tres formas:

### Opción A — Desde GitHub directamente
1. Ir a tu repo → carpeta `reportes/`.
2. Click en el archivo `reporte_YYYY-MM-DD.md`.
3. Click en el ícono de descarga (⬇️) o en **Raw** para ver el texto.

### Opción B — Clonar el repo localmente
```bash
git pull origin main
# El reporte más reciente estará en reportes/reporte_YYYY-MM-DD.md
```

### Opción C — Via email
Si `EMAIL_RECIPIENT` está configurado, el reporte llega a tu bandeja con:
- **Cuerpo HTML** con el reporte formateado.
- **Archivo .md adjunto** para descargar y guardar.

---

## Costos estimados

| Componente          | Costo                                      |
|---------------------|--------------------------------------------|
| GitHub Actions      | **Gratis** (2.000 minutos/mes en plan free)|
| Claude API (Sonnet) | ~$0.05–0.15 por reporte                    |
| Gmail SMTP          | **Gratis**                                 |
| **Total mensual**   | **< $3 USD**                               |

Cada reporte tarda aproximadamente 2–4 minutos en GitHub Actions (incluye setup de Python, llamada a la API y push).

---

## Solución de problemas

| Problema                                | Solución                                                      |
|-----------------------------------------|---------------------------------------------------------------|
| `❌ Error de autenticación` en email    | Verificá que usás App Password, no tu contraseña de Gmail     |
| `❌ No se encontró prompt_llm.md`       | Asegurate de que el archivo esté en la raíz del repo          |
| `❌ APIStatusError 401`                 | Verificá que el Secret `ANTHROPIC_API_KEY` esté bien copiado  |
| El workflow no corre a la hora exacta   | GitHub Actions tiene un delay de 5–15 min en el schedule      |
| El reporte no se commitea al repo       | Verificá que el repo tenga permisos de escritura para Actions  |

### Habilitar permisos de escritura para Actions

Si el paso de commit falla:
1. Ir a **Settings → Actions → General**.
2. En **Workflow permissions**, seleccionar **Read and write permissions**.
3. Guardar.

---

## Personalización avanzada

### Cambiar la watchlist
Editá la tabla en `prompt_llm.md` (sección **LISTA DE ACCIONES A MONITOREAR**) y hacé push. El próximo reporte usará la lista actualizada.

### Agregar múltiples destinatarios de email
En `send_email.py`, cambiá la línea de `sendmail`:
```python
destinatarios = ["email1@ejemplo.com", "email2@ejemplo.com"]
server.sendmail(sender, destinatarios, msg.as_string())
```
Y actualizá el header `To`:
```python
msg["To"] = ", ".join(destinatarios)
```

### Guardar reportes como PDF
Instalá `weasyprint` en `requirements.txt` y convertí el HTML del reporte antes de adjuntarlo. Consultá la documentación de [WeasyPrint](https://weasyprint.org).
