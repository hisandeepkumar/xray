import os
import sys
import socket
import json
import threading
import time
import shutil
import sqlite3
import winreg
from tkinter import Tk, Label, Entry, Button, StringVar, messagebox, ttk, filedialog, Frame, Text, Scrollbar, END, Checkbutton, IntVar, PhotoImage, Toplevel
import numpy as np
import pydicom
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import requests

from pynetdicom import AE, evt, sop_class
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ------------------------------------------------------------
# HARD‑CODED CONSTANTS (NOT stored in config file)
# ------------------------------------------------------------
MASTER_PASSWORD = "Sandeep@123"
DEFAULT_MASTER_USER_ID = "878604830"
DEFAULT_TELEGRAM_BOT_TOKEN = "7941135502:AAHz-KGvAAoZEhPVgfVKw3zFbkaB0_Pi5rM"
DEFAULT_WHATSAPP_API_KEY = ""
CONFIG_PASSWORD = "18040709"   # password to open Config Control tab
# ------------------------------------------------------------

CONFIG_DIR = r"C:\RAD-XR"
CONFIG_FILE = os.path.join(CONFIG_DIR, "rad_xr_config.json")
DATABASE_DIR = os.path.join(CONFIG_DIR, "DATABASE")
DATABASE_PATH = os.path.join(DATABASE_DIR, "radxr_index.db")

