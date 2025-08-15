"""
Vlastní tkinter widgets pro LG ThinQ aplikaci.
Obsahuje LED indikátor a další GUI komponenty.
"""
import tkinter as tk
from tkinter import ttk

class LEDIndicator(ttk.Frame):
    """LED indikátor stavu zařízení"""
    
    def __init__(self, master, size=20, **kwargs):
        super().__init__(master, **kwargs)
        self.size = size
        self.canvas = tk.Canvas(self, width=size*2, height=size*2, bg="#222222", highlightthickness=0)
        self.led = self.canvas.create_oval(2, 2, size*2-2, size*2-2, fill="gray", outline="#444444")
        self.canvas.pack()
        
    def set_state(self, state):
        """Nastavení stavu LED (on, off, error)"""
        if state == "on" or state == "POWER_ON":
            color = "#00ff00"  # Zelená pro zapnuto
        elif state == "off" or state == "POWER_OFF":
            color = "#ff0000"  # Červená pro vypnuto
        elif state == "error":
            color = "#ff8800"  # Oranžová pro chybu
        else:
            color = "#666666"  # Šedá pro neznámý stav
            
        self.canvas.itemconfig(self.led, fill=color)

# Zpětná kompatibilita
class LedIndicator(LEDIndicator):
    """Zpětně kompatibilní alias pro LEDIndicator"""
    pass
