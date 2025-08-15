import tkinter as tk
from tkinter import ttk

def setup_dark_theme(root):
    # Nastavení pozadí hlavního okna
    root.configure(bg="#222222")
    
    style = ttk.Style(root)
    style.theme_use("clam")
    
    # Tmavé téma pro všechny widgety
    style.configure("TFrame", background="#222222")
    style.configure("TLabel", background="#222222", foreground="#eeeeee", font=("Segoe UI", 10))
    style.configure("TButton", 
                   background="#333333", 
                   foreground="#eeeeee",
                   relief="flat",
                   borderwidth=1,
                   font=("Segoe UI", 9))
    style.map("TButton",
              background=[('active', '#444444'), ('pressed', '#555555')],
              foreground=[('active', '#ffffff'), ('pressed', '#ffffff')])
    
    style.configure("TCombobox", 
                   fieldbackground="#333333", 
                   background="#333333", 
                   foreground="#eeeeee",
                   arrowcolor="#eeeeee",
                   bordercolor="#555555",
                   font=("Segoe UI", 9))
    style.map("TCombobox",
              fieldbackground=[('readonly', '#333333'), ('active', '#404040')],
              selectbackground=[('readonly', '#444444')],
              foreground=[('active', '#ffffff')])
    
    style.configure("TCheckbutton", 
                   background="#222222", 
                   foreground="#eeeeee",
                   font=("Segoe UI", 9))
    style.map("TCheckbutton",
              background=[('active', '#333333')],
              foreground=[('active', '#ffffff')])
              
    style.configure("TLabelframe", 
                   background="#222222", 
                   foreground="#eeeeee",
                   bordercolor="#444444")
    style.configure("TLabelframe.Label", 
                   background="#222222", 
                   foreground="#eeeeee",
                   font=("Segoe UI", 10, "bold"))
    
    style.configure("Horizontal.TScale",
                   background="#222222",
                   troughcolor="#333333",
                   bordercolor="#555555",
                   darkcolor="#222222",
                   lightcolor="#222222")
    style.map("Horizontal.TScale",
              background=[('active', '#333333')])
    
    # Styly pro scrollbar
    style.configure("Vertical.TScrollbar",
                   background="#333333",
                   troughcolor="#222222",
                   bordercolor="#555555",
                   arrowcolor="#eeeeee",
                   darkcolor="#333333",
                   lightcolor="#444444")
    style.map("Vertical.TScrollbar",
              background=[('active', '#444444')])
              
    # Styly pro Treeview
    style.configure("Treeview",
                   background="#333333",
                   foreground="#eeeeee",
                   fieldbackground="#333333",
                   bordercolor="#444444",
                   font=("Segoe UI", 9))
    style.map("Treeview",
              background=[('selected', '#0078d4')],
              foreground=[('selected', '#ffffff')])
              
    style.configure("Treeview.Heading",
                   background="#444444",
                   foreground="#eeeeee",
                   font=("Segoe UI", 9, "bold"))
    style.map("Treeview.Heading",
              background=[('active', '#555555')],
              foreground=[('active', '#ffffff')])
              
    # Entry styly
    style.configure("TEntry",
                   fieldbackground="#333333",
                   background="#333333",
                   foreground="#eeeeee",
                   bordercolor="#555555",
                   insertcolor="#eeeeee",
                   font=("Segoe UI", 9))
    style.map("TEntry",
              fieldbackground=[('focus', '#404040')],
              bordercolor=[('focus', '#0078d4')],
              foreground=[('focus', '#ffffff')])