class DicomArchiveHandler(FileSystemEventHandler):
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
        
        # Load icon
        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
            if os.path.exists(icon_path):
                icon_img = PhotoImage(file=icon_path)
                self.root.iconphoto(True, icon_img)
        except Exception:
            pass
        
        self.bg_dark = "#1e1e24"
        self.bg_card = "#2a2a35"
        self.text_light = "#f3f4f6"
        self.accent_cyan = "#06b6d4"
        self.accent_green = "#10b981"
        self.accent_red = "#ef4444"
        
        os.makedirs(CONFIG_DIR, exist_ok=True)
        os.makedirs(DATABASE_DIR, exist_ok=True)
        
        self.config = {
            "password_verified": False,
            "whatsapp_api_key": DEFAULT_WHATSAPP_API_KEY,
            "institute_name": "RAD-XR IMAGING CENTER",
            "ae_title": "RAD-XR",
            "ip_address": self.get_local_ip(),
            "port": "11112",
            "receive_folder": "D:\\RAD-XR\\Inbox",
            "archive_folder": "D:\\RAD-XR\\Archive",
            "telegram_bot_token": DEFAULT_TELEGRAM_BOT_TOKEN,
            "footer_message": "",
            "auto_start": False,
            "bot_display_name": "RAD-XR Bot"
        }
        
        self.TELEGRAM_BOT_TOKEN = None
        self.TELEGRAM_MASTER_USER_ID = DEFAULT_MASTER_USER_ID
        self.allowed_users = [DEFAULT_MASTER_USER_ID]
        self.footer_message = ""
        self.bot_username = ""
        self.config_unlocked = False   # will be reset on each tab selection
        
        self.server_instance = None
        self.is_listening = False
        self.bot_running = True
        self.queue_data = {}
        self.last_update_id = 0
        
        self.observer = None
        self.monitoring_active = False
        self.indexing_in_progress = False
        self.lbl_index_progress_monitor = None
        self.lbl_index_progress_config = None
        self.log_widget = None
        self.lbl_bot_name = None
        self.lbl_bot_username = None
        self.lock_frame = None
        self.config_pass_var = None
        
        self.load_configuration()
        self.setup_modern_styles()
        
        if self.config.get("auto_start", False):
            self._add_to_startup()
        else:
            self._remove_from_startup()
        
        self.init_db()
        self.init_telegram_users_table()
        self.update_bot_username()
        
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

    # ---------- Auto‑Start Registry ----------
    def _get_app_path(self):
        if getattr(sys, 'frozen', False):
            return sys.executable
        else:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(pythonw):
                pythonw = sys.executable
            return f'"{pythonw}" "{os.path.abspath(__file__)}"'

    def _add_to_startup(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, "RAD-XR", 0, winreg.REG_SZ, self._get_app_path())
            winreg.CloseKey(key)
            self.log_message("✅ Added to Windows Startup")
        except Exception as e:
            self.log_message(f"❌ Failed to add to startup: {e}")

    def _remove_from_startup(self):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, "RAD-XR")
            winreg.CloseKey(key)
            self.log_message("🗑️ Removed from Windows Startup")
        except FileNotFoundError:
            pass
        except Exception as e:
            self.log_message(f"❌ Failed to remove from startup: {e}")

    # ---------- Configuration ----------
    def load_configuration(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    loaded_data = json.load(f)
                    self.config.update(loaded_data)
            except Exception:
                pass
        self.config.setdefault("telegram_bot_token", DEFAULT_TELEGRAM_BOT_TOKEN)
        self.config.setdefault("footer_message", "")
        self.config.setdefault("whatsapp_api_key", DEFAULT_WHATSAPP_API_KEY)
        self.config.setdefault("institute_name", "RAD-XR IMAGING CENTER")
        self.config.setdefault("ae_title", "RAD-XR")
        self.config.setdefault("ip_address", self.get_local_ip())
        self.config.setdefault("port", "11112")
        self.config.setdefault("receive_folder", "D:\\RAD-XR\\Inbox")
        self.config.setdefault("archive_folder", "D:\\RAD-XR\\Archive")
        self.config.setdefault("auto_start", False)
        self.config.setdefault("bot_display_name", "RAD-XR Bot")
        
        self.TELEGRAM_BOT_TOKEN = self.config["telegram_bot_token"]
        self.footer_message = self.config.get("footer_message", "")
        self.allowed_users = [DEFAULT_MASTER_USER_ID]

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

    def log_message(self, msg):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        full_msg = f"[{timestamp}] {msg}"
        print(full_msg, flush=True)
        if self.log_widget:
            self.log_widget.insert(END, full_msg + "\n")
            self.log_widget.see(END)
            self.root.update_idletasks()

    # ---------- Database ----------
    def init_db(self):
        os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
        conn = sqlite3.connect(DATABASE_PATH)
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
        return DATABASE_PATH

    def init_telegram_users_table(self):
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS telegram_users (
                        user_id TEXT PRIMARY KEY,
                        username TEXT,
                        full_name TEXT,
                        first_seen INTEGER
                     )''')
        conn.commit()
        conn.close()

    def save_telegram_user(self, user_id, username, full_name):
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO telegram_users (user_id, username, full_name, first_seen)
                     VALUES (?, ?, ?, COALESCE((SELECT first_seen FROM telegram_users WHERE user_id=?), ?))''',
                  (user_id, username, full_name, user_id, int(time.time())))
        conn.commit()
        conn.close()

    def delete_telegram_user(self, user_id):
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM telegram_users WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

    def get_all_telegram_users(self):
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM telegram_users")
        results = [row[0] for row in c.fetchall()]
        conn.close()
        return results

    def update_bot_username(self):
        """Fetch bot info from Telegram and update self.bot_username and config display name."""
        if not self.TELEGRAM_BOT_TOKEN:
            return
        try:
            url = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/getMe"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    self.bot_username = data["result"].get("username", "")
                    self.log_message(f"Bot username: @{self.bot_username}")
                    if not self.config.get("bot_display_name") or self.config["bot_display_name"] == "RAD-XR Bot":
                        self.config["bot_display_name"] = data["result"].get("first_name", "RAD-XR Bot")
                        self.save_configuration()
                    self.refresh_bot_info_gui()
        except Exception as e:
            self.log_message(f"Failed to fetch bot info: {e}")

    def refresh_bot_info_gui(self):
        """Update the bot name and username labels in Network Config."""
        if self.lbl_bot_name:
            self.lbl_bot_name.config(text=f"Name: {self.config.get('bot_display_name', 'RAD-XR Bot')}")
        if self.lbl_bot_username:
            bot_uname = f"@{self.bot_username}" if self.bot_username else "Not available"
            self.lbl_bot_username.config(text=f"Username: {bot_uname}")

    # ---------- Indexing ----------
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

        self.init_db()
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()

        if reindex:
            self.log_message("Re-indexing: dropping existing table...")
            c.execute("DROP TABLE IF EXISTS dicom_index")
            self.init_db()
            conn = sqlite3.connect(DATABASE_PATH)
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

    def index_dicom_file(self, dcm_path, patient_id, patient_name, accession_no):
        if not os.path.exists(dcm_path):
            return
        self.init_db()
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO dicom_index (file_path, accession, patient_id, patient_name, created_at) VALUES (?,?,?,?,?)",
                  (dcm_path, accession_no, patient_id, patient_name, int(time.time())))
        conn.commit()
        conn.close()

    def get_patient_files_from_db(self, q_id, q_name):
        self.init_db()
        conn = sqlite3.connect(DATABASE_PATH)
        c = conn.cursor()
        name_prefix = q_name[:4].lower() if len(q_name) >= 4 else q_name.lower()
        c.execute("""
            SELECT file_path, patient_id, patient_name, accession
            FROM dicom_index
            WHERE patient_id = ? AND LOWER(patient_name) LIKE ?
        """, (q_id.strip(), f"{name_prefix}%"))
        results = c.fetchall()
        conn.close()
        return results

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
        if self.pass_var.get() == MASTER_PASSWORD:
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
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=15)
        frame_receiver = Frame(self.notebook, bg=self.bg_dark)
        frame_settings = Frame(self.notebook, bg=self.bg_dark)
        self.notebook.add(frame_receiver, text="  Live Monitor  ")
        self.notebook.add(frame_settings, text="  Config Control  ")

        # --- Build Live Monitor Tab (no password) ---
        self.build_live_monitor_tab(frame_receiver)

        # --- Build Config Control Tab (password protected) ---
        self.build_config_tab(frame_settings)

        # Bind tab selection event to check for password
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

        # Refresh bot info in GUI
        self.refresh_bot_info_gui()

    def on_tab_change(self, event=None):
        """Called when user switches tabs. If Config Control is selected, show lock."""
        if not self.notebook:
            return
        selected = self.notebook.select()
        tab_text = self.notebook.tab(selected, "text")
        if tab_text == "  Config Control  " and hasattr(self, 'lock_frame') and self.lock_frame:
            # Always show lock and reset unlocked state
            self.config_unlocked = False
            self.lock_frame.place(relx=0, rely=0, relwidth=1, relheight=1)
            # Clear password entry if it exists
            if self.config_pass_var:
                self.config_pass_var.set("")
            # Focus on the password entry
            for child in self.lock_frame.winfo_children():
                if isinstance(child, Frame):
                    for sub in child.winfo_children():
                        if isinstance(sub, Entry):
                            sub.focus()
                            break

    def unlock_config_tab(self):
        """Verify password and unlock Config Control tab."""
        if self.config_pass_var.get() == CONFIG_PASSWORD:
            self.config_unlocked = True
            if self.lock_frame:
                self.lock_frame.place_forget()
            messagebox.showinfo("Success", "Config Control unlocked!")
        else:
            messagebox.showerror("Error", "Incorrect password!")
            # Clear and refocus
            self.config_pass_var.set("")
            for child in self.lock_frame.winfo_children():
                if isinstance(child, Frame):
                    for sub in child.winfo_children():
                        if isinstance(sub, Entry):
                            sub.focus()
                            break

    def build_live_monitor_tab(self, parent):
        top_ctrl_bar = Frame(parent, bg=self.bg_dark)
        top_ctrl_bar.pack(fill="x", pady=15, padx=15)
        Label(top_ctrl_bar, text="RAD-XR PROCESS CONTROL", font=("Arial", 14, "bold"), fg=self.text_light, bg=self.bg_dark).pack(side="left")
        self.status_var = StringVar(value="● Stopped")
        self.lbl_status_indicator = Label(top_ctrl_bar, textvariable=self.status_var, font=("Arial", 11, "bold"), fg=self.accent_red, bg=self.bg_dark)
        self.lbl_status_indicator.pack(side="left", padx=20)
        btn_manual_upload = Button(top_ctrl_bar, text="+ Import DICOM File", font=("Arial", 9, "bold"), bg=self.accent_cyan, fg=self.bg_dark, bd=0, padx=10, pady=5, cursor="hand2", command=self.manual_file_upload_trigger)
        btn_manual_upload.pack(side="right", padx=5)
        self.btn_toggle_server = Button(top_ctrl_bar, text="Start Server", bg=self.accent_green, fg=self.bg_dark, font=("Arial", 9, "bold"), bd=0, padx=10, pady=5, width=12, cursor="hand2", command=self.toggle_server_process)
        self.btn_toggle_server.pack(side="right", padx=5)

        content_splitter = Frame(parent, bg=self.bg_dark)
        content_splitter.pack(fill="both", expand=True, padx=15, pady=5)

        # Left panel: network + bot info
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

        # Bot info (with updatable labels)
        Label(net_card, text="🤖 TELEGRAM BOT", font=("Arial", 8, "bold"), fg=self.accent_cyan, bg=self.bg_card).pack(anchor="w", padx=15, pady=(10, 0))
        bot_display = self.config.get("bot_display_name", "RAD-XR Bot")
        self.lbl_bot_name = Label(net_card, text=f"Name: {bot_display}", font=("Arial", 9), fg=self.text_light, bg=self.bg_card, wraplength=190, justify="left")
        self.lbl_bot_name.pack(anchor="w", padx=15, pady=(0, 2))
        bot_uname = f"@{self.bot_username}" if self.bot_username else "Not available"
        self.lbl_bot_username = Label(net_card, text=f"Username: {bot_uname}", font=("Arial", 9), fg="#9ca3af", bg=self.bg_card, wraplength=190, justify="left")
        self.lbl_bot_username.pack(anchor="w", padx=15, pady=(0, 5))
        Label(net_card, text="Search on Telegram: @...", font=("Arial", 7), fg="#6b7280", bg=self.bg_card).pack(anchor="w", padx=15, pady=(0, 5))

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

        # Console
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

        progress_frame = Frame(parent, bg=self.bg_dark)
        progress_frame.pack(fill="x", padx=15, pady=5)
        self.lbl_index_progress_monitor = Label(progress_frame, text="✅ Indexing ready.", font=("Arial", 9), fg=self.accent_green, bg=self.bg_dark)
        self.lbl_index_progress_monitor.pack(side="left")
        Label(progress_frame, text="Made with ❤️ by Sandeep", font=("Arial", 9, "bold", "italic"), fg="#6b7280", bg=self.bg_dark).pack(side="right")

    def build_config_tab(self, parent):
        """Build the Config Control tab content and place a lock overlay."""
        # Create a container for the actual content
        content_frame = Frame(parent, bg=self.bg_card)
        content_frame.pack(fill="both", expand=True)

        # We'll build the content inside content_frame
        Label(content_frame, text="SYSTEM INITIALIZATION TARGETS", font=("Arial", 14, "bold"), fg=self.accent_cyan, bg=self.bg_card).pack(pady=15)

        form = Frame(content_frame, bg=self.bg_card)
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

        # Auto‑Start Checkbox
        self.auto_start_var = IntVar(value=1 if self.config.get("auto_start", False) else 0)
        def toggle_auto_start():
            enable = bool(self.auto_start_var.get())
            self.config["auto_start"] = enable
            if enable:
                self._add_to_startup()
            else:
                self._remove_from_startup()
            self.save_configuration()
            self.log_message(f"Auto‑start {'enabled' if enable else 'disabled'}")
        cb_auto = Checkbutton(form, text="🚀 Launch on System Startup (Windows)", variable=self.auto_start_var,
                              command=toggle_auto_start, bg=self.bg_card, fg=self.text_light,
                              selectcolor=self.bg_card, font=("Arial", 10, "bold"))
        cb_auto.pack(anchor="w", padx=20, pady=8)

        # Database
        db_frame = Frame(form, bg=self.bg_card)
        db_frame.pack(fill="x", pady=5, padx=20)
        Label(db_frame, text="Database Path (fixed):", font=("Arial", 9, "bold"), fg=self.text_light, bg=self.bg_card).pack(anchor="w")
        lbl_db_path = Label(db_frame, text=DATABASE_PATH, font=("Arial", 9), fg="#9ca3af", bg=self.bg_card, wraplength=500, justify="left")
        lbl_db_path.pack(anchor="w", side="left")
        Button(db_frame, text="📋 Copy Path", font=("Arial", 8, "bold"), bg="#4b5563", fg=self.text_light, bd=0, padx=5, pady=2, cursor="hand2",
               command=lambda: self.copy_to_clipboard(DATABASE_PATH)).pack(side="left", padx=10)

        self.lbl_index_progress_config = Label(form, text="✅ Indexing ready.", font=("Arial", 9), fg=self.accent_green, bg=self.bg_card)
        self.lbl_index_progress_config.pack(anchor="w", padx=20, pady=(5,10))
        Button(form, text="🔄 Re-index Archive (Full Rebuild)", font=("Arial", 9, "bold"), bg=self.accent_cyan, fg=self.bg_dark, bd=0, padx=10, pady=5, cursor="hand2", command=self.reindex_archive).pack(anchor="w", padx=20, pady=5)

        Button(content_frame, text="Apply Node Topology Changes", font=("Arial", 11, "bold"), bg=self.accent_green, fg=self.bg_dark, width=28, bd=0, cursor="hand2", command=self.apply_and_save_node_settings).pack(pady=15)
        Label(content_frame, text="Made with ❤️ by Sandeep", font=("Arial", 9, "bold", "italic"), fg="#6b7280", bg=self.bg_card).pack(side="bottom", pady=5)

        # --- Lock overlay (always shown initially) ---
        self.lock_frame = Frame(parent, bg=self.bg_dark)
        self.lock_frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        lock_card = Frame(self.lock_frame, bg=self.bg_card, bd=2, relief="ridge")
        lock_card.place(relx=0.5, rely=0.5, anchor="center", width=350, height=180)
        Label(lock_card, text="🔒 Config Control Locked", font=("Arial", 14, "bold"), fg=self.accent_cyan, bg=self.bg_card).pack(pady=(20,10))
        Label(lock_card, text="Enter password to access settings:", font=("Arial", 10), fg=self.text_light, bg=self.bg_card).pack(pady=5)
        self.config_pass_var = StringVar()
        entry_cfg_pass = Entry(lock_card, textvariable=self.config_pass_var, show="*", font=("Arial", 12), width=20, justify="center", bg=self.bg_dark, fg=self.text_light, bd=1)
        entry_cfg_pass.pack(pady=5)
        entry_cfg_pass.focus()
        btn_unlock = Button(lock_card, text="Unlock", font=("Arial", 10, "bold"), bg=self.accent_cyan, fg=self.bg_dark, width=12, command=self.unlock_config_tab)
        btn_unlock.pack(pady=10)

        # Bind Enter key to unlock
        entry_cfg_pass.bind("<Return>", lambda e: self.unlock_config_tab())

    # ---------- Helpers ----------
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

    # ---------- DICOM Server ----------
    def toggle_server_process(self):
        if not self.is_listening:
            port = int(self.config["port"])
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
        raw_ae = self.config["ae_title"]
        sanitized = ''.join(c if c.isalnum() or c in ' _' else '_' for c in raw_ae)
        ae.ae_title = sanitized
        self.log_message(f"   Sanitized AE Title: '{ae.ae_title}'")
        try:
            ae.add_supported_context("1.2.840.10008.1.1")
            common_storage_classes = [
                "1.2.840.10008.5.1.4.1.1.1",
                "1.2.840.10008.5.1.4.1.1.2",
                "1.2.840.10008.5.1.4.1.1.4",
                "1.2.840.10008.5.1.4.1.1.7",
                "1.2.840.10008.5.1.4.1.1.12.1",
                "1.2.840.10008.5.1.4.1.1.12.2",
                "1.2.840.10008.5.1.4.1.1.20",
                "1.2.840.10008.5.1.4.1.1.6.1",
            ]
            for uid in common_storage_classes:
                ae.add_supported_context(uid)
            handlers = [
                (evt.EVT_C_STORE, self.handle_incoming_c_store),
                (evt.EVT_C_ECHO, self.handle_incoming_c_echo)
            ]
            self.log_message("⏳ Attempting to bind to 0.0.0.0:" + self.config["port"])
            if sys.stdout is not None:
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

    # ---------- PDF Generation ----------
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
        study_date = str(ds.get("StudyDate", "N/A")).strip()

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
            ("Study Date", study_date),
            ("Modality", str(ds.get("Modality", "N/A"))),
            ("Accession No", accession_no)
        ]
        available_metadata = [(k, v) for k, v in metadata if v.strip() and v != "N/A"]

        footer_text = self.footer_message.strip()

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

            if footer_text:
                c.setFont("Helvetica", 8)
                c.setFillColorRGB(0.4, 0.4, 0.4)
                footer_y = 30
                c.drawCentredString(width / 2, footer_y, footer_text)
                c.setFillColorRGB(0, 0, 0)

            if frame_idx < num_frames - 1:
                c.showPage()

        c.showPage()
        c.save()
        return patient_id, patient_name, accession_no

    # ---------- Processing Pipeline ----------
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

            clean_pname = "".join(x for x in patient_name if x.isalnum() or x in " -_")
            pdf_output_path = os.path.join(
                self.config["receive_folder"],
                f"{clean_pname}'s medical report.pdf"
            )
            self.generate_pdf_report_from_dicom(dcm_path_for_index, pdf_output_path)

            file_key = dcm_path_for_index
            self.root.after(0, lambda: self.upsert_grid_record(file_key, patient_id, patient_name, accession_no, "⏳ Processing"))
            self.root.after(0, lambda: self.upsert_grid_record(file_key, patient_id, patient_name, accession_no, "📤 Sending"))

            tg_ok = self.send_to_all_telegram(pdf_output_path, patient_id, patient_name, accession_no)
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

    def build_beautiful_caption_string(self, p_id, p_name, acc_no, include_footer=True):
        caption = (
            f"🏥 *{self.config['institute_name']}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Patient Name:* {p_name}\n"
            f"🆔 *Patient ID:* {p_id}\n"
            f"🔢 *Accession No:* {acc_no}\n"
        )
        if include_footer and self.footer_message.strip():
            caption += f"\n{self.footer_message.strip()}\n"
        caption += f"\n*Made with ❤️ by Sandeep*"
        return caption

    # ---------- Telegram ----------
    def send_to_all_telegram(self, file_path, p_id, p_name, acc_no):
        user_ids = self.get_all_telegram_users()
        if not user_ids:
            self.log_message("No Telegram users registered.")
            return True
        success = True
        for chat_id in user_ids:
            ok = self.dispatch_to_telegram(file_path, p_id, p_name, acc_no, chat_id)
            if not ok:
                success = False
                self.log_message(f"❌ Failed to send to Telegram user {chat_id}")
        return success

    def dispatch_to_telegram(self, file_path, p_id, p_name, acc_no, target_chat_id):
        url = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/sendDocument"
        try:
            caption_text = self.build_beautiful_caption_string(p_id, p_name, acc_no, include_footer=True)
            with open(file_path, "rb") as document:
                payload = {
                    "chat_id": target_chat_id,
                    "caption": caption_text,
                    "parse_mode": "Markdown"
                }
                files = {"document": (os.path.basename(file_path), document, "application/pdf")}
                res = requests.post(url, data=payload, files=files, timeout=25)
                return res.status_code == 200
        except Exception as e:
            self.log_message(f"Telegram send error: {e}")
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
            caption_text = self.build_beautiful_caption_string(p_id, p_name, acc_no, include_footer=True)
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
        except Exception as e:
            self.log_message(f"WhatsApp send error: {e}")
            return False

    # ---------- Telegram Bot Polling ----------
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
                        if "message" not in update:
                            continue
                        msg = update["message"]
                        chat_id = str(msg["chat"]["id"])
                        text = msg.get("text", "").strip()
                        # Save user info
                        user = msg.get("from", {})
                        user_id = str(user.get("id", ""))
                        username = user.get("username", "")
                        full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
                        if user_id:
                            self.save_telegram_user(user_id, username, full_name)

                        # --- Commands ---
                        if text.lower().startswith("/start"):
                            welcome = (
                                f"🏥 *Welcome to RAD-XR Portal Search Node*\n\n"
                                f"Your User ID: `{chat_id}`\n\n"
                                "To retrieve your patient's report(s), send the following format:\n"
                                "`[PATIENT ID]`\n"
                                "`[PATIENT FIRST NAME]`\n\n"
                                "*Example:*\n"
                                "`1898`\n"
                                "`sandeep`"
                            )
                            if self.footer_message.strip():
                                welcome += f"\n\n📝 *Message from Admin:* {self.footer_message.strip()}"
                            self._send_message(base_url, chat_id, welcome)
                            continue

                        # --- Master commands ---
                        if chat_id == self.TELEGRAM_MASTER_USER_ID:
                            # /newbot <token>
                            if text.lower().startswith("/newbot "):
                                new_token = text[8:].strip()
                                if new_token:
                                    self.TELEGRAM_BOT_TOKEN = new_token
                                    self.last_update_id = 0
                                    self.config["telegram_bot_token"] = new_token
                                    self.save_configuration()
                                    base_url = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}"
                                    self.update_bot_username()
                                    self.refresh_bot_info_gui()
                                    self._send_message(base_url, chat_id, f"✅ Bot token updated successfully. New token: `{new_token}`")
                                    self.log_message(f"Bot token changed to {new_token}")
                                else:
                                    self._send_message(base_url, chat_id, "❌ Please provide a valid token: `/newbot <token>`")
                                continue

                            # /adduser <userid>
                            if text.lower().startswith("/adduser "):
                                uid = text[9:].strip()
                                if uid:
                                    self.save_telegram_user(uid, "", "")
                                    self._send_message(base_url, chat_id, f"✅ User `{uid}` added to broadcast list.")
                                    self.log_message(f"Added Telegram user {uid}")
                                else:
                                    self._send_message(base_url, chat_id, "❌ Please provide a user ID: `/adduser <userid>`")
                                continue

                            # /remove <userid>
                            if text.lower().startswith("/remove "):
                                uid = text[8:].strip()
                                if uid == self.TELEGRAM_MASTER_USER_ID:
                                    self._send_message(base_url, chat_id, "❌ Cannot remove the master user.")
                                elif uid:
                                    self.delete_telegram_user(uid)
                                    self._send_message(base_url, chat_id, f"✅ User `{uid}` removed from broadcast list.")
                                    self.log_message(f"Removed Telegram user {uid}")
                                else:
                                    self._send_message(base_url, chat_id, "❌ Please provide a user ID: `/remove <userid>`")
                                continue

                            # /message <text>
                            if text.lower().startswith("/message "):
                                new_msg = text[9:].strip()
                                self.footer_message = new_msg
                                self.config["footer_message"] = new_msg
                                self.save_configuration()
                                self._send_message(base_url, chat_id, f"✅ Footer message updated to:\n\n{new_msg}")
                                self.log_message(f"Footer message changed to: {new_msg}")
                                continue

                            # /addbotname <name>
                            if text.lower().startswith("/addbotname "):
                                new_name = text[12:].strip()
                                if new_name:
                                    try:
                                        set_url = f"{base_url}/setMyName?name={new_name}"
                                        resp = requests.get(set_url, timeout=10)
                                        if resp.status_code == 200 and resp.json().get("ok"):
                                            self.config["bot_display_name"] = new_name
                                            self.save_configuration()
                                            self.refresh_bot_info_gui()
                                            self._send_message(base_url, chat_id, f"✅ Bot display name updated to: {new_name}")
                                            self.log_message(f"Bot name changed to {new_name}")
                                        else:
                                            self._send_message(base_url, chat_id, "❌ Failed to update bot name via Telegram API.")
                                    except Exception as e:
                                        self._send_message(base_url, chat_id, f"❌ Error: {e}")
                                else:
                                    self._send_message(base_url, chat_id, "❌ Please provide a name: `/addbotname MyBot`")
                                continue

                            # /broadcast <message>
                            if text.lower().startswith("/broadcast "):
                                broadcast_msg = text[11:].strip()
                                if broadcast_msg:
                                    self._broadcast_text(base_url, broadcast_msg, chat_id)
                                else:
                                    self._send_message(base_url, chat_id, "❌ Please provide a message: `/broadcast Hello everyone`")
                                continue

                            # /prompt
                            if text.lower() == "/prompt":
                                help_text = (
                                    "*Available Commands (Master only):*\n\n"
                                    "/newbot `<token>` – Change Telegram bot token.\n"
                                    "/adduser `<userid>` – Add a user to broadcast list.\n"
                                    "/remove `<userid>` – Remove a user from broadcast list.\n"
                                    "/message `<text>` – Set custom footer message (appears in PDF captions & inside PDF).\n"
                                    "/addbotname `<name>` – Change bot display name.\n"
                                    "/broadcast `<message>` – Send text message to all users.\n"
                                    "Reply to any message with `/broadcast` – forward that message to all users.\n"
                                    "/prompt – Show this help message.\n\n"
                                    "Any user can send `/start` to get their ID and a welcome message.\n"
                                    "To request a report, send:\n"
                                    "`[PATIENT ID]`\n"
                                    "`[PATIENT FIRST NAME]`"
                                )
                                self._send_message(base_url, chat_id, help_text)
                                continue

                            # Reply broadcast (if reply_to_message and text == "/broadcast")
                            if msg.get("reply_to_message") and text.lower() == "/broadcast":
                                reply_to = msg["reply_to_message"]
                                self._broadcast_reply(base_url, reply_to, chat_id)
                                continue

                        # --- Patient Query (any user) ---
                        lines = [line.strip() for line in text.split("\n") if line.strip()]
                        if len(lines) >= 2:
                            query_id = lines[0]
                            query_name = lines[1].lower()
                            matched_entries = self.get_patient_files_from_db(query_id, query_name)

                            if matched_entries:
                                valid_entries = []
                                for entry in matched_entries:
                                    file_path, p_id, p_name, acc_no = entry
                                    if os.path.exists(file_path):
                                        valid_entries.append(entry)
                                    else:
                                        self._send_message(base_url, chat_id,
                                            f"⚠️ File for Patient `{p_name}` (ID: {p_id}) is **deleted or not available**.")
                                if not valid_entries:
                                    self._send_message(base_url, chat_id, "❌ No available files found for this patient.")
                                    continue

                                self._send_message(base_url, chat_id,
                                    f"🔍 Found **{len(valid_entries)}** available DICOM file(s). Generating PDF(s)...")
                                for idx, entry in enumerate(valid_entries, 1):
                                    file_path, p_id, p_name, acc_no = entry
                                    try:
                                        self._send_message(base_url, chat_id, f"📄 Generating PDF {idx} / {len(valid_entries)}...")
                                        clean_pname = "".join(x for x in p_name if x.isalnum() or x in " -_")
                                        bot_pdf_path = os.path.join(
                                            self.config["receive_folder"],
                                            f"{clean_pname}'s medical report_{idx}_{int(time.time())}.pdf"
                                        )
                                        self.generate_pdf_report_from_dicom(file_path, bot_pdf_path)
                                        self.dispatch_to_telegram(bot_pdf_path, p_id, p_name, acc_no, chat_id)
                                        self.root.after(0, lambda pi=p_id, pn=p_name, ac=acc_no, fp=file_path:
                                                        self.upsert_grid_record(fp, pi, pn, ac, "📤 Sent via Bot (Multi)"))
                                        if os.path.exists(bot_pdf_path):
                                            os.remove(bot_pdf_path)
                                    except Exception as ex:
                                        self._send_message(base_url, chat_id, f"❌ Error processing file {idx}: {str(ex)}")
                                        self.log_message(f"❌ Bot error: {ex}")
                                    time.sleep(0.5)
                                self._send_message(base_url, chat_id, f"✅ All {len(valid_entries)} PDF(s) sent successfully!")
                            else:
                                self._send_message(base_url, chat_id,
                                    f"❌ No records found for Patient ID: `{query_id}` and Name: `{query_name}`.")
            except Exception as e:
                self.log_message(f"Bot polling error: {e}")
            time.sleep(1)

    def _send_message(self, base_url, chat_id, text, parse_mode="Markdown"):
        try:
            requests.post(f"{base_url}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode}, timeout=10)
        except Exception as e:
            self.log_message(f"Error sending message: {e}")

    def _broadcast_text(self, base_url, text, master_chat_id):
        users = self.get_all_telegram_users()
        if not users:
            self._send_message(base_url, master_chat_id, "No users to broadcast to.")
            return
        count = 0
        for uid in users:
            try:
                requests.post(f"{base_url}/sendMessage", json={"chat_id": uid, "text": text, "parse_mode": "Markdown"}, timeout=10)
                count += 1
            except Exception as e:
                self.log_message(f"Broadcast failed to {uid}: {e}")
        self._send_message(base_url, master_chat_id, f"✅ Broadcast sent to {count} users.")

    def _broadcast_reply(self, base_url, reply_msg, master_chat_id):
        users = self.get_all_telegram_users()
        if not users:
            self._send_message(base_url, master_chat_id, "No users to broadcast to.")
            return
        count = 0
        for uid in users:
            try:
                orig_chat_id = reply_msg["chat"]["id"]
                orig_msg_id = reply_msg["message_id"]
                copy_url = f"{base_url}/copyMessage"
                payload = {
                    "chat_id": uid,
                    "from_chat_id": orig_chat_id,
                    "message_id": orig_msg_id
                }
                if "caption" in reply_msg:
                    payload["caption"] = reply_msg["caption"]
                resp = requests.post(copy_url, json=payload, timeout=15)
                if resp.status_code == 200:
                    count += 1
                else:
                    self.log_message(f"Copy failed for {uid}: {resp.text}")
            except Exception as e:
                self.log_message(f"Broadcast reply error to {uid}: {e}")
            time.sleep(0.1)
        self._send_message(base_url, master_chat_id, f"✅ Broadcast reply sent to {count} users.")

if __name__ == "__main__":
    root = Tk()
    app = RadXrReceiverApp(root)
    root.mainloop()
