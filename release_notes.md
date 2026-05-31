# Crescendo v1.5.0 - Servidor & VPK

¡Bienvenido a la versión oficial de **Crescendo**! Esta entrega incluye el instalador para la PlayStation Vita y el paquete del servidor de sincronización para PC listo para su distribución.

---

## 🎮 Aplicación Vita (Crescendo.vpk)
* Reproductor de música moderno y estilizado para PS Vita.
* Sincronización local fluida e integración directa con tu servidor de PC.

## 💻 Servidor para PC (Crescendo-Servidor.zip)
El servidor permite organizar tu colección local, además de buscar y descargar música en segundo plano a la máxima calidad disponible.

### Componentes incluidos en el ZIP:
* **`Crescendo-Servidor.bat`**: Script de inicio rápido optimizado para Windows (soporta caracteres UTF-8/Unicode).
* **`sync_server.py`**: Servidor de sincronización y API en Python.
* **`Spotify.cfg`**: Plantilla lista para que coloques tus claves de desarrollador de Spotify.
* **`instructions.txt`**: Guía rápida y detallada de uso en inglés.

---

## 🛠️ Instrucciones de Inicio Rápido

### En la PlayStation Vita:
1. Transfiere e instala **`Crescendo.vpk`** usando VitaShell.

### En la PC:
1. Asegúrate de tener **Python 3.x** instalado.
2. Descomprime **`Crescendo-Servidor.zip`**.
3. (Opcional pero Recomendado) Ejecuta en tu consola:
   ```bash
   pip install spotdl SpotiFLAC
   ```
4. (Opcional) Abre `Spotify.cfg` con el bloc de notas y coloca tus credenciales si quieres búsqueda a través de Spotify.
5. Ejecuta **`Crescendo-Servidor.bat`** con doble clic.
6. Configura la dirección IP y el puerto que muestra la ventana de tu PC dentro de la aplicación en la PS Vita.
