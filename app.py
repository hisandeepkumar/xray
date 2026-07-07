import os
import sys
from tkinter import Tk, filedialog, messagebox, ttk

# Force Import for PyInstaller to bundle libraries properly
import numpy as np
import pydicom
# Yeh import compression plugins ko trigger karne ke liye zaroori hai
import pylibjpeg 
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


class DicomToPdfApp:

    def __init__(self, root):
        self.root = root
        self.root.title("DICOM to PDF Converter")
        self.root.geometry("500x300")
        self.root.resizable(False, False)

        # UI Styling
        self.style = ttk.Style()
        self.style.theme_use("clam")

        self.dicom_path = ""

        # UI Elements
        self.create_widgets()

    def create_widgets(self):
        # Title Label
        title_label = ttk.Label(
            self.root, text="DICOM to PDF Converter", font=("Arial", 16, "bold")
        )
        title_label.pack(pady=20)

        # File Selection Frame
        frame = ttk.Frame(self.root)
        frame.pack(pady=10, padx=20, fill="x")

        self.file_label = ttk.Label(
            frame, text="Koi DICOM file chuni nahi gayi hai", wraplength=350
        )
        self.file_label.pack(side="left", padx=5)

        browse_btn = ttk.Button(
            frame, text="File Chunen (Browse)", command=self.browse_file
        )
        browse_btn.pack(side="right", padx=5)

        # Convert Button
        self.convert_btn = ttk.Button(
            self.root,
            text="PDF mein Convert Karen",
            command=self.convert_dicom_to_pdf,
            state="disabled",
        )
        self.convert_btn.pack(pady=30, ipadx=10, ipady=5)

        # Footer / Status
        self.status_label = ttk.Label(
            self.root, text="Ready", font=("Arial", 9, "italic"), foreground="gray"
        )
        self.status_label.pack(side="bottom", pady=10)

    def browse_file(self):
        file_path = filedialog.askopenfilename(
            filetypes=[("DICOM Files", "*.dcm"), ("All Files", "*.*")]
        )
        if file_path:
            self.dicom_path = file_path
            self.file_label.config(text=os.path.basename(file_path))
            self.convert_btn.config(state="normal")
            self.status_label.config(
                text="File load ho gayi hai. Convert button par click karen."
            )

    def convert_dicom_to_pdf(self):
        if not self.dicom_path:
            return

        # Save PDF Location Dialog
        output_pdf_path = filedialog.asksaveasfilename(
            defaultextension=".pdf", filetypes=[("PDF Files", "*.pdf")]
        )
        if not output_pdf_path:
            return

        try:
            self.status_label.config(text="Convert ho raha hai... Kripya ruken.")
            self.root.update()

            # 1. Read DICOM file
            ds = pydicom.dcmread(self.dicom_path)

            # 2. Extract Pixel Data Safely
            # Koi bhi compressed format (JPEG Lossless etc.) ho, ye automatically decode karega
            pixel_array = ds.pixel_array

            # 3. Medical Image Scaling (12/16-bit to 8-bit conversion)
            # Iske bina image blank ya black aati hai
            if pixel_array.dtype != np.uint8:
                p_min = pixel_array.min()
                p_max = pixel_array.max()
                if p_max > p_min:
                    pixel_array = ((pixel_array - p_min) / (p_max - p_min) * 255).astype(np.uint8)
                else:
                    pixel_array = pixel_array.astype(np.uint8)

            # 4. Create PIL Image
            image = Image.fromarray(pixel_array)
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Temporary image path to dump raw image
            temp_img_path = "temp_dicom_processed.jpg"
            image.save(temp_img_path, quality=95)

            # 5. Create PDF using ReportLab
            c = canvas.Canvas(output_pdf_path, pagesize=letter)
            width, height = letter

            # Patient Metadata info top par draw karein
            c.setFont("Helvetica-Bold", 12)
            patient_name = str(ds.get("PatientName", "Unknown Patient"))
            c.drawString(50, height - 50, f"Patient Name: {patient_name}")
            
            # Ek separator line draw karte hain metadata ke niche
            c.setLineWidth(1)
            c.setStrokeColorRGB(0.8, 0.8, 0.8)
            c.line(50, height - 65, width - 50, height - 65)

            # 6. Draw Image on PDF (Centered & Well Proportioned)
            # Image ko stretch hone se bachane ke liye width auto-scale hogi
            img_w, img_h = image.size
            display_width = width - 100 # Margins chhodkar
            display_height = (img_h / img_w) * display_width

            # Agar image height page se badi ho rahi hai toh use constrain karein
            if display_height > (height - 150):
                display_height = height - 150
                display_width = (img_w / img_h) * display_height

            # Centering calculation
            x_pos = (width - display_width) / 2
            y_pos = (height - display_height) / 2 - 20

            c.drawImage(temp_img_path, x_pos, y_pos, width=display_width, height=display_height)
            
            c.showPage()
            c.save()

            # Clean up temporary file
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

            self.status_label.config(text="Safaltapoorvak convert ho gaya!")
            messagebox.showinfo("Success", f"PDF safaltapoorvak yahan save ho gayi:\n{output_pdf_path}")

        except Exception as e:
            self.status_label.config(text="Error aaya hai.")
            messagebox.showerror("Error", f"File convert karne mein dikkat aayi:\n{str(e)}")


if __name__ == "__main__":
    root = Tk()
    app = DicomToPdfApp(root)
    root.mainloop()
