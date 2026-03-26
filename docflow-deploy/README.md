# DocFlow Pro — Guía de Despliegue Gratuito

Convierte PDFs a Word preservando el diseño. Funciona con PDFs protegidos con contraseña o con restricciones.

---

## ¿Qué necesitas?
- Cuenta en **GitHub** (gratis) → https://github.com
- Cuenta en **Render.com** (gratis, entra con Google) → https://render.com

**Tiempo estimado: 20–30 minutos**

---

## PASO 1 — Subir el código a GitHub

1. Ve a https://github.com y entra a tu cuenta
2. Haz clic en el botón verde **"New"** (arriba a la izquierda)
3. En **Repository name** escribe: `docflow-pro`
4. Selecciona **Private** (para que nadie más vea tu código)
5. Haz clic en **"Create repository"**
6. En la página siguiente, haz clic en **"uploading an existing file"**
7. **Arrastra TODOS estos archivos** al área de carga:
   - `server.py`
   - `requirements.txt`
   - `Dockerfile`
   - `render.yaml`
   - La carpeta `static/` con el archivo `index.html` dentro
8. Escribe un mensaje como "primer commit" y haz clic en **"Commit changes"**

✅ Tu código ya está en GitHub.

---

## PASO 2 — Desplegar en Render.com (gratis)

1. Ve a https://render.com
2. Haz clic en **"Get Started for Free"**
3. Selecciona **"Sign in with Google"** (usa tu cuenta de Google)
4. Una vez dentro, haz clic en **"New +"** → selecciona **"Web Service"**
5. Selecciona **"Connect a repository"**
6. Haz clic en **"Connect GitHub"** y autoriza a Render
7. Busca y selecciona tu repositorio `docflow-pro`
8. Render detectará el `Dockerfile` automáticamente. Verifica que diga:
   - **Name:** `docflow-pro` (o el nombre que quieras)
   - **Instance Type:** `Free`
   - **Branch:** `main`
9. Haz clic en **"Create Web Service"**

⏳ Render construirá la app (esto tarda 5–10 minutos la primera vez, instala LibreOffice).

---

## PASO 3 — Obtener tu URL

Una vez que el deploy termine (verás `Live` en verde), Render te dará una URL como:

```
https://docflow-pro.onrender.com
```

¡Esa es tu URL! Compártela con tus clientes.

---

## Notas importantes

**Plan gratuito de Render:**
- La app se "duerme" si nadie la usa por 15 minutos
- La primera visita después del sueño tarda ~30 segundos en cargar
- Para evitar esto, puedes usar un servicio como https://uptimerobot.com (gratis) que la "pinga" cada 10 minutos

**Límites:**
- 50 MB máximo por archivo PDF
- Plan gratuito incluye 750 horas/mes (suficiente para uso normal)

**Si necesitas más capacidad:**
- Plan Starter de Render: $7/mes, sin límite de tiempo activo

---

## ¿Problemas?

Si el deploy falla, revisa los logs en Render haciendo clic en **"Logs"** en tu servicio. El error más común es de memoria — si ocurre, escribe al soporte de Render o contacta al desarrollador.

---

## Actualizar la app

Si necesitas hacer cambios:
1. Edita los archivos en GitHub directamente
2. Render re-desplegará automáticamente en 2–3 minutos

---

*DocFlow Pro — Desarrollado con LibreOffice + qpdf + Flask*
