# -*- coding: utf-8 -*-
"""
Modul pro správu a zobrazení plánovače klimatizace.
Umožňuje vytváření časových plánů s různými režimy a nastaveními.
"""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime, time
import json
import os
from typing import List, Dict, Any

class ScheduleEntry:
    """Třída reprezentující jeden záznam v plánu"""
    
    def __init__(self, name: str = "", start_time: str = "08:00", 
                 end_time: str = "10:00", mode: str = "FAN", temperature: int = 22, 
                 wind: str = "AUTO", power_on: bool = True, power_off_at_end: bool = True):
        self.name = name
        self.start_time = start_time
        self.end_time = end_time
        self.mode = mode
        self.temperature = temperature
        self.wind = wind
        self.power_on = power_on
        self.power_off_at_end = power_off_at_end  # Vypnout na konci plánu
        self.enabled = True
        
        # Zpětná kompatibilita - pokud je zadána jen délka
        self.duration_hours = self._calculate_duration_hours()
        
    def _calculate_duration_hours(self) -> float:
        """Výpočet délky trvání z časů start a end"""
        try:
            start = datetime.strptime(self.start_time, "%H:%M").time()
            end = datetime.strptime(self.end_time, "%H:%M").time()
            
            # Převod na minuty pro výpočet
            start_minutes = start.hour * 60 + start.minute
            end_minutes = end.hour * 60 + end.minute
            
            # Pokud end_time je menší než start_time, předpokládáme přes půlnoc
            if end_minutes <= start_minutes:
                end_minutes += 24 * 60  # Přidat 24 hodin
            
            duration_minutes = end_minutes - start_minutes
            return round(duration_minutes / 60.0, 2)
        except:
            return 2.0  # Výchozí 2 hodiny
        
    def _calculate_end_time_from_duration(self, duration_hours: float) -> str:
        """
        Vypočítá end_time z start_time a délky trvání.

        Args:
            duration_hours: Délka trvání v hodinách (může být desetinné číslo)

        Returns:
            str: Čas konce ve formátu HH:MM
        """
        try:
            from datetime import timedelta
            start = datetime.strptime(self.start_time, "%H:%M")
            total_minutes = int(duration_hours * 60)
            # timedelta zvládne přechod přes půlnoc bez ValueError
            end = (start + timedelta(minutes=total_minutes))
            # Oříznutí na rozsah 0-23h pomocí modulo (přes půlnoc)
            end_minutes_total = (start.hour * 60 + start.minute + total_minutes) % (24 * 60)
            return f"{end_minutes_total // 60:02d}:{end_minutes_total % 60:02d}"
        except Exception:
            return "10:00"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "mode": self.mode,
            "temperature": self.temperature,
            "wind": self.wind,
            "power_on": self.power_on,
            "power_off_at_end": getattr(self, 'power_off_at_end', True),
            "enabled": self.enabled,
            # Zpětná kompatibilita
            "time": self.start_time,
            "duration_hours": self.duration_hours
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScheduleEntry':
        """Vytvoření instance z dict s podporou starého i nového formátu"""
        # Nový formát s start_time a end_time
        if "start_time" in data and "end_time" in data:
            entry = cls(
                name=data.get("name", ""),
                start_time=data.get("start_time", "08:00"),
                end_time=data.get("end_time", "10:00"),
                mode=data.get("mode", "FAN"),
                temperature=data.get("temperature", 22),
                wind=data.get("wind", "AUTO"),
                power_on=data.get("power_on", True),
                power_off_at_end=data.get("power_off_at_end", True)
            )
        else:
            # Starý formát - převést duration_hours na end_time
            start_time = data.get("time", "08:00")
            duration_hours = data.get("duration_hours", 2)
            
            entry = cls(
                name=data.get("name", ""),
                start_time=start_time,
                end_time="10:00",  # Dočasně
                mode=data.get("mode", "FAN"),
                temperature=data.get("temperature", 22),
                wind=data.get("wind", "AUTO"),
                power_on=data.get("power_on", True),
                power_off_at_end=data.get("power_off_at_end", True)
            )
            
            # Vypočítat end_time z duration
            entry.end_time = entry._calculate_end_time_from_duration(duration_hours)
        
        entry.enabled = data.get("enabled", True)
        return entry

