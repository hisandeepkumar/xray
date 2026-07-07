import os
import sys
import socket
import json
import threading
from tkinter import Tk, Label, Entry, Button, StringVar, messagebox, ttk, filedialog
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
        self.root.title("RAD-XR - DICOM to PDF & Smart Dispatcher")
        self.root.geometry("600x650")
        self.root.resizable(False, False)
        
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
        
        self.load_configuration()
        
        # Route Flow based on verification status
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

    # ----------------------------------------------------
    # SCREEN 1: ONE-TIME SECURITY LOCK
    # ----------------------------------------------------
    def show_password_screen(self):
        self.clear_screen()
        
        lbl_title = Label(self.root, text="RAD-XR Activation Lock", font=("Arial", 16, "bold"), fg="#007bff")
        lbl_title.pack(pady=40)
        
        lbl_info = Label(self.root, text="Enter the master password to activate RAD-XR on this PC:", font=("Arial", 10))
        lbl_info.pack(pady=10)
        
        self.pass_var = StringVar()
        entry_pass = Entry(self.root, textvariable=self.pass_var, show="*", font=("Arial", 12), width=30, justify="center")
        entry_pass.pack(pady=10)
        entry_pass.focus()
        
        btn_verify = Button(self.root, text="Verify & Activate", font=("Arial", 11, "bold"), bg="#28a745", fg="white", width=18, command=self.verify_master_password)
        btn_verify.pack(pady=20)

    def verify_master_password(self):
        if self.pass_var.get() == "Sandeep@123":
            self.config["password_verified"] = True
            self.save_configuration()
            messagebox.showinfo("Success", "RAD-XR successfully activated on this PC Node!")
            self.show_main_dashboard()
        else:
            messagebox.showerror("Error", "Invalid Security Master Password!")

    def clear_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    # ----------------------------------------------------
    # MAIN RAD-XR DASHBOARD
    # ----------------------------------------------------
    def show_main_dashboard(self):
        self.clear_screen()
        
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        frame_receiver = ttk.Frame(notebook)
        frame_settings = ttk.Frame(notebook)
        
        notebook.add(frame_receiver, text="RAD-XR Receiver Server")
        notebook.add(frame_settings, text="Configuration Settings")
        
        # --- TAB 1: RAD-XR RECEIVER UI ---
        lbl_header = Label(frame_receiver, text="DICOM RECEIVER SETTINGS (RAD-XR)", font=("Arial", 14, "bold"), fg="#17a2b8")
        lbl_header.pack(pady=15)
        
        # Status Box Indicator
        self.status_var = StringVar(value="● Stopped")
        self.lbl_status_indicator = Label(frame_receiver, textvariable=self.status_var, font=("Arial", 12, "bold"), fg="red")
        self.lbl_status_indicator.pack(pady=5)
        
        # Display Specs Grid
        grid_frame = ttk.Frame(frame_receiver)
        grid_frame.pack(pady=15, padx=20, fill="x")
        
        Label(grid_frame, text="Institute Name:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        self.lbl_inst = Label(grid_frame, text=self.config["institute_name"], font=("Arial", 10))
        self.lbl_inst.grid(row=0, column=1, sticky="w", pady=5, padx=10)
        
        Label(grid_frame, text="AE Title:", font=("Arial", 10, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        self.lbl_ae = Label(grid_frame, text=self.config["ae_title"], font=("Arial", 10))
        self.lbl_ae.grid(row=1, column=1, sticky="w", pady=5, padx=10)
        
        Label(grid_frame, text="IP Address:", font=("Arial", 10, "bold")).grid(row=2, column=0, sticky="w", pady=5)
        self.lbl_ip = Label(grid_frame, text=self.config["ip_address"], font=("Arial", 10))
        self.lbl_ip.grid(row=2, column=1, sticky="w", pady=5, padx=10)
        
        Label(grid_frame, text="Port Number:", font=("Arial", 10, "bold")).grid(row=3, column=0, sticky="w", pady=5)
        self.lbl_port = Label(grid_frame, text=self.config["port"], font=("Arial", 10))
        self.lbl_port.grid(row=3, column=1, sticky="w", pady=5, padx=10)
        
        Label(grid_frame, text="Receive Folder:", font=("Arial", 10, "bold")).grid(row=4, column=0, sticky="w", pady=5)
        self.lbl_folder = Label(grid_frame, text=self.config["receive_folder"], font=("Arial", 9), wraplength=350, justify="left")
        self.lbl_folder.grid(row=4, column=1, sticky="w", pady=5, padx=10)
        
        # Control Buttons
        btn_frame = ttk.Frame(frame_receiver)
        btn_frame.pack(pady=20)
        
        self.btn_toggle_server = Button(btn_frame, text="Start Server", bg="#28a745", fg="white", font=("Arial", 10, "bold"), width=15, command=self.toggle_server_process)
        self.btn_toggle_server.grid(row=0, column=0, padx=10)
        
        btn_copy = Button(btn_frame, text="Copy Settings", bg="#6c757d", fg="white", font=("Arial", 10), width=15, command=self.copy_network_settings)
        btn_copy.grid(row=0, column=1, padx=10)
        
        # --- TAB 2: CONFIGURATION UI ---
        lbl_settings_title = Label(frame_settings, text="RAD-XR SYSTEM CONFIGURATION", font=("Arial", 12, "bold"))
        lbl_settings_title.pack(pady=15)
        
        config_form = ttk.Frame(frame_settings)
        config_form.pack(padx=20, fill="x", pady=10)
        
        Label(config_form, text="Institute Name (PDF Header Title):", font=("Arial", 9, "bold")).pack(anchor="w", pady=2)
        self.ent_inst_name = Entry(config_form, font=("Arial", 10))
        self.ent_inst_name.pack(fill="x", pady=5)
        self.ent_inst_name.insert(0, self.config["institute_name"])
        
        Label(config_form, text="WhatsApp Business API Key:", font=("Arial", 9, "bold")).pack(anchor="w", pady=2)
        self.ent_wa_key = Entry(config_form, font=("Arial", 10), show="*")
        self.ent_wa_key.pack(fill="x", pady=5)
        self.ent_wa_key.insert(0, self.config["whatsapp_api_key"])
        
        Label(config_form, text="Storage AE Title:", font=("Arial", 9, "bold")).pack(anchor="w", pady=2)
        self.ent_ae_title = Entry(config_form, font=("Arial", 10))
        self.ent_ae_title.pack(fill="x", pady=5)
        self.ent_ae_title.insert(0, self.config["ae_title"])
        
        Label(config_form, text="Local IP Address:", font=("Arial", 9, "bold")).pack(anchor="w", pady=2)
        self.ent_ip_addr = Entry(config_form, font=("Arial", 10))
        self.ent_ip_addr.pack(fill="x", pady=5)
        self.ent_ip_addr.insert(0, self.config["ip_address"])
        
        Label(config_form, text="Listener Port Number:", font=("Arial", 9, "bold")).pack(anchor="w", pady=2)
        self.ent_port_num = Entry(config_form, font=("Arial", 10))
        self.ent_port_num.pack(fill="x", pady=5)
        self.ent_port_num.insert(0, self.config["port"])
        
        # Target Path Picker
        Label(config_form, text="Receive Folder Directory:", font=("Arial", 9, "bold")).pack(anchor="w", pady=2)
        path_frame = ttk.Frame(config_form)
        path_frame.pack(fill="x", pady=2)
        self.ent_folder_path = Entry(path_frame, font=("Arial", 10), width=45)
        self.ent_folder_path.pack(side="left", fill="x", expand=True)
        self.ent_folder_path.insert(0, self.config["receive_folder"])
        Button(path_frame, text="...", command=self.pick_destination_directory).pack(side="right", padx=5)
        
        btn_save_settings = Button(frame_settings, text="Save RAD-XR Settings", font=("Arial", 11, "bold"), bg="#007bff", fg="white", command=self.apply_and_save_node_settings)
        btn_save_settings.pack(pady=20)

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
        messagebox.showinfo("Configuration", "RAD-XR node settings updated! Restart server to apply changes.")
        self.show_main_dashboard()

    def copy_network_settings(self):
        settings_text = f"AE Title: {self.config['ae_title']}\nIP Address: {self.config['ip_address']}\nPort: {self.config['port']}"
        self.root.clipboard_clear()
        self.root.clipboard_append(settings_text)
        messagebox.showinfo("Clipboard", "Connectivity details copied!")

    # ----------------------------------------------------
    # DICOM CORE SCP LISTENER & BROADCAST ENGINE
    # ----------------------------------------------------
    def toggle_server_process(self):
        if not self.is_listening:
            os.makedirs(self.config["receive_folder"], exist_ok=True)
            self.is_listening = True
            self.status_var.set("● Listening")
            self.lbl_status_indicator.config(fg="green")
            self.btn_toggle_server.config(text="Stop Server", bg="#dc3545")
            
            self.server_thread = threading.Thread(target=self.run_dicom_scp_listener, daemon=True)
            self.server_thread.start()
        else:
            self.is_listening = False
            if self.server_instance:
                self.server_instance.shutdown()
            self.status_var.set("● Stopped")
            self.lbl_status_indicator.config(fg="red")
            self.btn_toggle_server.config(text="Start Server", bg="#28a745")

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
            self.root.after(0, lambda: messagebox.showerror("Network Binding Error", f"Could not bind socket: {str(e)}"))
            self.root.after(0, self.toggle_server_process)

    def handle_incoming_c_store(self, event):
        try:
            dataset = event.dataset
            accession_number = str(dataset.get("AccessionNumber", "UNKNOWN_ACC")).strip()
            patient_id = str(dataset.get("PatientID", "N/A")).strip()
            
            filename = f"RADXR_{accession_number}_{patient_id}.dcm"
            filepath = os.path.join(self.config["receive_folder"], filename)
            
            event.write_dataset(filepath)
            
            processing_thread = threading.Thread(target=self.autonomous_processing_pipeline, args=(filepath,), daemon=True)
            processing_thread.start()
            
            return 0x0000 
        except Exception as e:
            print(f"Error handling store command: {e}")
            return 0xC000 

    # ----------------------------------------------------
    # RAD-XR AUTOMATED SYSTEM PIPELINE
    # ----------------------------------------------------
    def autonomous_processing_pipeline(self, dcm_path):
        try:
            ds = pydicom.dcmread(dcm_path)
            accession_no = str(ds.get("AccessionNumber", "NO_ACC")).strip()
            
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
                ("Patient Name", str(ds.get("PatientName", "N/A"))),
                ("Patient ID", str(ds.get("PatientID", "N/A"))),
                ("Patient Sex", str(ds.get("PatientSex", "N/A"))),
                ("Birth Date", str(ds.get("PatientBirthDate", "N/A"))),
                ("Study Date", str(ds.get("StudyDate", "N/A"))),
                ("Institution", str(ds.get("InstitutionName", "N/A"))),
                ("Modality", str(ds.get("Modality", "N/A"))),
                ("Manufacturer", str(ds.get("Manufacturer", "N/A"))),
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

                temp_img_path = f"radxr_temp_frame_{frame_idx}.jpg"
                image.save(temp_img_path, quality=100, subsampling=0)

                # Upper Header Dynamic Title (Institute Name)
                c.setFont("Helvetica-Bold", 14)
                c.drawString(40, height - 40, self.config["institute_name"])
                
                c.setFont("Helvetica-Oblique", 9)
                c.drawRightString(width - 40, height - 40, f"Page {frame_idx + 1} of {num_frames}")
                
                c.setLineWidth(1)
                c.setStrokeColorRGB(0.1, 0.5, 0.7) 
                c.line(40, height - 46, width - 40, height - 46)

                # Metadata layout mapping
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

                # Auto Fit Image logic 
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
            
            # --- AUTOMATED DISPATCH SYSTEM ---
            # 1. Send via Telegram Bot 
            self.dispatch_to_telegram(pdf_output_path, accession_no)
            
            # 2. Send via WhatsApp Business API (Uses Accession No as Phone Number)
            if self.config["whatsapp_api_key"]:
                self.dispatch_to_whatsapp_business(pdf_output_path, accession_no)
                
        except Exception as e:
            print(f"RAD-XR Pipeline error: {e}")

    def dispatch_to_telegram(self, file_path, accession_no):
        url = f"https://api.telegram.org/bot{self.TELEGRAM_BOT_TOKEN}/sendDocument"
        try:
            with open(file_path, "rb") as document:
                payload = {
                    "chat_id": self.TELEGRAM_CHAT_ID,
                    "caption": f"✅ RAD-XR: New DICOM Report Generated\n🔹 Accession No: {accession_no}"
                }
                files = {"document": document}
                requests.post(url, data=payload, files=files, timeout=20)
        except Exception as e:
            print(f"Failed to send via Telegram: {e}")

    def dispatch_to_whatsapp_business(self, file_path, phone_number):
        target_phone = "".join(filter(str.isdigit, phone_number))
        if len(target_phone) < 10:
            print(f"WhatsApp Dispatch Cancelled: Accession '{phone_number}' is not a valid number.")
            return

        if len(target_phone) == 10:
            target_phone = "91" + target_phone

        headers = {
            "Authorization": f"Bearer {self.config['whatsapp_api_key']}",
        }
        
        upload_url = "https://graph.facebook.com/v18.0/me/media" 
        try:
            with open(file_path, "rb") as f:
                files = {
                    "file": (os.path.basename(file_path), f, "application/pdf"),
                    "messaging_product": (None, "whatsapp")
                }
                res = requests.post(upload_url, headers=headers, files=files, timeout=20)
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
                            "caption": f"Your medical report from {self.config['institute_name']}"
                        }
                    }
                    requests.post(msg_url, headers=headers, json=payload, timeout=20)
        except Exception as e:
            print(f"Failed to send via WhatsApp: {e}")


if __name__ == "__main__":
    root = Tk()
    app = RadXrReceiverApp(root)
    root.mainloop()
