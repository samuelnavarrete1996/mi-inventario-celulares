# Guía de Acceso Remoto y Despliegue 24/7
## Mi Inventario - Samuel Navarrete (Celulares)

Tienes 3 formas de acceder a tu sistema según tus necesidades:

---

### Opción 1: Acceso Inmediato desde tu Celular en el mismo Wi-Fi
*(Ideal para usar tu teléfono como terminal POS dentro de tu tienda o casa)*

1. Ejecuta el archivo `iniciar_servidor.bat` en tu computadora.
2. Asegúrate de que tu celular esté conectado a la misma red Wi-Fi que la computadora.
3. Abre el navegador de tu celular (Chrome o Safari) e ingresa la dirección:
   ```text
   http://192.168.1.66:8000
   ```
4. ¡Listo! Puedes registrar celulares, vender con el carrito y consultar stock directamente desde tu teléfono.

---

### Opción 2: Acceso desde Cualquier Lugar con Enlace Seguro de Internet (Cloudflare Tunnel)
*(Ideal para entrar desde la calle con datos 4G/5G, desde otra ciudad o compartir el enlace con un colaborador sin pagar nada)*

1. En la carpeta del proyecto, haz doble clic en:
   ```text
   iniciar_con_acceso_publico.bat
   ```
2. La ventana iniciará el sistema y generará automáticamente un enlace seguro con candado HTTPS tipo:
   ```text
   https://tu-enlace-unico.trycloudflare.com
   ```
3. Guarda ese enlace en los marcadores de tu celular o envíatelo por WhatsApp.
4. Podrás entrar desde cualquier lugar del mundo mientras tu computadora permanezca encendida con esa ventana abierta.

---

### Opción 3: Servidor en la Nube 24/7 (Siempre Funciona, incluso con tu PC Apagada)
*(La solución definitiva para tener tu negocio disponible todo el año en la nube sin gastar luz ni batería de tu computadora)*

Hemos dejado el proyecto 100% configurado con `Dockerfile`, `Procfile` y `render.yaml`. Puedes montarlo gratis en plataformas como **Render** o **Railway**:

#### Pasos para subirlo a Render.com (Gratis):
1. **Crear repositorio en GitHub:**
   - Entra a [github.com](https://github.com) y crea una cuenta si no tienes una.
   - Crea un nuevo repositorio (por ejemplo: `mi-inventario-celulares`).
   - Sube todos los archivos de esta carpeta.
2. **Crear cuenta en Render:**
   - Entra a [render.com](https://render.com) e inicia sesión con tu cuenta de GitHub.
3. **Crear Web Service:**
   - Haz clic en **"New"** > **"Web Service"**.
   - Selecciona tu repositorio `mi-inventario-celulares`.
   - Render detectará automáticamente la configuración de Python / Docker.
   - En *Environment*, asegúrate de tener:
     - `PORT`: `10000`
     - `HOST`: `0.0.0.0`
     - `AUTO_OPEN_BROWSER`: `0`
4. **Obtener tu URL fija:**
   - Render te asignará un enlace permanente gratuito como:
     `https://mi-inventario-samuel.onrender.com`
   - Ese enlace estará encendido 24/7 y podrás agregarlo como icono en la pantalla de inicio de tu celular como si fuera una aplicación instalada.