class SchedulerWidget(ttk.Frame):
    """Widget pro správu časového plánu"""
    
    def __init__(self, parent, modes: List[str], wind_options: List[str], 
                 on_schedule_change=None):
        super().__init__(parent)
        self.modes = modes
        self.wind_options = wind_options
        self.on_schedule_change = on_schedule_change
        self.schedule_file = "data/schedule.json"
        self.schedule_entries: List[ScheduleEntry] = []
        
        self.create_widgets()
        self.load_schedule()
        
    def create_widgets(self):
        """Vytvoření GUI pro plánovač"""
        # Hlavní label frame
        main_frame = ttk.LabelFrame(self, text="📅 Časový plánovač", padding=10)
        main_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Tlačítka pro správu
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(0, 10))
        
        self.add_btn = ttk.Button(btn_frame, text="➕ Přidat plán", command=self.add_schedule_entry)
        self.add_btn.pack(side="left", padx=2)
        
        self.edit_btn = ttk.Button(btn_frame, text="✏️ Upravit", command=self.edit_selected)
        self.edit_btn.pack(side="left", padx=2)
        
        self.delete_btn = ttk.Button(btn_frame, text="🗑️ Smazat", command=self.delete_selected)
        self.delete_btn.pack(side="left", padx=2)
        
        self.enable_btn = ttk.Button(btn_frame, text="🔄 Zapnout/Vypnout", command=self.toggle_selected)
        self.enable_btn.pack(side="left", padx=2)
        
        # Seznam plánů
        list_frame = ttk.Frame(main_frame)
        list_frame.pack(fill="both", expand=True)
        
        # Treeview pro zobrazení plánů
        self.schedule_tree = ttk.Treeview(list_frame, columns=("time", "mode", "temp", "wind", "duration", "status"), 
                                         show="tree headings", height=6)
        
        # Nastavení sloupců
        self.schedule_tree.heading("#0", text="Název")
        self.schedule_tree.heading("time", text="Čas (od-do)")
        self.schedule_tree.heading("mode", text="Režim")
        self.schedule_tree.heading("temp", text="Teplota")
        self.schedule_tree.heading("wind", text="Větrák")
        self.schedule_tree.heading("duration", text="Doba")
        self.schedule_tree.heading("status", text="Stav")
        
        # Nastavení šířek sloupců
        self.schedule_tree.column("#0", width=120)
        self.schedule_tree.column("time", width=100)
        self.schedule_tree.column("mode", width=60)
        self.schedule_tree.column("temp", width=60)
        self.schedule_tree.column("wind", width=60)
        self.schedule_tree.column("duration", width=60)
        self.schedule_tree.column("status", width=80)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.schedule_tree.yview)
        self.schedule_tree.configure(yscrollcommand=scrollbar.set)
        
        # Packing
        self.schedule_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Status info
        self.status_label = ttk.Label(main_frame, text="Žádné plány nenačteny", font=("Segoe UI", 9))
        self.status_label.pack(pady=5)
        
    def add_schedule_entry(self):
        """Přidání nového záznamu do plánu"""
        self.open_schedule_dialog()
        
    def edit_selected(self):
        """Úprava vybraného záznamu"""
        selection = self.schedule_tree.selection()
        if not selection:
            return
        
        item_id = selection[0]
        index = int(item_id) if item_id.isdigit() else 0
        if 0 <= index < len(self.schedule_entries):
            self.open_schedule_dialog(self.schedule_entries[index], index)
            
    def delete_selected(self):
        """Smazání vybraného záznamu"""
        selection = self.schedule_tree.selection()
        if not selection:
            return
            
        item_id = selection[0]
        index = int(item_id) if item_id.isdigit() else 0
        if 0 <= index < len(self.schedule_entries):
            del self.schedule_entries[index]
            self.refresh_display()
            self.save_schedule()
            
    def toggle_selected(self):
        """Zapnutí/vypnutí vybraného záznamu"""
        selection = self.schedule_tree.selection()
        if not selection:
            return
            
        item_id = selection[0]
        index = int(item_id) if item_id.isdigit() else 0
        if 0 <= index < len(self.schedule_entries):
            self.schedule_entries[index].enabled = not self.schedule_entries[index].enabled
            self.refresh_display()
            self.save_schedule()
            
    def open_schedule_dialog(self, entry: ScheduleEntry = None, index: int = -1):
        """Otevření dialogu pro úpravu/přidání plánu"""
        dialog = ScheduleEditDialog(self, self.modes, self.wind_options, entry)
        result = dialog.show()
        
        if result:
            if index >= 0:  # Úprava existujícího
                self.schedule_entries[index] = result
            else:  # Přidání nového
                self.schedule_entries.append(result)
            
            self.refresh_display()
            self.save_schedule()
            
    def refresh_display(self):
        """Obnovení zobrazení seznamu plánů"""
        # Vyčištění treeview
        for item in self.schedule_tree.get_children():
            self.schedule_tree.delete(item)
            
        # Přidání záznamů
        for i, entry in enumerate(self.schedule_entries):
            status = "🟢 Zapnuto" if entry.enabled else "🔴 Vypnuto"
            temp_text = f"{entry.temperature}°C" if entry.mode != "FAN" else "---"
            time_text = f"{entry.start_time} - {entry.end_time}"
            
            self.schedule_tree.insert("", "end", iid=str(i), 
                                    text=entry.name or f"Plán {i+1}",
                                    values=(time_text, entry.mode, temp_text, 
                                           entry.wind, f"{entry.duration_hours:.1f}h", status))
        
        # Aktualizace status labelu
        enabled_count = sum(1 for e in self.schedule_entries if e.enabled)
        total_count = len(self.schedule_entries)
        self.status_label.config(text=f"Plánů: {total_count}, Aktivních: {enabled_count}")
        
    def save_schedule(self):
        """Uložení plánu do souboru"""
        try:
            os.makedirs("data", exist_ok=True)
            schedule_data = [entry.to_dict() for entry in self.schedule_entries]
            data = {
                "schedules": schedule_data,
                "settings": {
                    "enable_scheduler": True,
                    "notification_enabled": True,
                    "auto_execute": True
                }
            }
            with open(self.schedule_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving schedule: {e}")
            
    def load_schedule(self):
        """Načtení plánu ze souboru"""
        try:
            if os.path.exists(self.schedule_file):
                with open(self.schedule_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Kontrola struktury souboru
                    if isinstance(data, dict) and "schedules" in data:
                        schedules_data = data["schedules"]
                    elif isinstance(data, list):
                        schedules_data = data
                    else:
                        schedules_data = []
                    
                    self.schedule_entries = [ScheduleEntry.from_dict(item) for item in schedules_data]
                    self.refresh_display()
        except Exception as e:
            print(f"Error loading schedule: {e}")
            self.schedule_entries = []
            
    def get_active_schedule_for_time(self, current_time: datetime) -> ScheduleEntry:
        """Získání aktivního plánu pro daný čas"""
        current_time_only = current_time.time()
        
        for entry in self.schedule_entries:
            if not entry.enabled:
                continue
                
            try:
                start_time = datetime.strptime(entry.start_time, "%H:%M").time()
                end_time = datetime.strptime(entry.end_time, "%H:%M").time()
                
                # Kontrola, zda aktuální čas je mezi start_time a end_time
                if end_time > start_time:
                    # Normální rozsah (např. 8:00 - 10:00)
                    if start_time <= current_time_only <= end_time:
                        return entry
                else:
                    # Rozsah přes půlnoc (např. 22:00 - 02:00)
                    if current_time_only >= start_time or current_time_only <= end_time:
                        return entry
                        
            except ValueError:
                continue
                
        return None

class ScheduleEditDialog:
    """Dialog pro úpravu/vytvoření plánu"""
    
    def __init__(self, parent, modes: List[str], wind_options: List[str], entry: ScheduleEntry = None):
        self.parent = parent
        self.modes = modes
        self.wind_options = wind_options
        self.entry = entry or ScheduleEntry()
        self.result = None
        
        # Vytvoření modálního okna
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Úprava plánu")
        self.dialog.geometry("400x500")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Centrování okna
        self.dialog.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        
        self.create_dialog_widgets()
        self.load_entry_data()
        
    def create_dialog_widgets(self):
        """Vytvoření widgetů dialogu"""
        main_frame = ttk.Frame(self.dialog, padding=10)
        main_frame.pack(fill="both", expand=True)
        
        # Název plánu
        ttk.Label(main_frame, text="Název plánu:").pack(anchor="w", pady=2)
        self.name_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.name_var, width=30).pack(fill="x", pady=2)
        
        # Čas spuštění
        ttk.Label(main_frame, text="Čas spuštění (HH:MM):").pack(anchor="w", pady=(10,2))
        self.start_time_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.start_time_var, width=10).pack(anchor="w", pady=2)
        
        # Čas konce
        ttk.Label(main_frame, text="Čas konce (HH:MM):").pack(anchor="w", pady=(10,2))
        self.end_time_var = tk.StringVar()
        ttk.Entry(main_frame, textvariable=self.end_time_var, width=10).pack(anchor="w", pady=2)
        
        # Režim
        ttk.Label(main_frame, text="Režim:").pack(anchor="w", pady=(10,2))
        self.mode_var = tk.StringVar()
        mode_combo = ttk.Combobox(main_frame, textvariable=self.mode_var, values=self.modes, state="readonly")
        mode_combo.pack(fill="x", pady=2)
        mode_combo.bind("<<ComboboxSelected>>", self.on_mode_change)
        
        # Teplota
        self.temp_frame = ttk.Frame(main_frame)
        self.temp_frame.pack(fill="x", pady=(10,2))
        ttk.Label(self.temp_frame, text="Teplota (°C):").pack(anchor="w")
        self.temp_var = tk.IntVar()
        self.temp_scale = ttk.Scale(self.temp_frame, from_=16, to=30, variable=self.temp_var, orient=tk.HORIZONTAL)
        self.temp_scale.pack(fill="x", pady=2)
        self.temp_label = ttk.Label(self.temp_frame, text="22°C")
        self.temp_label.pack(anchor="w")
        self.temp_scale.configure(command=self.update_temp_label)
        
        # Síla větru
        ttk.Label(main_frame, text="Síla větru:").pack(anchor="w", pady=(10,2))
        self.wind_var = tk.StringVar()
        ttk.Combobox(main_frame, textvariable=self.wind_var, values=self.wind_options, state="readonly").pack(fill="x", pady=2)
        
        # Zapnout zařízení
        self.power_var = tk.BooleanVar()
        ttk.Checkbutton(main_frame, text="Zapnout zařízení", variable=self.power_var).pack(anchor="w", pady=(10,2))
        
        # Vypnout zařízení na konci
        self.power_off_var = tk.BooleanVar()
        ttk.Checkbutton(main_frame, text="Vypnout zařízení na konci plánu", variable=self.power_off_var).pack(anchor="w", pady=2)
        
        # Tlačítka
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(20,0))
        
        ttk.Button(btn_frame, text="OK", command=self.ok_clicked).pack(side="right", padx=2)
        ttk.Button(btn_frame, text="Storno", command=self.cancel_clicked).pack(side="right", padx=2)
        
    def on_mode_change(self, event=None):
        """Reakce na změnu režimu"""
        if self.mode_var.get() == "FAN":
            self.temp_frame.pack_forget()
        else:
            self.temp_frame.pack(fill="x", pady=(10,2), after=self.dialog.children["!frame"].children["!combobox"])
            
    def update_temp_label(self, value):
        """Aktualizace labelu teploty"""
        self.temp_label.config(text=f"{int(float(value))}°C")
        
    def load_entry_data(self):
        """Načtení dat ze záznamu do formuláře"""
        self.name_var.set(self.entry.name)
        self.start_time_var.set(self.entry.start_time)
        self.end_time_var.set(self.entry.end_time)
        self.mode_var.set(self.entry.mode)
        self.temp_var.set(self.entry.temperature)
        self.wind_var.set(self.entry.wind)
        self.power_var.set(self.entry.power_on)
        self.power_off_var.set(getattr(self.entry, 'power_off_at_end', True))
        
        # Aktualizace labelu teploty
        self.update_temp_label(self.entry.temperature)
        
        # Skrytí teploty pro FAN režim
        self.on_mode_change()
        
    def ok_clicked(self):
        """Potvrzení změn"""
        try:
            # Validace časových formátů
            start_time = self.start_time_var.get()
            end_time = self.end_time_var.get()
            
            # Zkontroluj formát času
            datetime.strptime(start_time, "%H:%M")
            datetime.strptime(end_time, "%H:%M")
            
            # Vytvoř nový entry
            self.result = ScheduleEntry(
                name=self.name_var.get(),
                start_time=start_time,
                end_time=end_time,
                mode=self.mode_var.get(),
                temperature=int(self.temp_var.get()),
                wind=self.wind_var.get(),
                power_on=self.power_var.get(),
                power_off_at_end=self.power_off_var.get()
            )
            
            self.dialog.destroy()
        except ValueError:
            tk.messagebox.showerror("Chyba", "Neplatný formát času. Použijte HH:MM (např. 08:30)")
        except Exception as e:
            tk.messagebox.showerror("Chyba", f"Chyba při ukládání: {e}")
            
    def cancel_clicked(self):
        """Zrušení změn"""
        self.result = None
        self.dialog.destroy()
        
    def show(self) -> ScheduleEntry:
        """Zobrazení dialogu a vrácení výsledku"""
        self.dialog.wait_window()
        return self.result
