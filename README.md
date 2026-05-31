# Crescendo - Servidor de Sincronización (VitaMusic)

Este proyecto es un servidor de sincronización y buscador de música local/online diseñado para la aplicación **Crescendo** / **VitaMusic** en la PlayStation Vita. Permite buscar, descargar canciones de alta calidad en la red local y transmitirlas/sincronizarlas directamente a la consola.

---

## 🚀 Características

- **Sincronización en red local (LAN):** Servidor HTTP liviano sin autenticación para transferencias rápidas y estables.
- **Buscador Online Integrado:** 
  - Búsqueda en **iTunes API** (rápido y con soporte de metadatos).
  - Integración con **Spotify** (utilizando `spotdl` para metadatos y búsqueda).
- **Descargas en segundo plano:**
  - Descarga en formato **FLAC (Lossless)** usando `SpotiFLAC` (Deezer, Qobuz, Tidal fallback).
  - Descarga en formato **MP3 (320kbps)** usando `spotdl` desde YouTube Music.
- **Optimizado para Windows:** Script `.bat` listo para usarse con soporte para rutas unicode y codificación UTF-8.

---

## 📦 Requisitos

1. **Python 3.x** instalado. Asegúrate de marcar la casilla **"Add Python to PATH"** durante la instalación.
2. Dependencias de Python opcionales (pero recomendadas para las descargas):
   ```bash
   pip install spotdl SpotiFLAC
   ```

---

## 🛠️ Uso en Windows

1. Descarga el repositorio o clónalo.
2. Edita `VitaMusic-Servidor.bat` si deseas cambiar el puerto por defecto (`8787`) o asignar una carpeta de música predeterminada en `MUSIC_DIR`.
3. Ejecuta **`VitaMusic-Servidor.bat`** haciendo doble clic.
4. Conecta tu PlayStation Vita al servidor ingresando la IP de tu PC y el puerto correspondiente en la aplicación.

> [!TIP]
> Si deseas usar la búsqueda e integración de Spotify, crea un archivo llamado `Spotify.cfg` en el mismo directorio (o copia `Spotify.cfg.example`) y completa tus credenciales `client_id` y `client_secret` obtenidas desde el panel de desarrolladores de Spotify.

---

## 🌐 Endpoints de la API

El servidor expone los siguientes endpoints en la red local:

| Método | Endpoint | Descripción |
|---|---|---|
| `GET` | `/ping` | Verifica si el servidor está en línea (devuelve `ok`). |
| `GET` | `/list` | Devuelve una lista en formato JSON de todas las canciones en la carpeta de música. |
| `GET` | `/search?q=<consulta>` | Busca canciones utilizando Spotify (vía `spotdl`) o iTunes API. |
| `GET` | `/download?url=<url>&fmt=<format>` | Inicia la descarga en background de una URL de Spotify/iTunes en formato `flac` o `mp3`. |
| `GET` | `/dlstatus?job=<id>` | Obtiene el estado actual del proceso de descarga en segundo plano. |
| `GET` | `/file?name=<archivo>` | Descarga el archivo de audio especificado. |

---

## 🔒 Seguridad y Configuración

El archivo `Spotify.cfg` contiene credenciales sensibles y se encuentra en el archivo `.gitignore` para evitar ser subido a repositorios públicos por accidente. Utiliza `Spotify.cfg.example` como plantilla para tus despliegues locales.
