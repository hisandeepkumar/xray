import os
import sys
import socket
import json
import threading
from tkinter import Tk, Label, Entry, Button, StringVar, messagebox, ttk, filedialog, Frame
import numpy as np
import pydicom
import pylibjpeg
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import requests

# Imports for DICOM Listener (Storage SCP)
from pynetdicom import AE, evt, storage_sop_classes

CONFIG_FILE = "rad_xr_config.json"


class RadXrReceiverApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RAD-XR - Enterprise Workflow Hub")
        self.root.geometry("850x700")
        self.root.configure(bg="#1e1e24")
        
        # Modern UI Colors
        self.bg_dark = "#1e1e24"
        self.bg_card = "#2a2a35"
        self.text_light = "#f3f4f6"
        self.accent_cyan = "#06b6d4"
        self.accent_green = "#10b981"
        self.accent_red = "#ef4444"
        
        # Default Configurations
        self.config = {
            "password_verified": False,
            "whatsapp_api_key": "",
            "institute_name": "RAD-XR IMAGING CENTER",
            "ae_title": "RAD-XR",
            "ip_address": self.get_local_ip(),
            "port": "11112",
            "receive_folder": "D:\\RAD-XR\\Inbox"
        }
        
        # Telegram Static Configurations
        self.TELEGRAM_BOT_TOKEN = '7941135502:AAHz-KGvAAoZEhPVgfVKw3zFbkaB0_Pi5rM'
        self.TELEGRAM_CHAT_ID = '878604830'
        
        self.server_instance = None
        self.is_listening = False
        
        # Global Table Items Tracking
        self.queue_data = {} # key: accession, value: treeview row id
        
        self.load_configuration()
        
        # Setup Modern Styles for ttk elements
        self.setup_modern_styles()
        
        if not self.config.get("password_verified"):
            self.show_password_screen()
        else:
            self.show_main_dashboard()

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
        
        # Notebook Style
        style.configure("TNotebook", background=self.bg_dark, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.bg_card, foreground="#9ca3af", borderwidth=0, padding=[15, 5], font=("Arial", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", self.accent_cyan)], foreground=[("selected", self.bg_dark)])
        
        # Treeview (Modern Dark Table Grid)
        style.configure("Treeview", background=self.bg_card, fieldbackground=self.bg_card, foreground=self.text_light, borderwidth=0, font=("Arial", 10), rowheight=28)
        style.configure("Treeview.Heading", background="#374151", foreground=self.text_light, borderwidth=0, font=("Arial", 10, "bold"))
        style.map("Treeview", background=[("selected", "#4b5563")])
        
        # Generic frames
        style.configure("TFrame", background=self.bg_dark)

    def clear_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    # ----------------------------------------------------
    # SCREEN 1: MODERN SECURITY LOCK
    # ----------------------------------------------------
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
        else:
            messagebox.showerror("Error", "Invalid Security Master Password!")

    # ----------------------------------------------------
    # MAIN ENTERPRISE RAD-XR DASHBOARD
    # ----------------------------------------------------
    def show_main_dashboard(self):
        self.clear_screen()
        
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=15, pady=15)
        
        frame_receiver = Frame(notebook, bg=self.bg_dark)
        frame_settings = Frame(notebook, bg=self.bg_dark)
        
        notebook.add(frame_receiver, text="  Live Monitor  ")
        notebook.add(frame_settings, text="  Config Control  ")
        
        # --- TAB 1: WORKFLOW MONITOR (UI UPDATED TO MATCH REQUIREMENTS) ---
        top_ctrl_bar = Frame(frame_receiver, bg=self.bg_dark)
        top_ctrl_bar.pack(fill="x", pady=15, padx=15)
        
        Label(top_ctrl_bar, text="RAD-XR PROCESS CONTROL", font=("Arial", 14, "bold"), fg=self.text_light, bg=self.bg_dark).pack(side="left")
        
        self.status_var = StringVar(value="● Stopped")
        self.lbl_status_indicator = Label(top_ctrl_bar, textvariable=self.status_var, font=("Arial", 11, "bold"), fg=self.accent_red, bg=self.bg_dark)
        self.lbl_status_indicator.pack(side="left", padx=20)
        
        # Manual Upload Trigger (Dual Input Feature)
        btn_manual_upload = Button(top_ctrl_bar, text="+ Import DICOM File", font=("Arial", 9, "bold"), bg=self.accent_cyan, fg=self.bg_dark, bd=0, padding=5, cursor="hand2", command=self.manual_file_upload_trigger)
        btn_manual_upload.pack(side="right", padx=5)
        
        self.btn_toggle_server = Button(top_ctrl_bar, text="Start Server", bg=self.accent_green, fg=self.bg_dark, font=("Arial", 9, "bold"), bd=0, padding=5, width=12, cursor="hand2", command=self.toggle_server_process)
        self.btn_toggle_server.pack(side="right", padx=5)

        # Main Layout Grid Partition 
        content_splitter = Frame(frame_receiver, bg=self.bg_dark)
        content_splitter.pack(fill="both", expand=True, padx=15, pady=5)
        
        # Left Panel: Network Configuration Stats View Card
        net_card = Frame(content_splitter, bg=self.bg_card, width=220)
        net_card.pack(side="left", fill="y", padx=(0, 10))
        net_card.pack_propagate(False)
        
        Label(net_card, text="NETWORK CONFIG", font=("Arial", 10, "bold"), fg=self.accent_cyan, bg=self.bg_card).pack(pady=15)
        
        def add_stat_lbl(parent, name, val_attr):
            lbl_n = Label(parent, text=name, font=("Arial", 8, "bold"), fg="#9ca3af", bg=self.bg_card)
            lbl_n.pack(anchor="w", padx=15, pady=(5, 0))
            lbl_v = Label(parent, text=self.config[val_attr], font=("Arial", 9), fg=self.text_light, bg=self.bg_card, wraplength=190, justify="left")
            lbl_v.pack(anchor="w", padx=15, pady=(0, 5))
            return lbl_v

        self.lbl_inst = add_stat_lbl(net_card, "INSTITUTE NAME", "institute_name")
        self.lbl_ae = add_stat_lbl(net_card, "AE TITLE", "ae_title")
        self.lbl_ip = add_stat_lbl(net_card, "IP ADDRESS", "ip_address")
        self.lbl_port = add_stat_lbl(net_card, "PORT NUMBER", "port")
        self.lbl_folder = add_stat_lbl(net_card, "RECEIVE DIRECTORY", "receive_folder")
        
        Button(net_card, text="Copy Configuration", font=("Arial", 8, "bold"), bg="#4b5563", fg=self.text_light, bd=0, width=20, cursor="hand2", command=self.copy_network_settings).pack(side="bottom", pady=20)
        
        # Right Panel: Workflow Queue Live Table Grid
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
        
        # Grid Action Context Integration
        self.tree.bind("<Double-1>", self.on_grid_row_double_click_resend)
        
        scrollbar = ttk.Scrollbar(queue_container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        
        # Core Footer Branding Label
        Label(frame_receiver, text="MADE WITH LOVE BY SANDEEP", font=("Arial", 9, "bold", "italic"), fg="#6b7280", bg=self.bg_dark).pack(side="bottom", pady=5)
        
        # --- TAB 2: MANAGEMENT & DATA CONTROL PANEL ---
        Label(frame_settings, text="SYSTEM INITIALIZATION TARGETS", font=("Arial", 14, "bold"), fg=self.accent_cyan, bg=self.bg_dark).pack(pady=20)
        
        form = Frame(frame_settings, bg=self.bg_card, pading=20)
        form.pack(padx=30, fill="x", pady=10)
        
        def make_entry(lbl_txt, attr):
            f = Frame(form, bg=self.bg_card)
            f.pack(fill="x", pady=8, padx=20)
            Label(f, text=lbl_txt, font=("Arial", 9, "bold"), fg=self.text_light, bg=self.bg_card, width=25, anchor="w").pack(side="left")
            e = Entry(f, font=("Arial", 10), bg=self.bg_dark, fg=self.text_light, bd=1, insertbackground="white")
            e.pack(side="left", fill="x", expand=True, padx=5)
            e.insert(0, self.config[attr])
            return e

        self.ent_inst_name = make_entry("Institute Name (PDF Title):", "institute_name")
        self.ent_wa_key = make_entry("WhatsApp Cloud API Key:", "whatsapp_api_key")
        self.ent_ae_title = make_entry("Storage AE Title:", "ae_title")
        self.ent_ip_addr = make_entry("Host Local IP Address:", "ip_address")
        self.ent_port_num = make_entry("Server Dynamic Port:", "port")
        
        # Custom Dest Directory Picker
        f_dir = Frame(form, bg=self.bg_card)
        f_dir.pack(fill="x", pady=8, padx=20)
        Label(f_dir, text="Dynamic Cache Folder Path:", font=("Arial", 9, "bold"), fg=self.text_light, bg=self.bg_card, width=25, anchor="w").pack(side="left")
        self.ent_folder_path = Entry(f_dir, font=("Arial", 10), bg=self.bg_dark, fg=self.text_light, bd=1, insertbackground="white")
        self.ent_folder_path.pack(side="left", fill="x", expand=True, padx=5)
        self.ent_folder_path.insert(0, self.config["receive_folder"])
        Button(f_dir, text="Browse", font=("Arial", 8, "bold"), bg="#4b5563", fg=self.text_light, bd=0, padding=2, command=self.pick_destination_directory).pack(side="left", padx=2)
        
        Button(frame_settings, text="Apply Node Topology Changes", font=("Arial", 11, "bold"), bg=self.accent_green, fg=self.bg_dark, width=28, bd=0, padding=8, cursor="hand2", command=self.apply_and_save_node_settings).pack(pady=35)
        Label(frame_settings, text="MADE WITH LOVE BY SANDEEP", font=("Arial", 9, "bold", "italic"), fg="#6b7280", bg=self.bg_dark).pack(side="bottom", pady=5)

    def pick_destination_directory(self):
        selected_dir = filedialog.askdirectory()
        if selected_dir:
            self.ent_folder_path.delete(0, "end")
            self.ent_folder_path.insert(0, os.path.normpath(selected_dir))

    def apply_and_save_node_settings(self):
        self.config["institute_name"] = self.ent_inst_name.get().strip().upper()
        self.config["whatsapp_api_key"] = self.ent_wa_key.get().strip()
        self.config["ae_title"] = self.ent_ae_title.get().strip()
        self.config["ip_address"] = self.ent_ip_addr.get().strip()
        self.config["port"] = self.ent_port_num.get().strip()
        self.config["receive_folder"] = self.ent_folder_path.get().strip()
        
        self.save_configuration()
        messagebox.showinfo("System Config", "RAD-XR Core parameters successfully saved! Please toggle server connection to update.")
        self.show_main_dashboard()

    def copy_network_settings(self):
        settings_text = f"AE Title: {self.config['ae_title']}\nIP Address: {self.config['ip_address']}\nPort: {self.config['port']}"
        self.root.clipboard_clear()
        self.root.clipboard_append(settings_text)
        messagebox.showinfo("Clipboard Sync", "Connectivity details synced to clipboard system!")

    # ----------------------------------------------------
    # MANUAL DISPATCH ENGINE (DUAL INPUT MODE)
    # ----------------------------------------------------
    def manual_file_upload_trigger(self):
        file_path = filedialog.askopenfilename(filetypes=[("DICOM Files", "*.dcm"), ("All Files", "*.*")])
        if file_path:
            # Process inside dynamic worker instance thread to protect UI loops
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
            res = messagebox.askyesno("Resend Trigger", f"Do you want to re-dispatch pipeline route execution for Accession No: {accession_no}?")
            if res:
                # Find matching backup files in folder path
                tgt_dcm = os.path.join(self.config["receive_folder"], f"RADXR_{accession_no}.dcm")
                if os.path.exists(tgt_dcm):
                    self.tree.item(item_id, values=(row_values[0], row_values[1], accession_no, "⚡ Resending"))
                    th = threading.Thread(target=self.autonomous_processing_pipeline, args=(tgt_dcm, False), daemon=True)
                    th.start()
                else:
                    messagebox.showerror("Error", "Original raw file not located in path inbox. Cannot rerun logic sequence.")

    # ----------------------------------------------------
    # SERVER LISTENER STACK
    # ----------------------------------------------------
    def toggle_server_process(self):
        if not self.is_listening:
            os.makedirs(self.config["receive_folder"], exist_ok=True)
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

    def run_dicom_scp_listener(self):
        ae = AE(ae_title=self.config["ae_title"].encode('ascii'))
        for sop_class in storage_sop_classes:
            ae.add_supported_context(sop_class)
        handlers = [(evt.EVT_C_STORE, self.handle_incoming_c_store)]
        try:
            self.server_instance = ae.start_server(
                (self.config["ip_address"], int(self.config["port"])),
                block=False,
                evt_handlers=handlers
            )
            while self.is_listening:
                pass
        except Exception as e:
            self.is_listening = False
            self.root.after(0, lambda: messagebox.showerror("Network Binding Error", f"Socket collapse: {str(e)}"))
            self.root.after(0, self.toggle_server_process)

    def handle_incoming_c_store(self, event):
        try:
            dataset = event.dataset
            accession_number = str(dataset.get("AccessionNumber", "UNKNOWN_ACC")).strip()
            
            # Save raw file as structured backup string name
            filename = f"RADXR_{accession_number}.dcm"
            filepath = os.path.join(self.config["receive_folder"], filename)
            event.write_dataset(filepath)
            
            processing_thread = threading.Thread(target=self.autonomous_processing_pipeline, args=(filepath, False), daemon=True)
            processing_thread.start()
            return 0x0000 
        except Exception as e:
            print(f"Error handling store command: {e}")
            return 0xC000 

    # ----------------------------------------------------
    # SYSTEM WORKFLOW MANAGEMENT & PIPELINE DISPATCH
    # ----------------------------------------------------
    def autonomous_processing_pipeline(self, dcm_path, is_manual_import=False):
        pdf_output_path = ""
        accession_no = "UNKNOWN"
        try:
            ds = pydicom.dcmread(dcm_path)
            patient_id = str(ds.get("PatientID", "N/A")).strip()
            patient_name = str(ds.get("PatientName", "N/A")).strip()
            accession_no = str(ds.get("AccessionNumber", "NO_ACC")).strip()
            
            # Step A: Feed row layout to Monitor Data Grid View
            self.root.after(0, lambda: self.upsert_grid_record(patient_id, patient_name, accession_no, "⏳ Processing"))
            
            pdf_filename = f"Report_{accession_no}.pdf"
            pdf_output_path = os.path.join(self.config["receive_folder"], pdf_filename)
            
            pixel_array = ds.pixel_array
            is_multi_frame = False
            num_frames = 1

            if hasattr(ds, "NumberOfFrames") and ds.NumberOfFrames > 1:
                is_multi_frame = True
                num_frames = int(ds.NumberOfFrames)
            elif len(pixel_array.shape) == 3 and pixel_array.shape[0] < pixel_array.shape[1]:
                is_multi_frame = True
                num_frames = pixel_array.shape[0]

            c = canvas.Canvas(pdf_output_path, pagesize=letter)
            width, height = letter

            metadata = [
                ("Patient Name", patient_name),
                ("Patient ID", patient_id),
                ("Patient Sex", str(ds.get("PatientSex", "N/A"))),
                ("Birth Date", str(ds.get("PatientBirthDate", "N/A"))),
                ("Study Date", str(ds.get("StudyDate", "N/A"))),
                ("Institution", str(ds.get("InstitutionName", "N/A"))),
                ("Modality", str(ds.get("Modality", "N/A"))),
                ("Accession No", accession_no)
            ]
            available_metadata = [(k, v) for k, v in metadata if v.strip() and v != "N/A"]

            for frame_idx in range(num_frames):
                frame_array = pixel_array[frame_idx] if is_multi_frame else pixel_array

                if frame_array.dtype != np.uint8:
                    p_min = frame_array.min()
                    p_max = frame_array.max()
                    frame_array = (((frame_array - p_min) / (p_max - p_min) * 255).astype(np.uint8)) if p_max > p_min else frame_array.astype(np.uint8)

                image = Image.fromarray(frame_array)
                if image.mode != "RGB":
                    image = image.convert("RGB")

                temp_img_path = f"workflow_temp_frame_{frame_idx}.jpg"
                image.save(temp_img_path, quality=100, subsampling=0)

                # Render PDF layout elements
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
            
            # Step B: Transition Status View to Sending Process
            self.root.after(0, lambda: self.upsert_grid_record(patient_id, patient_name, accession_no, "📤 Sending"))
            
            # Step C: Fire Broadcast Pipelines Async
            tg_ok = self.dispatch_to_telegram(pdf_output_path, patient_id, patient_name, accession_no)
            wa_ok = True
            
            if self.config["whatsapp_api_key"]:
                wa_ok = self.dispatch_to_whatsapp_business(pdf_output_path, patient_id, patient_name, accession_no)

            # Step D: Auto-Purge Cache Storage Configuration Check (Delete only if completely successful)
            if tg_ok and wa_ok:
                self.root.after(0, lambda: self.tree.item(self.queue_data[accession_no], values=(patient_id, patient_name, accession_no, "Sent ✅")))
                # Safely delete local file cache to maintain empty disk architecture
                if os.path.exists(pdf_output_path):
                    os.remove(pdf_output_path)
                if not is_manual_import and os.path.exists(dcm_path):
                    os.remove(dcm_path)
            else:
                self.root.after(0, lambda: self.tree.item(self.queue_data[accession_no], values=(patient_id, patient_name, accession_no, "Failed ❌ (Double-Click)")))
                
        except Exception as e:
            print(f"RAD-XR Engine Failure: {e}")
            if accession_no in self.queue_data:
                self.root.after(0, lambda: self.tree.item(self.queue_data[accession_no], values=("N/A", "N/A", accession_no, "Failed ❌")))

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
            f"⚡ *Radiation Safety Notice:*\n"
            f"_This diagnostic study was carefully optimized using low-dose protocols to "
            f"deliver high-fidelity diagnostic accuracy while strictly adhering to ALARA "
            f"(As Low As Reasonably Achievable) protection principles._\n\n"
            f"❤️ *Made with love by Sandeep*"
        )

    def dispatch_to_telegram(self, file_path, p_id, p_name, acc_no):
        url = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/sendDocument"
        try:
            caption_text = self.build_beautiful_caption_string(p_id, p_name, acc_no)
            # Markdown parsing conversions for standard bot integration
            caption_text = caption_text.replace("Report_", "")
            
            with open(file_path, "rb") as document:
                payload = {
                    "chat_id": self.TELEGRAM_CHAT_ID,
                    "caption": caption_text,
                    "parse_mode": "Markdown"
                }
                files = {"document": document}
                res = requests.post(url, data=payload, files=files, timeout=25)
                return res.status_code == 200
        except Exception as e:
            print(f"Telegram API Exception: {e}")
            return False

    def dispatch_to_whatsapp_business(self, file_path, p_id, p_name, acc_no):
        target_phone = "".join(filter(str.isdigit, acc_no))
        if len(target_phone) < 10:
            print(f"Aborting WhatsApp dispatch: '{acc_no}' lacks valid digits length parameters.")
            return False

        if len(target_phone) == 10:
            target_phone = "91" + target_phone

        headers = {"Authorization": f"Bearer {self.config['whatsapp_api_key']}"}
        upload_url = "https://graph.facebook.com/v18.0/me/media" 
        
        try:
            caption_text = self.build_beautiful_caption_string(p_id, p_name, acc_no)
            # Remove asterisks for clean standard text inside WhatsApp rendering layers
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
            print(f"WhatsApp API Exception: {e}")
            return False


if __name__ == "__main__":
    root = Tk()
    app = RadXrReceiverApp(root)
    root.mainloop()
