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
            self.status_label.config(text="Converting multi-frame DICOM... Please wait.")
            self.root.update()

            # 1. Read DICOM file
            ds = pydicom.dcmread(self.dicom_path)

            # 2. Extract Pixel Data
            pixel_array = ds.pixel_array

            # Check if file has multiple frames/images
            # pixel_array shape for multi-frame is usually (frames, rows, columns) or (frames, rows, columns, channels)
            is_multi_frame = False
            num_frames = 1

            if hasattr(ds, "NumberOfFrames") and ds.NumberOfFrames > 1:
                is_multi_frame = True
                num_frames = int(ds.NumberOfFrames)
            elif len(pixel_array.shape) == 3 and pixel_array.shape[0] < pixel_array.shape[1]:
                # Fallback check if NumberOfFrames tag is missing but array is 3D
                is_multi_frame = True
                num_frames = pixel_array.shape[0]

            # 3. Initialize PDF Canvas
            c = canvas.Canvas(output_pdf_path, pagesize=letter)
            width, height = letter

            # 4. Extract Metadata once (to reuse on every page)
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
            available_metadata = [(k, v) for k, v in metadata if v.strip() and v != "N/A"]

            # 5. Loop through each frame/image
            for frame_idx in range(num_frames):
                
                # Extract specific frame array
                if is_multi_frame:
                    frame_array = pixel_array[frame_idx]
                else:
                    frame_array = pixel_array

                # Medical Image Scaling (Keep original data resolution intact)
                if frame_array.dtype != np.uint8:
                    p_min = frame_array.min()
                    p_max = frame_array.max()
                    if p_max > p_min:
                        frame_array = ((frame_array - p_min) / (p_max - p_min) * 255).astype(np.uint8)
                    else:
                        frame_array = frame_array.astype(np.uint8)

                # Create PIL Image for current frame
                image = Image.fromarray(frame_array)
                if image.mode != "RGB":
                    image = image.convert("RGB")

                # Save temporary file for current frame
                temp_img_path = f"temp_frame_{frame_idx}.jpg"
                image.save(temp_img_path, quality=100, subsampling=0)

                # --- Draw Page Content ---
                # Top Header Header Title
                c.setFont("Helvetica-Bold", 14)
                c.drawString(40, height - 40, "DICOM MEDICAL REPORT")
                
                # Page Number / Frame info
                c.setFont("Helvetica-Oblique", 10)
                c.drawRightString(width - 40, height - 40, f"Page {frame_idx + 1} of {num_frames}")
                
                # Top Separator Line
                c.setLineWidth(1)
                c.setStrokeColorRGB(0.7, 0.7, 0.7)
                c.line(40, height - 48, width - 40, height - 48)

                # Draw Metadata Table (Repeated on every page)
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

                # Divider line before the image
                c.setLineWidth(0.5)
                c.line(40, y_text, width - 40, y_text)
                y_text -= 15

                # Draw Image (Max Wide Fit, No Aspect Ratio Distortion)
                img_w, img_h = image.size
                display_width = width - 80 
                display_height = (img_h / img_w) * display_width

                # Height restriction check
                max_available_height = y_text - 40
                if display_height > max_available_height:
                    display_height = max_available_height
                    display_width = (img_w / img_h) * display_height

                # Centering and drawing
                x_pos = (width - display_width) / 2
                y_pos = y_text - display_height

                c.drawImage(temp_img_path, x_pos, y_pos, width=display_width, height=display_height)
                
                # Clean up current temp file immediately
                if os.path.exists(temp_img_path):
                    os.remove(temp_img_path)

                # Agar abhi aur frames bache hain, to naya page add karein
                if frame_idx < num_frames - 1:
                    c.showPage()
            
            # Save the final compiled multi-page PDF
            c.showPage()
            c.save()

            self.status_label.config(text="Converted successfully!")
            messagebox.showinfo("Success", f"Multi-page PDF successfully saved at:\n{output_pdf_path}")

        except Exception as e:
            self.status_label.config(text="Error occurred.")
            messagebox.showerror("Error", f"Failed to convert file:\n{str(e)}")


if __name__ == "__main__":
    root = Tk()
    app = DicomToPdfApp(root)
    root.mainloop()
