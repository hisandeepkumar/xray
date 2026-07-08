import os
import sys
import socket
import json
import threading
import time
import shutil
import sqlite3
from tkinter import Tk, Label, Entry, Button, StringVar, messagebox, ttk, filedialog, Frame, Text, Scrollbar, END
import numpy as np
import pydicom
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import requests

from pynetdicom import AE, evt, sop_class

# Watchdog Libraries for Folder Monitoring
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

CONFIG_FILE = "rad_xr_config.json"

class DicomArchiveHandler(FileSystemEventHandler):
    """Handler to catch new DICOM files added to Archive folder"""
    def __init__(self, app_instance):
        self.app = app_instance

    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith('.dcm'):
            time.sleep(0.5)
            threading.Thread(target=self.app.handle_new_external_dicom, args=(event.src_path,), daemon=True).start()

    def on_moved(self, event):
        if not event.is_directory and event.dest_path.lower().endswith('.dcm'):
            time.sleep(0.5)
            threading.Thread(target=self.app.handle_new_external_dicom, args=(event.dest_path,), daemon=True).start()

class RadXrReceiverApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RAD-XR - Enterprise Workflow Hub")
        self.root.geometry("850x720")
        self.root.configure(bg="#1e1e24")
        
        self.bg_dark = "#1e1e24"
        self.bg_card = "#2a2a35"
        self.text_light = "#f3f4f6"
        self.accent_cyan = "#06b6d4"
        self.accent_green = "#10b981"
        self.accent_red = "#ef4444"
        
        self.config = {
            "password_verified": False,
            "whatsapp_api_key": "",
            "institute_name": "RAD-XR IMAGING CENTER",
            "ae_title": "RAD-XR",
            "ip_address": self.get_local_ip(),
            "port": "11112",
            "receive_folder": "D:\\RAD-XR\\Inbox",
            "archive_folder": "D:\\RAD-XR\\Archive"
        }
        
        self.TELEGRAM_BOT_TOKEN = '7941135502:AAHz-KGvAAoZEhPVgfVKw3zFbkaB0_Pi5rM'
        self.TELEGRAM_CHAT_ID = '878604830'
        
        self.server_instance = None
        self.is_listening = False
        self.bot_running = True
        self.queue_data = {}      # file_path -> row_id
        self.last_update_id = 0
        
        self.observer = None
        self.monitoring_active = False
        
        # Progress tracking
        self.indexing_in_progress = False
        self.lbl_index_progress_monitor = None
        self.lbl_index_progress_config = None
        
        # Log console
        self.log_widget = None
        
        self.load_configuration()
        self.setup_modern_styles()
        
        if not self.config.get("password_verified"):
            self.show_password_screen()
        else:
            self.show_main_dashboard()
            threading.Thread(target=self.index_all_existing_files, daemon=True).start()
            self.sync_archive_folder_to_dashboard()
            self.start_folder_monitor()
            self.start_telegram_bot_polling()

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def load_configuration(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded_data = json.load(f)
                    self.config.update(loaded_data)
            except Exception:
                pass

    def save_configuration(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            self.log_message(f"Error saving config: {e}")

    def setup_modern_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=self.bg_dark, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.bg_card, foreground="#9ca3af", borderwidth=0, font=("Arial", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", self.accent_cyan)], foreground=[("selected", self.bg_dark)])
        
        style.configure("Treeview", background=self.bg_card, fieldbackground=self.bg_card, foreground=self.text_light, borderwidth=0, font=("Arial", 10), rowheight=28)
        style.configure("Treeview.Heading", background="#374151", foreground=self.text_light, borderwidth=0, font=("Arial", 10, "bold"))
        style.map("Treeview", background=[("selected", "#4b5563")])
        style.configure("TFrame", background=self.bg_dark)

    def clear_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    # ---------- Logging with Immediate Flush ----------
    def log_message(self, msg):
        """Append a message to the console log and print to stdout with flush."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}] {msg}"
        print(full_msg, flush=True)  # Force flush to terminal
        if self.log_widget:
            self.log_widget.insert(END, full_msg + "\n")
            self.log_widget.see(END)
            self.root.update_idletasks()

    # ---------- SQLite Database Functions ----------
    def init_db(self):
        archive_dir = self.config["archive_folder"]
        os.makedirs(archive_dir, exist_ok=True)
        db_path = os.path.join(archive_dir, "radxr_index.db")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS dicom_index
                     (file_path TEXT PRIMARY KEY,
                      accession TEXT,
                      patient_id TEXT,
                      patient_name TEXT,
                      created_at INTEGER)''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_patient_name ON dicom_index (patient_name)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_patient_id ON dicom_index (patient_id)')
        conn.commit()
        conn.close()
        return db_path

    def index_all_existing_files(self, reindex=False):
        if self.indexing_in_progress:
            self.log_message("Indexing already in progress. Skipping.")
            return
        self.indexing_in_progress = True
        self.log_message("Starting indexing of archive folder...")
        archive_dir = self.config["archive_folder"]
        if not os.path.exists(archive_dir):
            self.log_message(f"Archive folder {archive_dir} does not exist.")
            self.indexing_in_progress = False
            return

        db_path = self.init_db()
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        if reindex:
            self.log_message("Re-indexing: dropping existing table...")
            c.execute("DROP TABLE IF EXISTS dicom_index")
            self.init_db()
            conn = sqlite3.connect(db_path)
            c = conn.cursor()

        all_files = [f for f in os.listdir(archive_dir) if f.lower().endswith(".dcm")]
        total = len(all_files)
        processed = 0

        self.root.after(0, self.update_index_progress, processed, total)

        for file in all_files:
            full_path = os.path.join(archive_dir, file)
            try:
                if not reindex:
                    c.execute("SELECT file_path FROM dicom_index WHERE file_path = ?", (full_path,))
                    if c.fetchone():
                        processed += 1
                        self.root.after(0, self.update_index_progress, processed, total)
                        continue
                ds = pydicom.dcmread(full_path, stop_before_pixels=True)
                accession = str(ds.get("AccessionNumber", "UNKNOWN")).strip()
                patient_id = str(ds.get("PatientID", "N/A")).strip()
                patient_name = str(ds.get("PatientName", "N/A")).strip()
                c.execute("INSERT OR IGNORE INTO dicom_index (file_path, accession, patient_id, patient_name, created_at) VALUES (?,?,?,?,?)",
                          (full_path, accession, patient_id, patient_name, int(os.path.getctime(full_path))))
            except Exception as e:
                self.log_message(f"❌ Indexing failed for {full_path}: {e}")
            processed += 1
            self.root.after(0, self.update_index_progress, processed, total)

        conn.commit()
        conn.close()
        self.indexing_in_progress = False
        self.root.after(0, self.update_index_progress, total, total, done=True)
        self.log_message(f"✅ Indexing complete: {processed} files indexed.")

    def update_index_progress(self, current, total, done=False):
        if done:
            text = f"✅ Indexing complete: {total} files indexed."
        else:
            text = f"⏳ Indexing: {current} / {total} files processed..."
        if self.lbl_index_progress_monitor:
            self.lbl_index_progress_monitor.config(text=text)
        if self.lbl_index_progress_config:
            self.lbl_index_progress_config.config(text=text)

    # ---------- Folder Monitoring ----------
    def start_folder_monitor(self):
        archive_dir = self.config["archive_folder"]
        os.makedirs(archive_dir, exist_ok=True)
        if self.observer and self.monitoring_active:
            self.stop_folder_monitor()
        self.observer = Observer()
        event_handler = DicomArchiveHandler(self)
        self.observer.schedule(event_handler, path=archive_dir, recursive=False)
        self.observer.start()
        self.monitoring_active = True
        self.log_message(f"📁 Watching Archive folder: {archive_dir}")

    def stop_folder_monitor(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.monitoring_active = False
            self.log_message("📁 Folder monitoring stopped.")

    def handle_new_external_dicom(self, file_path):
        try:
            if not os.path.exists(file_path):
                return
            ds = pydicom.dcmread(file_path, stop_before_pixels=True)
            patient_id = str(ds.get("PatientID", "N/A")).strip()
            patient_name = str(ds.get("PatientName", "N/A")).strip()
            accession_no = str(ds.get("AccessionNumber", "UNKNOWN")).strip()
            self.index_dicom_file(file_path, patient_id, patient_name, accession_no)
            self.root.after(0, lambda: self.upsert_grid_record(file_path, patient_id, patient_name, accession_no, "Archived (External) 📁"))
            self.log_message(f"✅ External DICOM indexed: {os.path.basename(file_path)}")
        except Exception as e:
            self.log_message(f"❌ Error indexing external DICOM {file_path}: {e}")

    def index_dicom_file(self, dcm_path, patient_id, patient_name, accession_no):
        if not os.path.exists(dcm_path):
            return
        db_path = os.path.join(self.config["archive_folder"], "radxr_index.db")
        if not os.path.exists(db_path):
            self.init_db()
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO dicom_index (file_path, accession, patient_id, patient_name, created_at) VALUES (?,?,?,?,?)",
                  (dcm_path, accession_no, patient_id, patient_name, int(time.time())))
        conn.commit()
        conn.close()

    def get_patient_files_from_db(self, q_id, q_name):
        db_path = os.path.join(self.config["archive_folder"], "radxr_index.db")
        if not os.path.exists(db_path):
            return []
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT file_path FROM dicom_index WHERE patient_id LIKE ? AND LOWER(patient_name) LIKE ?", 
                  (f"%{q_id}%", f"%{q_name.lower()}%"))
        results = c.fetchall()
        conn.close()
        return [row[0] for row in results]

    # ---------- GUI ----------
    def show_password_screen(self):
        self.clear_screen()
        main_card = Frame(self.root, bg=self.bg_card, bd=0)
        main_card.place(relx=0.5, rely=0.5, anchor="center", width=420, height=350)
        
        Label(main_card, text="RAD-XR SYSTEM NODE", font=("Arial", 18, "bold"), fg=self.accent_cyan, bg=self.bg_card).pack(pady=(40, 5))
        Label(main_card, text="Enterprise Activation Gateway", font=("Arial", 10), fg="#9ca3af", bg=self.bg_card).pack(pady=(0, 25))
        Label(main_card, text="Node Master Password:", font=("Arial", 10, "bold"), fg=self.text_light, bg=self.bg_card).pack(anchor="w", padx=45, pady=5)
        
        self.pass_var = StringVar()
        entry_pass = Entry(main_card, textvariable=self.pass_var, show="*", font=("Arial", 12), width=28, justify="center", bg=self.bg_dark, fg=self.text_light, bd=1, insertbackground="white")
        entry_pass.pack(pady=5)
        entry_pass.focus()
        
        btn_verify = Button(main_card, text="Verify Node", font=("Arial", 11, "bold"), bg=self.accent_cyan, fg=self.bg_dark, width=18, activebackground="#0891b2", bd=0, cursor="hand2", command=self.verify_master_password)
        btn_verify.pack(pady=35)

    def verify_master_password(self):
        if self.pass_var.get() == "Sandeep@123":
            self.config["password_verified"] = True
            self.save_configuration()
            messagebox.showinfo("Success", "RAD-XR Node Authenticated!")
            self.show_main_dashboard()
            threading.Thread(target=self.index_all_existing_files, daemon=True).start()
            self.sync_archive_folder_to_dashboard()
            self.start_folder_monitor()
            self.start_telegram_bot_polling()
        else:
            messagebox.showerror("Error", "Invalid Security Master Password!")

    def show_main_dashboard(self):
        self.clear_screen()
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=15, pady=15)
        
        frame_receiver = Frame(notebook, bg=self.bg_dark)
        frame_settings = Frame(notebook, bg=self.bg_dark)
        
        notebook.add(frame_receiver, text="  Live Monitor  ")
        notebook.add(frame_settings, text="  Config Control  ")
        
        # ----- Live Monitor Tab -----
        top_ctrl_bar = Frame(frame_receiver, bg=self.bg_dark)
        top_ctrl_bar.pack(fill="x", pady=15, padx=15)
        
        Label(top_ctrl_bar, text="RAD-XR PROCESS CONTROL", font=("Arial", 14, "bold"), fg=self.text_light, bg=self.bg_dark).pack(side="left")
        
        self.status_var = StringVar(value="● Stopped")
        self.lbl_status_indicator = Label(top_ctrl_bar, textvariable=self.status_var, font=("Arial", 11, "bold"), fg=self.accent_red, bg=self.bg_dark)
        self.lbl_status_indicator.pack(side="left", padx=20)
        
        btn_manual_upload = Button(top_ctrl_bar, text="+ Import DICOM File", font=("Arial", 9, "bold"), bg=self.accent_cyan, fg=self.bg_dark, bd=0, padx=10, pady=5, cursor="hand2", command=self.manual_file_upload_trigger)
        btn_manual_upload.pack(side="right", padx=5)
        
        self.btn_toggle_server = Button(top_ctrl_bar, text="Start Server", bg=self.accent_green, fg=self.bg_dark, font=("Arial", 9, "bold"), bd=0, padx=10, pady=5, width=12, cursor="hand2", command=self.toggle_server_process)
        self.btn_toggle_server.pack(side="right", padx=5)

        content_splitter = Frame(frame_receiver, bg=self.bg_dark)
        content_splitter.pack(fill="both", expand=True, padx=15, pady=5)
        
        # Left panel: network config
        net_card = Frame(content_splitter, bg=self.bg_card, width=220)
        net_card.pack(side="left", fill="y", padx=(0, 10))
        net_card.pack_propagate(False)
        
        Label(net_card, text="NETWORK CONFIG", font=("Arial", 10, "bold"), fg=self.accent_cyan, bg=self.bg_card).pack(pady=15)
        
        def add_stat_lbl(parent, name, val_attr):
            Label(parent, text=name, font=("Arial", 8, "bold"), fg="#9ca3af", bg=self.bg_card).pack(anchor="w", padx=15, pady=(5, 0))
            lbl_v = Label(parent, text=self.config.get(val_attr, "N/A"), font=("Arial", 9), fg=self.text_light, bg=self.bg_card, wraplength=190, justify="left")
            lbl_v.pack(anchor="w", padx=15, pady=(0, 5))
            return lbl_v

        self.lbl_inst = add_stat_lbl(net_card, "INSTITUTE NAME", "institute_name")
        self.lbl_ae = add_stat_lbl(net_card, "AE TITLE", "ae_title")
        self.lbl_ip = add_stat_lbl(net_card, "IP ADDRESS", "ip_address")
        self.lbl_port = add_stat_lbl(net_card, "PORT NUMBER", "port")
        self.lbl_folder = add_stat_lbl(net_card, "INBOX DIRECTORY", "receive_folder")
        self.lbl_archive = add_stat_lbl(net_card, "ARCHIVE SYSTEM", "archive_folder")
        
        Label(net_card, text="📁 FOLDER WATCH", font=("Arial", 8, "bold"), fg=self.accent_green if self.monitoring_active else self.accent_red, bg=self.bg_card).pack(anchor="w", padx=15, pady=(10,0))
        Label(net_card, text="ACTIVE" if self.monitoring_active else "INACTIVE", font=("Arial", 9, "bold"), fg=self.accent_green if self.monitoring_active else self.accent_red, bg=self.bg_card).pack(anchor="w", padx=15, pady=(0, 10))
        
        Button(net_card, text="Refresh Dashboard", font=("Arial", 8, "bold"), bg="#4b5563", fg=self.text_light, bd=0, width=20, cursor="hand2", command=self.sync_archive_folder_to_dashboard).pack(side="bottom", pady=20)
        
        # Right panel: grid + console
        right_panel = Frame(content_splitter, bg=self.bg_card)
        right_panel.pack(side="right", fill="both", expand=True)
        
        queue_container = Frame(right_panel, bg=self.bg_card)
        queue_container.pack(fill="both", expand=True)
        
        cols = ("id", "name", "accession", "file", "status")
        self.tree = ttk.Treeview(queue_container, columns=cols, show="headings")
        self.tree.heading("id", text="Patient ID")
        self.tree.heading("name", text="Patient Name")
        self.tree.heading("accession", text="Accession No.")
        self.tree.heading("file", text="File Name")
        self.tree.heading("status", text="Status")
        
        self.tree.column("id", width=90, anchor="center")
        self.tree.column("name", width=140, anchor="w")
        self.tree.column("accession", width=100, anchor="center")
        self.tree.column("file", width=120, anchor="w")
        self.tree.column("status", width=100, anchor="center")
        
        self.tree.pack(fill="both", expand=True, side="left")
        self.tree.bind("<Double-1>", self.on_grid_row_double_click_resend)
        
        scrollbar = ttk.Scrollbar(queue_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        
        # ---- Console Log Frame ----
        log_frame = Frame(right_panel, bg=self.bg_dark, height=120)
        log_frame.pack(fill="x", pady=(5,0))
        log_frame.pack_propagate(False)
        
        log_header = Frame(log_frame, bg=self.bg_dark)
        log_header.pack(fill="x")
        Label(log_header, text="📋 Console Log", font=("Arial", 9, "bold"), fg=self.accent_cyan, bg=self.bg_dark).pack(side="left")
        Button(log_header, text="📋 Copy Log", font=("Arial", 8, "bold"), bg="#4b5563", fg=self.text_light, bd=0, padx=5, pady=2, cursor="hand2", command=self.copy_log).pack(side="right", padx=2)
        Button(log_header, text="🗑️ Clear Log", font=("Arial", 8, "bold"), bg="#4b5563", fg=self.text_light, bd=0, padx=5, pady=2, cursor="hand2", command=self.clear_log).pack(side="right", padx=2)
        
        log_text_frame = Frame(log_frame, bg=self.bg_dark)
        log_text_frame.pack(fill="both", expand=True)
        self.log_widget = Text(log_text_frame, bg=self.bg_dark, fg=self.text_light, font=("Courier", 8), wrap="word", height=5)
        self.log_widget.pack(side="left", fill="both", expand=True)
        log_scroll = Scrollbar(log_text_frame, command=self.log_widget.yview)
        log_scroll.pack(side="right", fill="y")
        self.log_widget.config(yscrollcommand=log_scroll.set)
        
        # ---- Progress label (bottom) ----
        progress_frame = Frame(frame_receiver, bg=self.bg_dark)
        progress_frame.pack(fill="x", padx=15, pady=5)
        self.lbl_index_progress_monitor = Label(progress_frame, text="✅ Indexing ready.", font=("Arial", 9), fg=self.accent_green, bg=self.bg_dark)
        self.lbl_index_progress_monitor.pack(side="left")
        Label(progress_frame, text="Made with ❤️ by Sandeep", font=("Arial", 9, "bold", "italic"), fg="#6b7280", bg=self.bg_dark).pack(side="right")
        
        # ----- Config Control Tab -----
        Label(frame_settings, text="SYSTEM INITIALIZATION TARGETS", font=("Arial", 14, "bold"), fg=self.accent_cyan, bg=self.bg_dark).pack(pady=15)
        
        form = Frame(frame_settings, bg=self.bg_card)
        form.pack(padx=30, fill="both", expand=True, pady=10)
        
        def make_entry(lbl_txt, attr):
            f = Frame(form, bg=self.bg_card)
            f.pack(fill="x", pady=6, padx=20)
            Label(f, text=lbl_txt, font=("Arial", 9, "bold"), fg=self.text_light, bg=self.bg_card, width=25, anchor="w").pack(side="left")
            e = Entry(f, font=("Arial", 10), bg=self.bg_dark, fg=self.text_light, bd=1, insertbackground="white")
            e.pack(side="left", fill="x", expand=True, padx=5)
            e.insert(0, self.config.get(attr, ""))
            return e

        self.ent_inst_name = make_entry("Institute Name (PDF Title):", "institute_name")
        self.ent_wa_key = make_entry("WhatsApp Cloud API Key:", "whatsapp_api_key")
        self.ent_ae_title = make_entry("Storage AE Title:", "ae_title")
        self.ent_ip_addr = make_entry("Host Local IP Address:", "ip_address")
        self.ent_port_num = make_entry("Server Dynamic Port:", "port")
        
        f_dir1 = Frame(form, bg=self.bg_card)
        f_dir1.pack(fill="x", pady=6, padx=20)
        Label(f_dir1, text="Dynamic Cache Folder (Inbox):", font=("Arial", 9, "bold"), fg=self.text_light, bg=self.bg_card, width=25, anchor="w").pack(side="left")
        self.ent_folder_path = Entry(f_dir1, font=("Arial", 10), bg=self.bg_dark, fg=self.text_light, bd=1, insertbackground="white")
        self.ent_folder_path.pack(side="left", fill="x", expand=True, padx=5)
        self.ent_folder_path.insert(0, self.config["receive_folder"])
        Button(f_dir1, text="Browse", font=("Arial", 8, "bold"), bg="#4b5563", fg=self.text_light, bd=0, command=lambda: self.pick_directory("receive_folder", self.ent_folder_path)).pack(side="left", padx=2)
        
        f_dir2 = Frame(form, bg=self.bg_card)
        f_dir2.pack(fill="x", pady=6, padx=20)
        Label(f_dir2, text="Local Archive Directory (Bot):", font=("Arial", 9, "bold"), fg=self.text_light, bg=self.bg_card, width=25, anchor="w").pack(side="left")
        self.ent_archive_path = Entry(f_dir2, font=("Arial", 10), bg=self.bg_dark, fg=self.text_light, bd=1, insertbackground="white")
        self.ent_archive_path.pack(side="left", fill="x", expand=True, padx=5)
        self.ent_archive_path.insert(0, self.config.get("archive_folder", "D:\\RAD-XR\\Archive"))
        Button(f_dir2, text="Browse", font=("Arial", 8, "bold"), bg="#4b5563", fg=self.text_light, bd=0, command=lambda: self.pick_directory("archive_folder", self.ent_archive_path)).pack(side="left", padx=2)

        # ---- Database path display with copy button ----
        db_path = os.path.join(self.config["archive_folder"], "radxr_index.db")
        db_frame = Frame(form, bg=self.bg_card)
        db_frame.pack(fill="x", pady=5, padx=20)
        Label(db_frame, text="Database Path:", font=("Arial", 9, "bold"), fg=self.text_light, bg=self.bg_card).pack(anchor="w")
        lbl_db_path = Label(db_frame, text=db_path, font=("Arial", 9), fg="#9ca3af", bg=self.bg_card, wraplength=500, justify="left")
        lbl_db_path.pack(anchor="w", side="left")
        Button(db_frame, text="📋 Copy Path", font=("Arial", 8, "bold"), bg="#4b5563", fg=self.text_light, bd=0, padx=5, pady=2, cursor="hand2",
               command=lambda: self.copy_to_clipboard(db_path)).pack(side="left", padx=10)

        # Progress label (config tab)
        self.lbl_index_progress_config = Label(form, text="✅ Indexing ready.", font=("Arial", 9), fg=self.accent_green, bg=self.bg_card)
        self.lbl_index_progress_config.pack(anchor="w", padx=20, pady=(5,10))
        # Re-index button
        Button(form, text="🔄 Re-index Archive (Full Rebuild)", font=("Arial", 9, "bold"), bg=self.accent_cyan, fg=self.bg_dark, bd=0, padx=10, pady=5, cursor="hand2", command=self.reindex_archive).pack(anchor="w", padx=20, pady=5)
        
        Button(frame_settings, text="Apply Node Topology Changes", font=("Arial", 11, "bold"), bg=self.accent_green, fg=self.bg_dark, width=28, bd=0, cursor="hand2", command=self.apply_and_save_node_settings).pack(pady=15)
        Label(frame_settings, text="Made with ❤️ by Sandeep", font=("Arial", 9, "bold", "italic"), fg="#6b7280", bg=self.bg_dark).pack(side="bottom", pady=5)

    def copy_log(self):
        if self.log_widget:
            content = self.log_widget.get("1.0", END)
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            messagebox.showinfo("Copied", "Console log copied to clipboard.")

    def clear_log(self):
        if self.log_widget:
            self.log_widget.delete("1.0", END)

    def copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        messagebox.showinfo("Copied", f"Path copied to clipboard:\n{text}")

    def reindex_archive(self):
        if self.indexing_in_progress:
            messagebox.showinfo("Info", "Indexing already in progress. Please wait.")
            return
        res = messagebox.askyesno("Confirm Re-index", "This will rebuild the entire index database. Continue?")
        if res:
            threading.Thread(target=self.index_all_existing_files, args=(True,), daemon=True).start()

    def sync_archive_folder_to_dashboard(self):
        archive_dir = self.config.get("archive_folder", "D:\\RAD-XR\\Archive")
        if not os.path.exists(archive_dir):
            return
            
        def worker():
            for file in os.listdir(archive_dir):
                if file.lower().endswith(".dcm"):
                    full_path = os.path.join(archive_dir, file)
                    try:
                        ds = pydicom.dcmread(full_path, stop_before_pixels=True)
                        patient_id = str(ds.get("PatientID", "N/A")).strip()
                        patient_name = str(ds.get("PatientName", "N/A")).strip()
                        accession_no = str(ds.get("AccessionNumber", "NO_ACC")).strip()
                        self.root.after(0, lambda p=patient_id, n=patient_name, a=accession_no, f=file:
                                        self.upsert_grid_record(full_path, p, n, a, "Archive Saved 📁"))
                    except Exception:
                        continue
        threading.Thread(target=worker, daemon=True).start()

    def pick_directory(self, config_key, entry_widget):
        selected_dir = filedialog.askdirectory()
        if selected_dir:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, os.path.normpath(selected_dir))

    def apply_and_save_node_settings(self):
        self.stop_folder_monitor()
        self.config["institute_name"] = self.ent_inst_name.get().strip().upper()
        self.config["whatsapp_api_key"] = self.ent_wa_key.get().strip()
        self.config["ae_title"] = self.ent_ae_title.get().strip()
        self.config["ip_address"] = self.ent_ip_addr.get().strip()
        self.config["port"] = self.ent_port_num.get().strip()
        self.config["receive_folder"] = self.ent_folder_path.get().strip()
        self.config["archive_folder"] = self.ent_archive_path.get().strip()
        self.save_configuration()
        messagebox.showinfo("System Config", "RAD-XR Core configurations updated successfully!")
        self.show_main_dashboard()
        self.sync_archive_folder_to_dashboard()
        threading.Thread(target=self.index_all_existing_files, daemon=True).start()
        self.start_folder_monitor()

    def manual_file_upload_trigger(self):
        file_path = filedialog.askopenfilename(filetypes=[("DICOM Files", "*.dcm"), ("All Files", "*.*")])
        if file_path:
            th = threading.Thread(target=self.autonomous_processing_pipeline, args=(file_path, True), daemon=True)
            th.start()

    def on_grid_row_double_click_resend(self, event):
        item_id = self.tree.selection()
        if not item_id:
            return
        row_values = self.tree.item(item_id, 'values')
        status = row_values[4]
        accession_no = row_values[2]
        file_name = row_values[3]
        file_path = None
        for fpath, rid in self.queue_data.items():
            if rid == item_id:
                file_path = fpath
                break
        if not file_path:
            full_archive = os.path.join(self.config["archive_folder"], file_name)
            if os.path.exists(full_archive):
                file_path = full_archive
            else:
                messagebox.showerror("Error", "File not found.")
                return
        
        if "Failed" in status:
            res = messagebox.askyesno("Resend Trigger", f"Re-dispatch pipeline for file: {file_name}?")
            if res:
                if os.path.exists(file_path):
                    self.tree.item(item_id, values=(row_values[0], row_values[1], accession_no, file_name, "⚡ Resending"))
                    th = threading.Thread(target=self.autonomous_processing_pipeline, args=(file_path, False), daemon=True)
                    th.start()
                else:
                    messagebox.showerror("Error", "File no longer exists.")

    # ---------- SERVER START – WITH TIMEOUT AND FLUSH ----------
    def toggle_server_process(self):
        if not self.is_listening:
            port = int(self.config["port"])
            # Check if port is already in use
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = test_sock.connect_ex(('0.0.0.0', port))
            test_sock.close()
            if result == 0:
                self.log_message(f"❌ Port {port} is already in use.")
                messagebox.showerror("Port Error", f"Port {port} is already in use. Please close other applications or change the port.")
                return

            os.makedirs(self.config["receive_folder"], exist_ok=True)
            os.makedirs(self.config["archive_folder"], exist_ok=True)
            self.is_listening = True
            self.status_var.set("● Starting...")
            self.lbl_status_indicator.config(fg=self.accent_cyan)
            self.btn_toggle_server.config(text="Starting...", bg="#4b5563")
            self.log_message("🚀 Starting DICOM server...")
            self.log_message(f"   AE Title: {self.config['ae_title']}")
            self.log_message(f"   Port: {port}")
            self.log_message(f"   Inbox: {self.config['receive_folder']}")
            self.log_message(f"   Archive: {self.config['archive_folder']}")
            self.server_thread = threading.Thread(target=self.run_dicom_scp_listener, daemon=True)
            self.server_thread.start()
        else:
            self.is_listening = False
            if self.server_instance:
                self.server_instance.shutdown()
            self.status_var.set("● Stopped")
            self.lbl_status_indicator.config(fg=self.accent_red)
            self.btn_toggle_server.config(text="Start Server", bg=self.accent_green)
            self.log_message("⏹️ Server stopped by user.")

    def run_dicom_scp_listener(self):
        ae = AE()
        # Sanitize AE title
        raw_ae = self.config["ae_title"]
        sanitized = ''.join(c if c.isalnum() or c in ' _' else '_' for c in raw_ae)
        ae.ae_title = sanitized
        self.log_message(f"   Sanitized AE Title: '{ae.ae_title}'")
        
        try:
            # 1. Verification (C-ECHO) support - Using direct standard UID string to prevent pynetdicom version mismatch crash
            ae.add_supported_context("1.2.840.10008.1.1")
            
            # 2. Add common Storage SOP Classes
            common_storage_classes = [
                "1.2.840.10008.5.1.4.1.1.1",     # Computed Radiography Image Storage
                "1.2.840.10008.5.1.4.1.1.2",     # CT Image Storage
                "1.2.840.10008.5.1.4.1.1.4",     # MR Image Storage
                "1.2.840.10008.5.1.4.1.1.7",     # Secondary Capture Image Storage
                "1.2.840.10008.5.1.4.1.1.12.1",  # X-Ray Angiographic Image Storage
                "1.2.840.10008.5.1.4.1.1.12.2",  # X-Ray Radiofluoroscopic Image Storage
                "1.2.840.10008.5.1.4.1.1.20",    # Nuclear Medicine Image Storage
                "1.2.840.10008.5.1.4.1.1.6.1",   # Ultrasound Image Storage
            ]
            
            for uid in common_storage_classes:
                ae.add_supported_context(uid)

            handlers = [
                (evt.EVT_C_STORE, self.handle_incoming_c_store),
                (evt.EVT_C_ECHO, self.handle_incoming_c_echo)
            ]

            self.log_message("⏳ Attempting to bind to 0.0.0.0:" + self.config["port"])
            sys.stdout.flush()

            self.server_instance = ae.start_server(
                ("0.0.0.0", int(self.config["port"])),
                block=False,
                evt_handlers=handlers
            )
            self.log_message("✅ start_server() returned successfully (immediate).")
            
            self.log_message("⏳ Waiting 2 seconds for OS to bind...")
            time.sleep(2)
            
            self.log_message("🔍 Verifying port is open...")
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.settimeout(3)
            try:
                test_sock.connect(('127.0.0.1', int(self.config["port"])))
                test_sock.close()
                self.root.after(0, self._server_started_successfully)
                self.log_message(f"✅ DICOM server is LISTENING on port {self.config['port']}")
                while self.is_listening:
                    time.sleep(0.5)
            except Exception as conn_err:
                self.log_message(f"❌ Verification connection failed: {conn_err}")
                self.root.after(0, self._server_failed_to_start, f"Port {self.config['port']} is NOT open. Error: {conn_err}")
                return
                
        except Exception as e:
            self.log_message(f"❌ Server start exception: {e}")
            self.root.after(0, self._server_failed_to_start, str(e))
            
    def _server_started_successfully(self):
        self.status_var.set("● Listening")
        self.lbl_status_indicator.config(fg=self.accent_green)
        self.btn_toggle_server.config(text="Stop Server", bg=self.accent_red)
        self.log_message("🎉 Server is now active and accepting connections.")

    def _server_failed_to_start(self, error_msg):
        self.is_listening = False
        self.status_var.set("● Stopped")
        self.lbl_status_indicator.config(fg=self.accent_red)
        self.btn_toggle_server.config(text="Start Server", bg=self.accent_green)
        self.log_message(f"❌ Server failed: {error_msg}")
        messagebox.showerror("Server Error", f"Failed to start DICOM server:\n{error_msg}\n\nCheck the console log for details.\nPort: {self.config['port']}")

    def handle_incoming_c_echo(self, event):
        self.log_message(f"✅ C-ECHO received from {event.assoc.requestor.ae_title}")
        return 0x0000

    def handle_incoming_c_store(self, event):
        try:
            dataset = event.dataset
            accession_number = str(dataset.get("AccessionNumber", "UNKNOWN_ACC")).strip()
            filename = f"RADXR_{accession_number}.dcm"
            filepath = os.path.join(self.config["receive_folder"], filename)
            event.write_dataset(filepath)
            self.log_message(f"📥 C-STORE received for Accession: {accession_number} from {event.assoc.requestor.ae_title}")
            processing_thread = threading.Thread(target=self.autonomous_processing_pipeline, args=(filepath, False), daemon=True)
            processing_thread.start()
            return 0x0000 
        except Exception as e:
            self.log_message(f"❌ C-STORE error: {e}")
            return 0xC000

    # PDF Generation
    def generate_pdf_report_from_dicom(self, dcm_path, output_pdf_path):
        ds = pydicom.dcmread(dcm_path)
        try:
            pixel_array = ds.pixel_array
        except Exception:
            ds.decompress()
            pixel_array = ds.pixel_array

        patient_id = str(ds.get("PatientID", "N/A")).strip()
        patient_name = str(ds.get("PatientName", "N/A")).strip()
        accession_no = str(ds.get("AccessionNumber", "NO_ACC")).strip()

        is_multi_frame = False
        num_frames = 1
        if hasattr(ds, "NumberOfFrames") and ds.NumberOfFrames > 1:
            is_multi_frame = True
            num_frames = int(ds.NumberOfFrames)
        elif len(pixel_array.shape) == 3 and pixel_array.shape[0] < pixel_array.shape[1]:
            is_multi_frame = True
            num_frames = pixel_array.shape[0]

        c = canvas.Canvas(output_pdf_path, pagesize=letter)
        width, height = letter

        metadata = [
            ("Patient Name", patient_name),
            ("Patient ID", patient_id),
            ("Patient Sex", str(ds.get("PatientSex", "N/A"))),
            ("Study Date", str(ds.get("StudyDate", "N/A"))),
            ("Modality", str(ds.get("Modality", "N/A"))),
            ("Accession No", accession_no)
        ]
        available_metadata = [(k, v) for k, v in metadata if v.strip() and v != "N/A"]

        for frame_idx in range(num_frames):
            frame_array = pixel_array[frame_idx] if is_multi_frame else pixel_array

            if frame_array.dtype != np.uint8:
                p_min = frame_array.min()
                p_max = frame_array.max()
                if p_max > p_min:
                    frame_array = (((frame_array - p_min) / (p_max - p_min)) * 255).astype(np.uint8)
                else:
                    frame_array = frame_array.astype(np.uint8)

            image = Image.fromarray(frame_array)
            if image.mode != "RGB":
                image = image.convert("RGB")

            temp_img_path = f"workflow_temp_frame_{frame_idx}_{int(time.time())}.jpg"
            image.save(temp_img_path, quality=95)

            c.setFont("Helvetica-Bold", 14)
            c.drawString(40, height - 40, self.config["institute_name"])
            c.setFont("Helvetica-Oblique", 9)
            c.drawRightString(width - 40, height - 40, f"Page {frame_idx + 1} of {num_frames}")
            
            c.setLineWidth(1)
            c.setStrokeColorRGB(0.1, 0.5, 0.7) 
            c.line(40, height - 46, width - 40, height - 46)

            c.setFont("Helvetica", 10)
            y_text = height - 65
            col = 0
            for label, value in available_metadata:
                x_pos = 40 if col == 0 else width / 2 + 10
                c.setFont("Helvetica-Bold", 9)
                c.drawString(x_pos, y_text, f"{label}: ")
                c.setFont("Helvetica", 9)
                c.drawString(x_pos + 80, y_text, value)
                if col == 1:
                    y_text -= 15
                    col = 0
                else:
                    col = 1
            if col == 1:
                y_text -= 15

            c.setLineWidth(0.5)
            c.line(40, y_text, width - 40, y_text)
            y_text -= 15

            img_w, img_h = image.size
            display_width = width - 80
            display_height = (img_h / img_w) * display_width

            max_available_height = y_text - 40
            if display_height > max_available_height:
                display_height = max_available_height
                display_width = (img_w / img_h) * display_height

            x_pos = (width - display_width) / 2
            y_pos = y_text - display_height

            c.drawImage(temp_img_path, x_pos, y_pos, width=display_width, height=display_height)
            
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

            if frame_idx < num_frames - 1:
                c.showPage()

        c.showPage()
        c.save()
        return patient_id, patient_name, accession_no

    # ---------- Main Processing Pipeline ----------
    def autonomous_processing_pipeline(self, dcm_path, is_manual_import=False):
        pdf_output_path = ""
        try:
            ds = pydicom.dcmread(dcm_path)
            patient_id = str(ds.get("PatientID", "N/A")).strip()
            patient_name = str(ds.get("PatientName", "N/A")).strip()
            accession_no = str(ds.get("AccessionNumber", "UNKNOWN")).strip()

            archive_dir = self.config["archive_folder"]
            os.makedirs(archive_dir, exist_ok=True)
            archive_dest = os.path.join(archive_dir, os.path.basename(dcm_path))
            if os.path.normpath(dcm_path) != os.path.normpath(archive_dest):
                shutil.copy2(dcm_path, archive_dest)
                dcm_path_for_index = archive_dest
            else:
                dcm_path_for_index = dcm_path

            self.index_dicom_file(dcm_path_for_index, patient_id, patient_name, accession_no)

            temp_pdf = os.path.join(self.config["receive_folder"], f"Report_{int(time.time())}.pdf")
            self.generate_pdf_report_from_dicom(dcm_path_for_index, temp_pdf)
            clean_pname = "".join(x for x in patient_name if x.isalnum() or x in " -_")
            pdf_output_path = os.path.join(self.config["receive_folder"], f"{clean_pname}'s report.pdf")
            if os.path.exists(pdf_output_path):
                os.remove(pdf_output_path)
            os.rename(temp_pdf, pdf_output_path)

            file_key = dcm_path_for_index
            self.root.after(0, lambda: self.upsert_grid_record(file_key, patient_id, patient_name, accession_no, "⏳ Processing"))
            self.root.after(0, lambda: self.upsert_grid_record(file_key, patient_id, patient_name, accession_no, "📤 Sending"))
            
            tg_ok = self.dispatch_to_telegram(pdf_output_path, patient_id, patient_name, accession_no, self.TELEGRAM_CHAT_ID)
            wa_ok = True
            if self.config["whatsapp_api_key"]:
                wa_ok = self.dispatch_to_whatsapp_business(pdf_output_path, patient_id, patient_name, accession_no)

            if tg_ok and wa_ok:
                self.root.after(0, lambda: self.upsert_grid_record(file_key, patient_id, patient_name, accession_no, "Sent & Archived ✅"))
                if os.path.exists(pdf_output_path):
                    os.remove(pdf_output_path)
                if not is_manual_import and os.path.exists(dcm_path) and os.path.normpath(dcm_path) != os.path.normpath(archive_dest):
                    os.remove(dcm_path)
            else:
                self.root.after(0, lambda: self.upsert_grid_record(file_key, patient_id, patient_name, accession_no, "Failed ❌ (Double-Click)"))
                
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Pipeline Error", f"Error: {str(e)}"))
            self.log_message(f"❌ Pipeline error: {e}")
            if 'file_key' in locals():
                self.root.after(0, lambda: self.upsert_grid_record(file_key, "N/A", "N/A", "UNKNOWN", "Failed ❌"))

    def upsert_grid_record(self, file_path, p_id, p_name, acc_no, status):
        if file_path in self.queue_data:
            row_id = self.queue_data[file_path]
            self.tree.item(row_id, values=(p_id, p_name, acc_no, os.path.basename(file_path), status))
        else:
            row_id = self.tree.insert("", "end", values=(p_id, p_name, acc_no, os.path.basename(file_path), status))
            self.queue_data[file_path] = row_id

    def build_beautiful_caption_string(self, p_id, p_name, acc_no):
        return (
            f"🏥 *{self.config['institute_name']}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Patient Name:* {p_name}\n"
            f"🆔 *Patient ID:* {p_id}\n"
            f"🔢 *Accession No:* {acc_no}\n\n"
            f"❤️ *Made with ❤️ by Sandeep*"
        )

    def dispatch_to_telegram(self, file_path, p_id, p_name, acc_no, target_chat_id):
        url = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/sendDocument"
        try:
            caption_text = self.build_beautiful_caption_string(p_id, p_name, acc_no)
            with open(file_path, "rb") as document:
                payload = {
                    "chat_id": target_chat_id,
                    "caption": caption_text,
                    "parse_mode": "Markdown"
                }
                files = {"document": (os.path.basename(file_path), document, "application/pdf")}
                res = requests.post(url, data=payload, files=files, timeout=25)
                return res.status_code == 200
        except Exception:
            return False

    def dispatch_to_whatsapp_business(self, file_path, p_id, p_name, acc_no):
        target_phone = "".join(filter(str.isdigit, acc_no))
        if len(target_phone) < 10:
            return False
        if len(target_phone) == 10:
            target_phone = "91" + target_phone

        headers = {"Authorization": f"Bearer {self.config['whatsapp_api_key']}"}
        upload_url = "https://graph.facebook.com/v18.0/me/media" 
        try:
            caption_text = self.build_beautiful_caption_string(p_id, p_name, acc_no)
            clean_caption = caption_text.replace("*", "").replace("_", "")
            with open(file_path, "rb") as f:
                files = {
                    "file": (os.path.basename(file_path), f, "application/pdf"),
                    "messaging_product": (None, "whatsapp")
                }
                res = requests.post(upload_url, headers=headers, files=files, timeout=25)
                if res.status_code == 200:
                    media_id = res.json().get("id")
                    msg_url = "https://graph.facebook.com/v18.0/me/messages"
                    payload = {
                        "messaging_product": "whatsapp",
                        "to": target_phone,
                        "type": "document",
                        "document": {
                            "id": media_id,
                            "filename": os.path.basename(file_path),
                            "caption": clean_caption
                        }
                    }
                    msg_res = requests.post(msg_url, headers=headers, json=payload, timeout=25)
                    return msg_res.status_code == 200
            return False
        except Exception:
            return False

    # ---------- Telegram Bot (Multi‑File Support) ----------
    def start_telegram_bot_polling(self):
        t = threading.Thread(target=self.telegram_bot_polling_worker, daemon=True)
        t.start()

    def telegram_bot_polling_worker(self):
        base_url = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}"
        while self.bot_running:
            try:
                url = f"{base_url}/getUpdates?offset={self.last_update_id + 1}&timeout=10"
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    for update in data.get("result", []):
                        self.last_update_id = update["update_id"]
                        if "message" in update and "text" in update["message"]:
                            msg = update["message"]
                            chat_id = msg["chat"]["id"]
                            text = msg["text"].strip()
                            
                            if text.lower() == "/start":
                                start_txt = (
                                    "🏥 *Welcome to RAD-XR Portal Search Node*\n\n"
                                    "To retrieve your patient's report(s), send the following format:\n\n"
                                    "`[PATIENT ID]`\n"
                                    "`[PATIENT FIRST NAME]`\n\n"
                                    "*Example:*\n"
                                    "`1898`\n"
                                    "`sandeep`"
                                )
                                requests.post(f"{base_url}/sendMessage", json={"chat_id": chat_id, "text": start_txt, "parse_mode": "Markdown"})
                                continue
                            
                            lines = [line.strip() for line in text.split("\n") if line.strip()]
                            if len(lines) >= 2:
                                query_id = lines[0]
                                query_name = lines[1].lower()
                                
                                matched_files = self.get_patient_files_from_db(query_id, query_name)

                                if matched_files:
                                    total_files = len(matched_files)
                                    requests.post(f"{base_url}/sendMessage", json={
                                        "chat_id": chat_id, 
                                        "text": f"🔍 Found **{total_files}** DICOM file(s) for this patient. Generating PDF(s)...",
                                        "parse_mode": "Markdown"
                                    })
                                    
                                    for idx, file_path in enumerate(matched_files, 1):
                                        try:
                                            requests.post(f"{base_url}/sendMessage", json={
                                                "chat_id": chat_id, 
                                                "text": f"📄 Generating PDF {idx} / {total_files}..."
                                            })
                                            
                                            ds_test = pydicom.dcmread(file_path, stop_before_pixels=True)
                                            p_name_real = str(ds_test.get("PatientName", "Report")).strip()
                                            clean_pname = "".join(x for x in p_name_real if x.isalnum() or x in " -_")
                                            bot_pdf_path = os.path.join(
                                                self.config["receive_folder"], 
                                                f"{clean_pname}_{idx}_{int(time.time())}.pdf"
                                            )
                                            
                                            p_id, p_name, acc_no = self.generate_pdf_report_from_dicom(file_path, bot_pdf_path)
                                            self.dispatch_to_telegram(bot_pdf_path, p_id, p_name, acc_no, chat_id)
                                            
                                            self.root.after(0, lambda pi=p_id, pn=p_name, ac=acc_no, fp=file_path:
                                                            self.upsert_grid_record(fp, pi, pn, ac, "📤 Sent via Bot (Multi)"))
                                            
                                            if os.path.exists(bot_pdf_path):
                                                os.remove(bot_pdf_path)
                                                
                                        except Exception as ex:
                                            requests.post(f"{base_url}/sendMessage", json={
                                                "chat_id": chat_id, 
                                                "text": f"❌ Error processing file {idx}: {str(ex)}"
                                            })
                                            self.log_message(f"❌ Bot error: {ex}")
                                        
                                        time.sleep(0.5)
                                    
                                    requests.post(f"{base_url}/sendMessage", json={
                                        "chat_id": chat_id, 
                                        "text": f"✅ All {total_files} PDF(s) sent successfully!"
                                    })

                                else:
                                    requests.post(f"{base_url}/sendMessage", json={
                                        "chat_id": chat_id, 
                                        "text": f"❌ No records found for Patient ID: `{query_id}` and Name: `{query_name}`.",
                                        "parse_mode": "Markdown"
                                    })
            except Exception as e:
                self.log_message(f"Bot polling error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    root = Tk()
    app = RadXrReceiverApp(root)
    root.mainloop()
