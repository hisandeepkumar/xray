import os
import sys
from tkinter import Tk, filedialog, messagebox, ttk

# PyInstaller को मजबूर करने के लिए Force Import
import numpy as np 
import pydicom
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
            frame, text="कोई DICOM फाइल चुनी नहीं गई है", wraplength=350
        )
        self.file_label.pack(side="left", padx=5)

        browse_btn = ttk.Button(
            frame, text="फाइल चुनें (Browse)", command=self.browse_file
        )
        browse_btn.pack(side="right", padx=5)

        # Convert Button
        self.convert_btn = ttk.Button(
            self.root,
            text="PDF में कन्वर्ट करें",
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
                text="फाइल लोड हो गई है। कन्वर्ट बटन पर क्लिक करें।"
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
            self.status_label.config(text="कन्वर्ट हो रहा है... कृपया रुकें।")
            self.root.update()

            # Read DICOM file
            ds = pydicom.dcmread(self.dicom_path)

            # Extract Pixel Data and convert to Image
            pixel_array = ds.pixel_array
            
            # NumPy array को सही फॉर्मेट में सुनिश्चित करना
            if pixel_array.dtype != np.uint8:
                # Image को 8-bit में स्केल करना ताकि PIL समझ सके
                pixel_array = ((pixel_array - pixel_array.min()) / (pixel_array.max() - pixel_array.min()) * 255).astype(np.uint8)
            
            image = Image.fromarray(pixel_array)

            # Handle grayscale conversion if needed
            if image.mode != "RGB":
                image = image.convert("RGB")

            # Temporary image path
            temp_img_path = "temp_dicom_img.jpg"
            image.save(temp_img_path)

            # Create PDF
            c = canvas.Canvas(output_pdf_path, pagesize=letter)
            width, height = letter

            # Draw image on PDF (Centered)
            c.drawImage(temp_img_path, 50, 150, width=width - 100, preserveAspectRatio=True, mask='auto')
            
            # Add some basic text metadata from DICOM (Optional)
            c.setFont("Helvetica", 10)
            patient_name = str(ds.get("PatientName", "Unknown"))
            c.drawString(50, height - 50, f"Patient Name: {patient_name}")
            
            c.showPage()
            c.save()

            # Clean up temp image
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)

            self.status_label.config(text="सफलतापूर्वक कन्वर्ट हो गया!")
            messagebox.showinfo("Success", f"PDF सफलतापूर्वक यहाँ सेव हो गई:\n{output_pdf_path}")

        except Exception as e:
            self.status_label.config(text="एरर आया है।")
            messagebox.showerror("Error", f"फाइल कन्वर्ट करने में दिक्कत आई:\n{str(e)}")


if __name__ == "__main__":
    root = Tk()
    app = DicomToPdfApp(root)
    root.mainloop()
