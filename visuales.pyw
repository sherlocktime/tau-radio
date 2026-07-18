import tkinter as tk
from tkinter import ttk
import threading
import queue
from collections import deque
import numpy as np
import soundcard as sc

class SquareVisualizer(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        
        # 1. Quitar la barra de título y bordes
        self.overrideredirect(True)
        self.configure(bg="#111")
        
        # Dimensiones
        self.canvas_size = 260
        self.geometry("280x280")
        self.resizable(False, False)
        
        # Centrar el visualizador respecto a la ventana padre
        self.center_on_parent(parent)

        # Canvas cuadrado sin bordes molestos
        self.canvas = tk.Canvas(self, bg="#111", width=self.canvas_size, height=self.canvas_size, highlightthickness=0)
        self.canvas.pack(pady=10, padx=10)
        self.center = self.canvas_size // 2
        
        # 2. Permitir arrastrar la ventana sin bordes (Clic Izquierdo + Arrastrar)
        self.canvas.bind("<Button-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        
        # 3. Métodos alternativos para cerrar (Clic Derecho o tecla Esc)
        self.canvas.bind("<Button-3>", lambda e: self.on_close())
        self.bind("<Escape>", lambda e: self.on_close())
        
        # Delay e Historiales
        self.history_size = 15
        self.volume_history = deque([0.0] * self.history_size, maxlen=self.history_size)
        self.peak_history = deque([0.01] * 120, maxlen=120)
        
        # Renderizado de figuras
        tono = "crimson"
        self.square_outer = self.canvas.create_rectangle(0, 0, 0, 0, outline=tono, width=3)
        self.square_mid = self.canvas.create_rectangle(0, 0, 0, 0, outline=tono, width=2)
        self.square_inner = self.canvas.create_rectangle(0, 0, 0, 0, outline=tono, width=1)

        # Cruz central
        d = 20
        self.canvas.create_line(self.center-d, self.center, self.center+d, self.center, fill=tono, width=1)
        self.canvas.create_line(self.center, self.center-d, self.center, self.center+d, fill=tono, width=1)

        # Radio actual
        self.r_inner_curr = 20
        self.r_mid_curr = 20
        self.r_outer_curr = 20
        
        # Cola e hilo de audio
        self.audio_queue = queue.Queue()
        self.running = True
        
        self.audio_thread = threading.Thread(target=self.capture_audio, daemon=True)
        self.audio_thread.start()
        
        self.update_visuals()

    def center_on_parent(self, parent):
        """Calcula la posición para centrar el visualizador sobre la ventana padre"""
        parent.update_idletasks()
        p_x = parent.winfo_rootx()
        p_y = parent.winfo_rooty()
        p_w = parent.winfo_width()
        p_h = parent.winfo_height()
        
        # Centro relativo
        x = p_x + (p_w // 2) - 140
        y = p_y + (p_h // 2) - 140
        self.geometry(f"280x280+{max(0, x)}+{max(0, y)}")

    def start_drag(self, event):
        """Registra la posición inicial del clic para arrastrar"""
        self._drag_x = event.x
        self._drag_y = event.y

    def drag(self, event):
        """Calcula el desplazamiento y mueve la ventana"""
        deltax = event.x - self._drag_x
        deltay = event.y - self._drag_y
        x = self.winfo_x() + deltax
        y = self.winfo_y() + deltay
        self.geometry(f"+{x}+{y}")

    def capture_audio(self):
        try:
            mics = sc.all_microphones(include_loopback=True)
            if not mics:
                print("No se encontraron dispositivos de loopback de audio.")
                return
            speaker_loopback = mics[0]
        except Exception as e:
            print(f"Error al inicializar audio: {e}")
            return

        # Escuchamos de forma segura comprobando el estado de 'running'
        try:
            with speaker_loopback.recorder(samplerate=44100, blocksize=1024) as mic:
                while self.running:
                    data = mic.record(numframes=1024)
                    # Si dejamos de correr durante el record, salimos inmediatamente
                    if not self.running:
                        break
                    rms = np.sqrt(np.mean(data**2))
                    self.audio_queue.put(rms)
        except Exception as e:
            print(f"Error en la captura de audio: {e}")

    def draw_square(self, square_id, half_side):
        x0 = self.center - half_side
        y0 = self.center - half_side
        x1 = self.center + half_side
        y1 = self.center + half_side
        self.canvas.coords(square_id, x0, y0, x1, y1)

    def update_visuals(self):
        if not self.running:
            return
        
        volume = 0
        while not self.audio_queue.empty():
            volume = self.audio_queue.get()
            
        self.volume_history.appendleft(volume)
        self.peak_history.append(volume)
        
        vol_inner = self.volume_history[0]
        vol_mid = self.volume_history[6]
        vol_outer = self.volume_history[12]
        
        base_size = 10
        max_limit = 130  # Ajustado ligeramente para evitar que salga del canvas
        
        recent_peak = max(self.peak_history)
        if recent_peak < 0.005: 
            recent_peak = 0.005
            
        dynamic_scale_factor = max_limit / recent_peak
        dynamic_scale_factor = min(dynamic_scale_factor, 5000)
        
        r_inner_target = base_size + min(int(vol_inner * dynamic_scale_factor), max_limit)
        r_mid_target = base_size + min(int(vol_mid * dynamic_scale_factor * 0.9), max_limit) 
        r_outer_target = base_size + min(int(vol_outer * dynamic_scale_factor * 0.80), max_limit)
        
        decay = 0.82  # Suavizado ligeramente más reactivo
        
        if r_inner_target > self.r_inner_curr: self.r_inner_curr = r_inner_target
        else: self.r_inner_curr = self.r_inner_curr * decay + r_inner_target * (1 - decay)

        if r_mid_target > self.r_mid_curr: self.r_mid_curr = r_mid_target
        else: self.r_mid_curr = self.r_mid_curr * decay + r_mid_target * (1 - decay)

        if r_outer_target > self.r_outer_curr: self.r_outer_curr = r_outer_target
        else: self.r_outer_curr = self.r_outer_curr * decay + r_outer_target * (1 - decay)
        
        self.draw_square(self.square_inner, int(self.r_inner_curr))
        self.draw_square(self.square_mid, int(self.r_mid_curr))
        self.draw_square(self.square_outer, int(self.r_outer_curr))

        self.after(25, self.update_visuals)

    def on_close(self):
        self.running = False
        # Limpiamos la cola para desbloquear cualquier recurso
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break
        self.destroy()

# --- Integración de prueba ---
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Radio App")
    root.geometry("300x150")
    
    # Estilo básico para la ventana principal
    root.configure(bg="#222")
    style = ttk.Style()
    style.theme_use("clam")
    
    btn = ttk.Button(root, text="Lanzar Visualizador", command=lambda: SquareVisualizer(root))
    btn.pack(expand=True, pady=20)
    
    root.mainloop()