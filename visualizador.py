import tkinter as tk
from tkinter import ttk
import threading
import queue
from collections import deque
import numpy as np
import soundcard as sc

# =====================================================================
# 1. MOTORES DE DIBUJO (Graficadores)
# =====================================================================

class SquareGraph:
    """Motor de renderizado para los cuadrados concéntricos."""
    def __init__(self, canvas, center, color="crimson"):
        self.canvas = canvas
        self.center = center
        self.color = color
        
        # Crear figuras iniciales
        self.square_outer = self.canvas.create_rectangle(0, 0, 0, 0, outline=color, width=3)
        self.square_mid = self.canvas.create_rectangle(0, 0, 0, 0, outline=color, width=2)
        self.square_inner = self.canvas.create_rectangle(0, 0, 0, 0, outline=color, width=1)
        
        # Cruz central
        d = 20
        self.line_h = self.canvas.create_line(self.center-d, self.center, self.center+d, self.center, fill=color, width=1)
        self.line_v = self.canvas.create_line(self.center, self.center-d, self.center, self.center+d, fill=color, width=1)

        # Historiales y estados de animación específicos de este gráfico
        self.history_size = 15
        self.volume_history = deque([0.0] * self.history_size, maxlen=self.history_size)
        
        self.r_inner_curr = 20
        self.r_mid_curr = 20
        self.r_outer_curr = 20

    def cambiar_color(self, nuevo_color):
        self.color = nuevo_color
        self.canvas.itemconfig(self.square_outer, outline=nuevo_color)
        self.canvas.itemconfig(self.square_mid, outline=nuevo_color)
        self.canvas.itemconfig(self.square_inner, outline=nuevo_color)
        self.canvas.itemconfig(self.line_h, fill=nuevo_color)
        self.canvas.itemconfig(self.line_v, fill=nuevo_color)

    def _draw_square(self, square_id, half_side):
        x0 = self.center - half_side
        y0 = self.center - half_side
        x1 = self.center + half_side
        y1 = self.center + half_side
        self.canvas.coords(square_id, x0, y0, x1, y1)

    def draw(self, volume, recent_peak):
        """Procesa el volumen actual y redibuja."""
        self.volume_history.appendleft(volume)
        
        vol_inner = self.volume_history[0]
        vol_mid = self.volume_history[6]
        vol_outer = self.volume_history[12]
        
        base_size = 10
        max_limit = 130
        
        if recent_peak < 0.005: 
            recent_peak = 0.005
            
        dynamic_scale_factor = min(max_limit / recent_peak, 5000)
        
        r_inner_target = base_size + min(int(vol_inner * dynamic_scale_factor), max_limit)
        r_mid_target = base_size + min(int(vol_mid * dynamic_scale_factor * 0.9), max_limit) 
        r_outer_target = base_size + min(int(vol_outer * dynamic_scale_factor * 0.80), max_limit)
        
        decay = 0.82
        
        if r_inner_target > self.r_inner_curr: self.r_inner_curr = r_inner_target
        else: self.r_inner_curr = self.r_inner_curr * decay + r_inner_target * (1 - decay)

        if r_mid_target > self.r_mid_curr: self.r_mid_curr = r_mid_target
        else: self.r_mid_curr = self.r_mid_curr * decay + r_mid_target * (1 - decay)

        if r_outer_target > self.r_outer_curr: self.r_outer_curr = r_outer_target
        else: self.r_outer_curr = self.r_outer_curr * decay + r_outer_target * (1 - decay)
        
        self._draw_square(self.square_inner, int(self.r_inner_curr))
        self._draw_square(self.square_mid, int(self.r_mid_curr))
        self._draw_square(self.square_outer, int(self.r_outer_curr))


# =====================================================================
# 2. CONTENEDOR PRINCIPAL (Ventana y Audio)
# =====================================================================

class AudioVisualizerWindow(tk.Toplevel):
    def __init__(self, parent, graph_class, color="crimson"):
        super().__init__(parent)
        
        self.overrideredirect(True)
        self.configure(bg="#111")
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.95)
        
        self.canvas_size = 260
        self.geometry("280x280")
        self.resizable(False, False)
        self.center_on_parent(parent)

        self.canvas = tk.Canvas(self, bg="#111", width=self.canvas_size, height=self.canvas_size, highlightthickness=0)
        self.canvas.pack(pady=10, padx=10)
        self.center = self.canvas_size // 2
        
        # Eventos de ventana
        self.canvas.bind("<Button-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<Button-3>", lambda e: self.on_close())
        self.bind("<Escape>", lambda e: self.on_close())
        
        # Historial general de picos de audio
        self.peak_history = deque([0.01] * 120, maxlen=120)
        
        # --- INYECCIÓN DEL MOTOR DE GRÁFICOS ---
        # Instanciamos la clase de dibujo que nos pasaron por parámetro
        self.graph = graph_class(self.canvas, self.center, color)
        
        # Hilo de audio
        self.audio_queue = queue.Queue()
        self.running = True
        self.audio_thread = threading.Thread(target=self.capture_audio, daemon=True)
        self.audio_thread.start()
        
        self.update_visuals()

    def cambiar_color(self, nuevo_color):
        """Redirige la orden de cambio de color al motor gráfico activo."""
        if hasattr(self, 'graph') and hasattr(self.graph, 'cambiar_color'):
            self.graph.cambiar_color(nuevo_color)

    def center_on_parent(self, parent):
        parent.update_idletasks()
        p_x = parent.winfo_rootx()
        p_y = parent.winfo_rooty()
        p_w = parent.winfo_width()
        p_h = parent.winfo_height()
        x = p_x + (p_w // 2) - 140
        y = p_y + (p_h // 2) - 140
        self.geometry(f"280x280+{max(0, x)}+{max(0, y)}")

    def start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def drag(self, event):
        deltax = event.x - self._drag_x
        deltay = event.y - self._drag_y
        self.geometry(f"+{self.winfo_x() + deltax}+{self.winfo_y() + deltay}")

    def capture_audio(self):
        try:
            mics = sc.all_microphones(include_loopback=True)
            if not mics: return
            speaker_loopback = mics[0]
        except Exception: return

        try:
            with speaker_loopback.recorder(samplerate=44100, blocksize=2048) as mic:
                while self.running:
                    data = mic.record(numframes=2048)
                    if not self.running: break
                    rms = np.sqrt(np.mean(data**2))
                    self.audio_queue.put(rms)
        except Exception: pass

    def update_visuals(self):
        if not self.running: return
        
        volume = 0
        while not self.audio_queue.empty():
            volume = self.audio_queue.get()
            
        self.peak_history.append(volume)
        recent_peak = max(self.peak_history)
        
        # Delegar el dibujo en nuestro motor gráfico
        self.graph.draw(volume, recent_peak)

        self.after(25, self.update_visuals)

    def on_close(self):
        self.running = False
        while not self.audio_queue.empty():
            try: self.audio_queue.get_nowait()
            except queue.Empty: break
        self.destroy()


# =====================================================================
# 3. EJECUCIÓN (Ejemplo de uso)
# =====================================================================
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Radio App")
    root.geometry("280x280")
    root.configure(bg="#222")
    
    # Invocamos pasándole la clase SquareGraph como el motor visualizador
    btn = ttk.Button(
        root, 
        text="Lanzar Cuadrados", 
        command=lambda: AudioVisualizerWindow(root, graph_class=SquareGraph, color="orchid")
    )
    btn.pack(expand=True, pady=20)
    
    root.mainloop()