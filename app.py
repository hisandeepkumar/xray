import os
import sys
from tkinter import Tk, filedialog, messagebox, ttk

# Force Import for PyInstaller
import numpy as np
import pydicom
import pylibjpeg 
from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


class DicomToPdfApp:

    def __init__(self, root):
        self.root = root
        self.root.title("DICOM to PDF Converter")
        self.root.geometry("550x320")
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
            frame, text="No DICOM file selected", wraplength=380, font=("Arial", 10)
        )
        self.file_label.pack(side="left", padx=5)

        browse_btn = ttk.Button(
            frame, text="Browse File", command=self.browse_file
        )
        browse_btn.pack(side="right", padx=5)

        # Convert Button
        self.convert_btn = ttk.Button(
            self.root,
            text="Convert to PDF",
            command=self.convert_dicom_to_pdf,
            state="disabled",
        )
        self.convert_btn.pack(pady=25, ipadx=15, ipady=5)

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
            self.status_label.config(text="File loaded successfully. Click 'Convert to PDF'.")

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
            self.status_label.config(text="Converting... Please wait.")
            self.root.update()

            # 1. Read DICOM file
            ds = pydicom.dcmread(self.dicom_path)

            # 2. Extract Pixel Data Safely
            pixel_array = ds.pixel_array

            # 3. Medical Image Scaling (Keep original data resolution intact)
            if pixel_array.dtype != np.uint8:
                p_min = pixel_array.min()
                p_max = pixel_array.max()
                if p_max > p_min:
                    pixel_array = ((pixel_array - p_min) / (p_max - p_min) * 255).astype(np.uint8)
                else:
                    pixel_array = pixel_array.astype(np.uint8)

            # 4. Create PIL Image (Maintains original pixel dimensions)
            image = Image.fromarray(pixel_array)
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Save temporary file with full quality
            temp_img_path = "temp_dicom_highres.jpg"
            image.save(temp_img_path, quality=100, subsampling=0)

            # 5. Initialize PDF Canvas
            c = canvas.Canvas(output_pdf_path, pagesize=letter)
            width, height = letter

            # 6. Extract Metadata dynamically
            metadata = [
                ("Patient Name", str(ds.get("PatientName", "N/A"))),
                ("Patient ID", str(ds.get("PatientID", "N/A"))),
                ("Patient Sex", str(ds.get("PatientSex", "N/A"))),
                ("Birth Date", str(ds.get("PatientBirthDate", "N/A"))),
                ("Study Date", str(ds.get("StudyDate", "N/A"))),
                ("Institution", str(ds.get("InstitutionName", "N/A"))),
                ("Modality", str(ds.get("Modality", "N/A"))),
                ("Manufacturer", str(ds.get("Manufacturer", "N/A")))
            ]

            # Filter out N/A entries to keep it clean
            available_metadata = [(k, v) for k, v in metadata if v.strip() and v != "N/A"]

            # 7. Draw Metadata Table on PDF
            c.setFont("Helvetica-Bold", 14)
            c.drawString(40, height - 40, "DICOM MEDICAL REPORT")
            
            c.setLineWidth(1)
            c.setStrokeColorRGB(0.7, 0.7, 0.7)
            c.line(40, height - 48, width - 40, height - 48)

            c.setFont("Helvetica", 10)
            y_text = height - 65
            
            # Print metadata in a 2-column layout to save vertical space
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
            
            if col == 1: # Adjust line if odd number of metadata items
                y_text -= 15

            # Another separator line before the image
            c.setLineWidth(0.5)
            c.line(40, y_text, width - 40, y_text)
            y_text -= 15

            # 8. Draw Image on PDF (Max Fit, No Aspect Ratio Distortion)
            img_w, img_h = image.size
            
            # Margin left/right 40pt -> Available width = page width - 80
            display_width = width - 80 
            display_height = (img_h / img_w) * display_width

            # If height overflows the remaining page area, scale down based on height
            max_available_height = y_text - 40
            if display_height > max_available_height:
                display_height = max_available_height
                display_width = (img_w / img_h) * display_height

            # Horizontal Centering calculation
            x_pos = (width - display_width) / 2
            # Vertical alignment inside the remaining space
            y_pos = y_text - display_height

            c.drawImage(temp_img_path, x_pos, y_pos, width=display_width, height=display_height)
            
            c.showPage()
            c.save()

            # Clean up temporary file
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

            self.status_label.config(text="Converted successfully!")
            messagebox.showinfo("Success", f"PDF successfully saved at:\n{output_pdf_path}")

        except Exception as e:
            self.status_label.config(text="Error occurred.")
            messagebox.showerror("Error", f"Failed to convert file:\n{str(e)}")


if __name__ == "__main__":
    root = Tk()
    app = DicomToPdfApp(root)
    root.mainloop()
