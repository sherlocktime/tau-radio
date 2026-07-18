import tkinter as tk
import json, vlc, os, random
import hashlib, colorsys
import ctypes, subprocess
from datetime import date
from visualizador import AudioVisualizerWindow, SquareGraph

# --- Configuración de rutas ---
carpeta_actual = os.path.dirname(os.path.abspath(__file__))
ruta_json = os.path.join(carpeta_actual, "radios.json")
ruta_icono = os.path.join(carpeta_actual, "icono.png")
ruta_config = os.path.join(carpeta_actual, "reciente.json")

def cargar_estaciones():
    """Lee el archivo JSON con las emisoras y las devuelve ordenadas."""
    try:
        with open(ruta_json, "r", encoding="utf-8") as f:
            estaciones = json.load(f)
        estaciones.sort(key=lambda x: x.get("nombre", "").lower())
        return estaciones
    except FileNotFoundError:
        return [{"nombre": "No se encontró radios.json", "url_streaming": ""}]

ESTACIONES = cargar_estaciones()
SEMILLA = f"{date.today().year}-W{date.today().isocalendar()[1]}"
FUENTE = "Bahnschrift"

def string_to_color(text):
    """Genera un color hexadecimal único y semanal basado en el nombre."""
    h = int(hashlib.md5(f"{SEMILLA}:{text}".encode()).hexdigest()[:8], 16) % 360
    r, g, b = colorsys.hls_to_rgb(h / 360, 0.50, 0.80)
    return f'#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}'


class RadioApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Tau Radio")
        self.root.geometry("280x450")
        self.root.configure(bg="#1e1e1e")
        self.root.resizable(False, True)
        self.root.attributes("-alpha", 0.95)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        if os.path.exists(ruta_icono):
            self.root.iconphoto(False, tk.PhotoImage(file=ruta_icono))

        self.viz_window = None
        self.color_actual = "#d32f2f" 

        try:
            with open(ruta_config, "r", encoding="utf-8") as f:
                self.radio_actual = json.load(f)
        except Exception:
            self.radio_actual = {"nombre": "seleccionar emisora", "url": ""}

        # Inicialización de VLC
        self.instance = vlc.Instance("--quiet")
        self.player = self.instance.media_player_new()

        # --- Interfaz: Zona Superior ---
        top_bar = tk.Frame(root, bg="#1e1e1e")
        top_bar.pack(fill=tk.X, padx=15, pady=9)

        self.status_label = tk.Label(top_bar, text=self.radio_actual["nombre"], fg="#ffffff", bg="#1e1e1e", font=(FUENTE, 12), anchor="w")
        self.status_label.pack(fill=tk.X, expand=True)

        # --- Interfaz: Zona Inferior ---
        bottom_frame = tk.Frame(root, bg="#1e1e1e")
        bottom_frame.pack(fill=tk.X, padx=15, pady=5, side=tk.BOTTOM)

        # Configuramos 4 columnas con el mismo peso
        for i in range(4):
            bottom_frame.columnconfigure(i, weight=1, uniform="botones")

        btn_props = {"bg": "#1e1e1e", "fg": "white", "font": (FUENTE, 10), "bd": 0, "pady": 5}
        
        self.btn_toggle = tk.Button(bottom_frame, text="iniciar", command=self.toggle_reproduccion, **btn_props)
        self.btn_toggle.grid(row=0, column=0, padx=(0, 1), sticky="ew")

        self.btn_random = tk.Button(bottom_frame, text="aleatorio", command=self.reproducir_aleatorio, **btn_props)
        self.btn_random.grid(row=0, column=1, padx=1, sticky="ew")

        self.btn_edit = tk.Button(bottom_frame, text="listado", command=self.editar_json, **btn_props)
        self.btn_edit.grid(row=0, column=2, padx=1, sticky="ew")

        self.btn_viz = tk.Button(bottom_frame, text="visuales", command=self.abrir_visualizador, **btn_props)
        self.btn_viz.grid(row=0, column=3, padx=(1, 0), sticky="ew")

        # --- Interfaz: Zona Central (Scroll) ---
        self.container = tk.Frame(root, bg="#1e1e1e")
        self.container.pack(fill=tk.BOTH, expand=True, padx=15)

        self.canvas = tk.Canvas(self.container, bg="#1e1e1e", highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.scrollable_frame = tk.Frame(self.canvas, bg="#1e1e1e")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        self.root.bind("<FocusIn>", self.on_focus_in)
        self.root.bind("<Double-Button-1>", self.abrir_mezclador)
        
        self.dibujar_botones_estaciones()
        
        if self.radio_actual["url"]:
            self.color_actual = string_to_color(self.radio_actual["nombre"])
            self.status_label.config(text="# " + self.radio_actual["nombre"].upper(), fg=self.color_actual)
            self.actualizar_color_botones(self.color_actual)

    def abrir_mezclador(self, event):
        try:
            subprocess.Popen(["sndvol.exe"])
        except Exception as e:
            print(f"No se pudo abrir el mezclador de volumen: {e}")

    def abrir_visualizador(self):
        """Lanza el visualizador genérico con el motor gráfico de cuadrados."""
        if self.viz_window and tk.Toplevel.winfo_exists(self.viz_window):
            self.viz_window.lift()
        else:
            # Instanciamos la ventana pasándole el "cerebro" gráfico que queremos usar
            self.viz_window = AudioVisualizerWindow( self.root, graph_class=SquareGraph, color=self.color_actual )

    def actualizar_color_botones(self, color):
        self.color_actual = color
        self.btn_toggle.config(fg=color)
        self.btn_random.config(fg=color)
        self.btn_edit.config(fg=color)
        self.btn_viz.config(fg=color)
        
        if self.viz_window and tk.Toplevel.winfo_exists(self.viz_window):
            self.viz_window.cambiar_color(color)

    def dibujar_botones_estaciones(self):
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        for radio in ESTACIONES:
            nombre = radio.get("nombre", "Sin nombre")
            url = radio.get("url_streaming", "")

            if url:
                fila = tk.Frame(self.scrollable_frame, bg="#1e1e1e")
                fila.pack(fill=tk.X, pady=2)

                k = "#4a4a4a" if nombre != self.radio_actual["nombre"] else string_to_color(nombre)
                tk.Frame(fila, bg=k, width=12).pack(side=tk.LEFT, fill=tk.Y)

                btn = tk.Button(
                    fila, text=f"  {nombre}", command=lambda u=url, n=nombre: self.reproducir(u, n),
                    bg="#2d2d2d", fg="#ffffff", activebackground="#4a4a4a", activeforeground="#ffffff",
                    font=(FUENTE, 10), bd=0, anchor="w", pady=1
                )
                btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

                btn.bind("<Enter>", lambda e, b=btn: b.config(bg="#3d3d3d"))
                btn.bind("<Leave>", lambda e, b=btn: b.config(bg="#2d2d2d"))

    def reproducir(self, url, nombre):
        if not url: return
        self.radio_actual = {"nombre": nombre, "url": url}
        
        try:
            with open(ruta_config, "w", encoding="utf-8") as f:
                json.dump(self.radio_actual, f, indent=4)
        except Exception:
            pass
        
        self.player.stop()
        media = self.instance.media_new(url)
        self.player.set_media(media)
        self.player.play()

        k = string_to_color(nombre)
        self.status_label.config(text="# " + nombre.upper(), fg=k) 
        self.btn_toggle.config(text="detener")
        self.actualizar_color_botones(k)
        self.dibujar_botones_estaciones()

    def toggle_reproduccion(self):
        if self.player.is_playing():
            self.player.stop()
            self.status_label.config(text="reproductor detenido", fg="#d32f2f")
            self.btn_toggle.config(text="iniciar")
            self.actualizar_color_botones("#d32f2f")
        else:
            if self.radio_actual["url"]:
                self.reproducir(self.radio_actual["url"], self.radio_actual["nombre"])
            elif ESTACIONES and ESTACIONES[0].get("url_streaming"):
                self.reproducir(ESTACIONES[0].get("url_streaming"), ESTACIONES[0].get("nombre"))

    def reproducir_aleatorio(self):
        annotations = [r for r in ESTACIONES if r.get("url_streaming")]
        if annotations:
            radio_elegida = random.choice(annotations)
            self.reproducir(radio_elegida.get("url_streaming"), radio_elegida.get("nombre"))

    def editar_json(self):
        if not os.path.exists(ruta_json):
            with open(ruta_json, "w", encoding="utf-8") as f:
                json.dump([{"nombre": "Nueva Radio", "url_streaming": ""}], f, indent=4)
        os.startfile(ruta_json)

    def on_focus_in(self, event):
        if event.widget == self.root:
            self.recargar_json_silencioso()

    def recargar_json_silencioso(self):
        global ESTACIONES
        nuevas_estaciones = cargar_estaciones()
        if nuevas_estaciones != ESTACIONES:
            ESTACIONES = nuevas_estaciones
            self.dibujar_botones_estaciones()

    def on_closing(self):
        try:
            self.player.stop()
            self.player.release()
            self.instance.release()
        except Exception:
            pass
        self.root.destroy()

if __name__ == "__main__":
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Tau.RadioApp")
    root = tk.Tk()
    app = RadioApp(root)
    root.mainloop()