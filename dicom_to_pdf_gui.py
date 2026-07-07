import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import pydicom
from PIL import Image
import os
import sys
import img2pdf
import numpy as np
import tempfile

class DICOMtoPDF:
    def __init__(self, root):
        self.root = root
        self.root.title("DICOM to PDF Converter")
        self.root.geometry("500x200")
        self.root.resizable(False, False)

        self.input_file = tk.StringVar()
        self.output_file = tk.StringVar()

        tk.Label(root, text="Select DICOM file:").grid(row=0, column=0, padx=10, pady=10, sticky='w')
        tk.Entry(root, textvariable=self.input_file, width=40).grid(row=0, column=1, padx=5, pady=10)
        tk.Button(root, text="Browse", command=self.browse_input).grid(row=0, column=2, padx=5, pady=10)

        tk.Label(root, text="Output PDF file:").grid(row=1, column=0, padx=10, pady=10, sticky='w')
        tk.Entry(root, textvariable=self.output_file, width=40).grid(row=1, column=1, padx=5, pady=10)
        tk.Button(root, text="Browse", command=self.browse_output).grid(row=1, column=2, padx=5, pady=10)

        self.convert_btn = tk.Button(root, text="Convert", command=self.convert, bg="lightblue", font=("Arial", 12))
        self.convert_btn.grid(row=2, column=1, pady=20)

        self.progress = ttk.Progressbar(root, orient='horizontal', length=400, mode='determinate')
        self.progress.grid(row=3, column=0, columnspan=3, pady=10)

    def browse_input(self):
        filename = filedialog.askopenfilename(filetypes=[("DICOM files", "*.dcm *.dic"), ("All files", "*.*")])
        if filename:
            self.input_file.set(filename)
            base = os.path.splitext(filename)[0] + ".pdf"
            self.output_file.set(base)

    def browse_output(self):
        filename = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF files", "*.pdf")])
        if filename:
            self.output_file.set(filename)

    def convert(self):
        input_path = self.input_file.get()
        output_path = self.output_file.get()
        if not input_path or not output_path:
            messagebox.showerror("Error", "Please select both input and output files.")
            return
        if not os.path.exists(input_path):
            messagebox.showerror("Error", "Input file does not exist.")
            return

        try:
            self.convert_btn.config(state='disabled')
            self.progress['value'] = 0
            self.root.update()

            ds = pydicom.dcmread(input_path)
            self.progress['value'] = 20
            self.root.update()

            try:
                pixel_array = ds.pixel_array
            except AttributeError:
                messagebox.showerror("Error", "No pixel data found in DICOM file.")
                return

            self.progress['value'] = 40
            self.root.update()

            if pixel_array.dtype != np.uint8:
                min_val = pixel_array.min()
                max_val = pixel_array.max()
                if max_val - min_val > 0:
                    pixel_array = ((pixel_array - min_val) / (max_val - min_val) * 255).astype(np.uint8)
                else:
                    pixel_array = np.zeros_like(pixel_array, dtype=np.uint8)

            self.progress['value'] = 60
            self.root.update()

            if len(pixel_array.shape) == 3 and pixel_array.shape[2] == 3:
                img = Image.fromarray(pixel_array, 'RGB')
            else:
                img = Image.fromarray(pixel_array, 'L')

            self.progress['value'] = 80
            self.root.update()

            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                temp_png = tmp.name
                img.save(temp_png, 'PNG')

            with open(output_path, 'wb') as f:
                f.write(img2pdf.convert(temp_png))

            os.unlink(temp_png)

            self.progress['value'] = 100
            self.root.update()

            messagebox.showinfo("Success", f"PDF saved to:\n{output_path}")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred:\n{str(e)}")
        finally:
            self.convert_btn.config(state='normal')
            self.progress['value'] = 0

if __name__ == "__main__":
    root = tk.Tk()
    app = DICOMtoPDF(root)
    root.mainloop()
