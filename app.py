import os
import sys
import socket
import json
import threading
import time
import shutil
import sqlite3
from tkinter import Tk, Label, Entry, Button, StringVar, messagebox, ttk, filedialog, Frame
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
    """Archive Folder में नई DICOM आने पर इसे पकड़ने के लिए Handler"""
    def __init__(self, app_instance):
        self.app = app_instance

    def on_created(self, event):
        # जब कोई नई फ़ाइल बने (Create हो)
        if not event.is_directory and event.src_path.lower().endswith('.dcm'):
            # थोड़ा सा wait करें ताकि फ़ाइल पूरी तरह Write हो जाए
            time.sleep(0.5)
            threading.Thread(target=self.app.handle_new_external_dicom, args=(event.src_path,), daemon=True).start()

    def on_moved(self, event):
        # जब कोई फ़ाइल कहीं से Move करके इस फोल्डर में आए
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
        self.queue_data = {} 
        self.last_update_id = 0
        
        # Folder Watcher के लिए
        self.observer = None
        self.monitoring_active = False
        
        self.load_configuration()
        self.setup_modern_styles()
        
        if not self.config.get("password_verified"):
            self.show_password_screen()
        else:
            self.show_main_dashboard()
            # सारी मौजूदा फ़ाइलों को इंडेक्स करें (बैकग्राउंड में)
            threading.Thread(target=self.index_all_existing_files, daemon=True).start()
            self.sync_archive_folder_to_dashboard()
            # Archive Folder पर नज़र रखना शुरू करें
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
            print(f"Error saving config: {e}")

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

    # ---------- SQLite Database Functions ----------
    def init_db(self):
        """Archive folder में SQLite DB बनाएँ / कनेक्ट करें"""
        archive_dir = self.config["archive_folder"]
        os.makedirs(archive_dir, exist_ok=True)
        db_path = os.path.join(archive_dir, "radxr_index.db")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS dicom_index
                     (accession TEXT PRIMARY KEY,
                      patient_id TEXT,
                      patient_name TEXT,
                      file_path TEXT UNIQUE,
                      created_at INTEGER)''')
        c.execute('CREATE INDEX IF NOT EXISTS idx_patient_name ON dicom_index (patient_name)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_patient_id ON dicom_index (patient_id)')
        conn.commit()
        conn.close()
        return db_path

    def index_all_existing_files(self):
        """Archive folder की सभी .dcm फ़ाइलों को DB में डालें (पहली बार)"""
        archive_dir = self.config["archive_folder"]
        if not os.path.exists(archive_dir):
            return
        db_path = self.init_db()
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        indexed_count = 0
        for file in os.listdir(archive_dir):
            if not file.lower().endswith(".dcm"):
                continue
            full_path = os.path.join(archive_dir, file)
            try:
                # पहले check करें कि यह file_path DB में पहले से तो नहीं
                c.execute("SELECT accession FROM dicom_index WHERE file_path = ?", (full_path,))
                if c.fetchone():
                    continue
                ds = pydicom.dcmread(full_path, stop_before_pixels=True)
                accession = str(ds.get("AccessionNumber", "UNKNOWN")).strip()
                patient_id = str(ds.get("PatientID", "N/A")).strip()
                patient_name = str(ds.get("PatientName", "N/A")).strip()
                c.execute("INSERT OR REPLACE INTO dicom_index (accession, patient_id, patient_name, file_path, created_at) VALUES (?,?,?,?,?)",
                          (accession, patient_id, patient_name, full_path, int(os.path.getctime(full_path))))
                indexed_count += 1
            except Exception as e:
                print(f"Indexing failed for {full_path}: {e}")
        conn.commit()
        conn.close()
        print(f"Initial indexing complete: {indexed_count} files added to DB.")

    def index_dicom_file(self, dcm_path, patient_id, patient_name, accession_no):
        """किसी एक DICOM file का record DB में डालें/अपडेट करें"""
        if not os.path.exists(dcm_path):
            return
        db_path = os.path.join(self.config["archive_folder"], "radxr_index.db")
        if not os.path.exists(db_path):
            self.init_db()
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO dicom_index (accession, patient_id, patient_name, file_path, created_at) VALUES (?,?,?,?,?)",
                  (accession_no, patient_id, patient_name, dcm_path, int(time.time())))
        conn.commit()
        conn.close()

    def scan_archive_for_patient_match(self, q_id, q_name):
        """Database से मिलान करें – O(1) Query"""
        db_path = os.path.join(self.config["archive_folder"], "radxr_index.db")
        if not os.path.exists(db_path):
            return None
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        # patient_id exact match और patient_name में substring (lowercase) match
        c.execute("SELECT file_path FROM dicom_index WHERE patient_id = ? AND LOWER(patient_name) LIKE ? LIMIT 1",
                  (q_id, f"%{q_name.lower()}%"))
        result = c.fetchone()
        conn.close()
        return result[0] if result else None

    # ---------- Folder Monitoring Functions (Watchdog) ----------
    def start_folder_monitor(self):
        """Archive Folder पर नज़र रखना शुरू करें"""
        archive_dir = self.config["archive_folder"]
        os.makedirs(archive_dir, exist_ok=True)
        
        # अगर पहले से चल रहा है तो पहले बंद करें
        if self.observer and self.monitoring_active:
            self.stop_folder_monitor()
            
        self.observer = Observer()
        event_handler = DicomArchiveHandler(self)
        self.observer.schedule(event_handler, path=archive_dir, recursive=False)
        self.observer.start()
        self.monitoring_active = True
        print(f"📁 Watching Archive folder: {archive_dir}")

    def stop_folder_monitor(self):
        """Folder Watch बंद करें"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.monitoring_active = False
            print("📁 Folder monitoring stopped.")

    def handle_new_external_dicom(self, file_path):
        """
        जब बाहरी App (या कोई और) Archive folder में नई DICOM डाले,
        तो यह फंक्शन उसे Index करेगा और Dashboard पर दिखाएगा।
        """
        try:
            # फ़ाइल मौजूद है या नहीं
            if not os.path.exists(file_path):
                return
            
            # DICOM पढ़ें (सिर्फ मेटाडेटा)
            ds = pydicom.dcmread(file_path, stop_before_pixels=True)
            patient_id = str(ds.get("PatientID", "N/A")).strip()
            patient_name = str(ds.get("PatientName", "N/A")).strip()
            accession_no = str(ds.get("AccessionNumber", "UNKNOWN")).strip()
            
            # Database में Index करें
            self.index_dicom_file(file_path, patient_id, patient_name, accession_no)
            
            # Dashboard (Treeview) पर दिखाएँ
            self.root.after(0, lambda: self.upsert_grid_record(patient_id, patient_name, accession_no, "Archived (External) 📁"))
            print(f"✅ External DICOM indexed: {accession_no} - {patient_name}")
            
        except Exception as e:
            print(f"❌ Error indexing external DICOM {file_path}: {e}")

    # ---------- GUI Functions ----------
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
        
        # Status for Watcher
        Label(net_card, text="📁 FOLDER WATCH", font=("Arial", 8, "bold"), fg=self.accent_green if self.monitoring_active else self.accent_red, bg=self.bg_card).pack(anchor="w", padx=15, pady=(10,0))
        Label(net_card, text="ACTIVE" if self.monitoring_active else "INACTIVE", font=("Arial", 9, "bold"), fg=self.accent_green if self.monitoring_active else self.accent_red, bg=self.bg_card).pack(anchor="w", padx=15, pady=(0, 10))
        
        Button(net_card, text="Refresh Dashboard", font=("Arial", 8, "bold"), bg="#4b5563", fg=self.text_light, bd=0, width=20, cursor="hand2", command=self.sync_archive_folder_to_dashboard).pack(side="bottom", pady=20)
        
        queue_container = Frame(content_splitter, bg=self.bg_card)
        queue_container.pack(side="right", fill="both", expand=True)
        
        cols = ("id", "name", "mobile", "status")
        self.tree = ttk.Treeview(queue_container, columns=cols, show="headings")
        self.tree.heading("id", text="Patient ID")
        self.tree.heading("name", text="Patient Name")
        self.tree.heading("mobile", text="Accession / Mobile")
        self.tree.heading("status", text="Workflow Dispatch Status")
        
        self.tree.column("id", width=90, anchor="center")
        self.tree.column("name", width=140, anchor="w")
        self.tree.column("mobile", width=120, anchor="center")
        self.tree.column("status", width=110, anchor="center")
        
        self.tree.pack(fill="both", expand=True, side="left")
        self.tree.bind("<Double-1>", self.on_grid_row_double_click_resend)
        
        scrollbar = ttk.Scrollbar(queue_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        
        Label(frame_receiver, text="MADE WITH LOVE BY SANDEEP", font=("Arial", 9, "bold", "italic"), fg="#6b7280", bg=self.bg_dark).pack(side="bottom", pady=5)
        
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
        
        Button(frame_settings, text="Apply Node Topology Changes", font=("Arial", 11, "bold"), bg=self.accent_green, fg=self.bg_dark, width=28, bd=0, cursor="hand2", command=self.apply_and_save_node_settings).pack(pady=15)
        Label(frame_settings, text="MADE WITH LOVE BY SANDEEP", font=("Arial", 9, "bold", "italic"), fg="#6b7280", bg=self.bg_dark).pack(side="bottom", pady=5)

    def sync_archive_folder_to_dashboard(self):
        """Archive की फ़ाइलों को डैशबोर्ड पर दिखाएँ (पुराना तरीका) – अब बस डिस्प्ले के लिए"""
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
                        
                        self.root.after(0, lambda p=patient_id, n=patient_name, a=accession_no: self.upsert_grid_record(p, n, a, "Archive Saved 📁"))
                    except Exception:
                        continue
        threading.Thread(target=worker, daemon=True).start()

    def pick_directory(self, config_key, entry_widget):
        selected_dir = filedialog.askdirectory()
        if selected_dir:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, os.path.normpath(selected_dir))

    def apply_and_save_node_settings(self):
        # पुराना Archive folder बंद करें
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
        self.start_folder_monitor()  # नए Archive folder पर Watch शुरू करें

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
        status = row_values[3]
        accession_no = row_values[2]
        
        if "Failed" in status:
            res = messagebox.askyesno("Resend Trigger", f"Do you want to re-dispatch pipeline for Accession: {accession_no}?")
            if res:
                tgt_dcm = os.path.join(self.config["archive_folder"], f"RADXR_{accession_no}.dcm")
                if not os.path.exists(tgt_dcm):
                    for f in os.listdir(self.config["archive_folder"]):
                        if f.lower().endswith(".dcm"):
                            p = os.path.join(self.config["archive_folder"], f)
                            try:
                                ds = pydicom.dcmread(p, stop_before_pixels=True)
                                if str(ds.get("AccessionNumber", "")).strip() == accession_no:
                                    tgt_dcm = p
                                    break
                            except Exception: continue
                            
                if not os.path.exists(tgt_dcm):
                    tgt_dcm = os.path.join(self.config["receive_folder"], f"RADXR_{accession_no}.dcm")
                    
                if os.path.exists(tgt_dcm):
                    self.tree.item(item_id, values=(row_values[0], row_values[1], accession_no, "⚡ Resending"))
                    th = threading.Thread(target=self.autonomous_processing_pipeline, args=(tgt_dcm, False), daemon=True)
                    th.start()
                else:
                    messagebox.showerror("Error", "Original file could not be found anywhere.")

    def toggle_server_process(self):
        if not self.is_listening:
            os.makedirs(self.config["receive_folder"], exist_ok=True)
            os.makedirs(self.config["archive_folder"], exist_ok=True)
            self.is_listening = True
            self.status_var.set("● Listening")
            self.lbl_status_indicator.config(fg=self.accent_green)
            self.btn_toggle_server.config(text="Stop Server", bg=self.accent_red)
            
            self.server_thread = threading.Thread(target=self.run_dicom_scp_listener, daemon=True)
            self.server_thread.start()
        else:
            self.is_listening = False
            if self.server_instance:
                self.server_instance.shutdown()
            self.status_var.set("● Stopped")
            self.lbl_status_indicator.config(fg=self.accent_red)
            self.btn_toggle_server.config(text="Start Server", bg=self.accent_green)

    # DICOM SCP Listener
    def run_dicom_scp_listener(self):
        ae = AE()
        ae.add_supported_context(sop_class.VerificationSOPClass)
        for uid in sop_class.uid_to_class_name.keys():
            if len(uid) < 45: 
                ae.add_supported_context(uid)
                
        handlers = [
            (evt.EVT_C_STORE, self.handle_incoming_c_store),
            (evt.EVT_C_ECHO, self.handle_incoming_c_echo)
        ]
        try:
            self.server_instance = ae.start_server(
                (self.config["ip_address"], int(self.config["port"])),
                block=False,
                evt_handlers=handlers
            )
            while self.is_listening:
                time.sleep(0.1)
        except Exception as e:
            self.is_listening = False
            self.root.after(0, lambda: messagebox.showerror("Network Binding Error", f"Socket collapse: {str(e)}"))
            self.root.after(0, self.toggle_server_process)

    def handle_incoming_c_echo(self, event):
        return 0x0000

    def handle_incoming_c_store(self, event):
        try:
            dataset = event.dataset
            accession_number = str(dataset.get("AccessionNumber", "UNKNOWN_ACC")).strip()
            
            filename = f"RADXR_{accession_number}.dcm"
            filepath = os.path.join(self.config["receive_folder"], filename)
            event.write_dataset(filepath)
            
            processing_thread = threading.Thread(target=self.autonomous_processing_pipeline, args=(filepath, False), daemon=True)
            processing_thread.start()
            return 0x0000 
        except Exception:
            return 0xC000 

    # PDF Generation (same as before)
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
        """
        DICOM को प्रोसेस करें, Archive में Copy करें, Index करें, PDF भेजें।
        """
        pdf_output_path = ""
        accession_no = "UNKNOWN"
        try:
            # DICOM पढ़ें
            ds = pydicom.dcmread(dcm_path)
            patient_id = str(ds.get("PatientID", "N/A")).strip()
            patient_name = str(ds.get("PatientName", "N/A")).strip()
            accession_no = str(ds.get("AccessionNumber", "UNKNOWN")).strip()

            # 1. फ़ाइल को Archive folder में कॉपी करें (अगर पहले से नहीं है)
            archive_dir = self.config["archive_folder"]
            os.makedirs(archive_dir, exist_ok=True)
            archive_dest = os.path.join(archive_dir, os.path.basename(dcm_path))
            if os.path.normpath(dcm_path) != os.path.normpath(archive_dest):
                shutil.copy2(dcm_path, archive_dest)
                dcm_path_for_index = archive_dest
            else:
                dcm_path_for_index = dcm_path

            # 2. डेटाबेस में Index करें
            self.index_dicom_file(dcm_path_for_index, patient_id, patient_name, accession_no)

            # 3. PDF बनाएँ
            temp_pdf = os.path.join(self.config["receive_folder"], f"Report_{int(time.time())}.pdf")
            self.generate_pdf_report_from_dicom(dcm_path_for_index, temp_pdf)
            
            clean_pname = "".join(x for x in patient_name if x.isalnum() or x in " -_")
            pdf_output_path = os.path.join(self.config["receive_folder"], f"{clean_pname}'s report.pdf")
            
            if os.path.exists(pdf_output_path):
                os.remove(pdf_output_path)
            os.rename(temp_pdf, pdf_output_path)

            # UI Update
            self.root.after(0, lambda: self.upsert_grid_record(patient_id, patient_name, accession_no, "⏳ Processing"))
            self.root.after(0, lambda: self.upsert_grid_record(patient_id, patient_name, accession_no, "📤 Sending"))
            
            # 4. Telegram & WhatsApp भेजें
            tg_ok = self.dispatch_to_telegram(pdf_output_path, patient_id, patient_name, accession_no, self.TELEGRAM_CHAT_ID)
            wa_ok = True
            if self.config["whatsapp_api_key"]:
                wa_ok = self.dispatch_to_whatsapp_business(pdf_output_path, patient_id, patient_name, accession_no)

            # 5. परिणाम
            if tg_ok and wa_ok:
                self.root.after(0, lambda: self.upsert_grid_record(patient_id, patient_name, accession_no, "Sent & Archived ✅"))
                if os.path.exists(pdf_output_path):
                    os.remove(pdf_output_path)
                if not is_manual_import and os.path.exists(dcm_path) and os.path.normpath(dcm_path) != os.path.normpath(archive_dest):
                    os.remove(dcm_path)
            else:
                self.root.after(0, lambda: self.upsert_grid_record(patient_id, patient_name, accession_no, "Failed ❌ (Double-Click)"))
                
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Pipeline Error", f"Error: {str(e)}"))
            if accession_no in self.queue_data:
                self.root.after(0, lambda: self.upsert_grid_record("N/A", "N/A", accession_no, "Failed ❌"))

    def upsert_grid_record(self, p_id, p_name, acc_no, status):
        if acc_no in self.queue_data:
            self.tree.item(self.queue_data[acc_no], values=(p_id, p_name, acc_no, status))
        else:
            row_id = self.tree.insert("", "end", values=(p_id, p_name, acc_no, status))
            self.queue_data[acc_no] = row_id

    def build_beautiful_caption_string(self, p_id, p_name, acc_no):
        return (
            f"🏥 *{self.config['institute_name']}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Patient Name:* {p_name}\n"
            f"🆔 *Patient ID:* {p_id}\n"
            f"🔢 *Accession No:* {acc_no}\n\n"
            f"❤️ *Made with love by Sandeep*"
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

    # ---------- Telegram Bot ----------
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
                                    "Apne Patient ki file report paane ke liye niche diye format mein text send karein:\n\n"
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
                                
                                requests.post(f"{base_url}/sendMessage", json={"chat_id": chat_id, "text": "🔍 Searching archive index... (Lightning fast)"})
                                
                                matched_file = self.scan_archive_for_patient_match(query_id, query_name)
                                if matched_file:
                                    try:
                                        ds_test = pydicom.dcmread(matched_file, stop_before_pixels=True)
                                        p_name_real = str(ds_test.get("PatientName", "Report")).strip()
                                        clean_pname = "".join(x for x in p_name_real if x.isalnum() or x in " -_")
                                        bot_pdf_path = os.path.join(self.config["receive_folder"], f"{clean_pname}'s report.pdf")
                                        
                                        p_id, p_name, acc_no = self.generate_pdf_report_from_dicom(matched_file, bot_pdf_path)
                                        self.dispatch_to_telegram(bot_pdf_path, p_id, p_name, acc_no, chat_id)
                                        
                                        self.root.after(0, lambda pi=p_id, pn=p_name, ac=acc_no: self.upsert_grid_record(pi, pn, ac, "Archive Saved 📁"))
                                    except Exception as ex:
                                        requests.post(f"{base_url}/sendMessage", json={"chat_id": chat_id, "text": f"❌ File processing failed: {str(ex)}"})
                                    finally:
                                        if os.path.exists(bot_pdf_path):
                                            os.remove(bot_pdf_path)
                                else:
                                    requests.post(f"{base_url}/sendMessage", json={"chat_id": chat_id, "text": f"❌ No matching records located for ID: `{query_id}` with Name containing: `{query_name}`.", "parse_mode": "Markdown"})
            except Exception as e:
                print(f"Bot polling error: {e}")
            time.sleep(1)

if __name__ == "__main__":
    root = Tk()
    app = RadXrReceiverApp(root)
    root.mainloop()
