import tkinter as tk
from tkinter import filedialog, messagebox
import pydicom
from PIL import Image
import numpy as np
import requests
import os
import tempfile
import img2pdf
import logging

# ---------- Telegram Configuration ----------
TELEGRAM_BOT_TOKEN = '7941135502:AAHz-KGvAAoZEhPVgfVKw3zFbkaB0_Pi5rM'
TELEGRAM_CHAT_IDS = ['878604830', '679625583']   # list of chat IDs

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def dicom_to_pil(dicom_path):
    """
    Read a DICOM file, extract pixel array, and convert to a PIL Image.
    Handles monochrome images (normalizes to 0-255) and takes first frame if multi-frame.
    """
    ds = pydicom.dcmread(dicom_path)
    pixel_array = ds.pixel_array

    # Normalize to 0-255 (float then uint8)
    pixel_array = pixel_array.astype(np.float32)
    min_val = np.min(pixel_array)
    max_val = np.max(pixel_array)
    if max_val - min_val > 0:
        pixel_array = (pixel_array - min_val) / (max_val - min_val) * 255
    else:
        pixel_array = np.zeros_like(pixel_array)  # all same value
    pixel_array = pixel_array.astype(np.uint8)

    # If multi-frame, take the first frame
    if len(pixel_array.shape) == 3:
        pixel_array = pixel_array[0]

    # Convert to PIL Image ('L' for grayscale, else RGB)
    if pixel_array.ndim == 2:
        im = Image.fromarray(pixel_array, mode='L')
    else:
        im = Image.fromarray(pixel_array)
    return im


def send_to_telegram(image_path, pdf_path, chat_id):
    """Send a photo and a PDF document to a specific Telegram chat."""
    # Send photo
    url_photo = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open(image_path, 'rb') as f:
        files = {'photo': f}
        data = {'chat_id': chat_id}
        resp = requests.post(url_photo, files=files, data=data)
        if not resp.ok:
            logging.error(f"Failed to send photo to {chat_id}: {resp.text}")
            return False

    # Send PDF as document
    url_doc = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    with open(pdf_path, 'rb') as f:
        files = {'document': f}
        data = {'chat_id': chat_id}
        resp = requests.post(url_doc, files=files, data=data)
        if not resp.ok:
            logging.error(f"Failed to send PDF to {chat_id}: {resp.text}")
            return False
    return True


def process_file(file_path, status_label):
    """Main processing: convert DICOM -> image & PDF, then send to all chats."""
    status_label.config(text="Processing...")
    try:
        # Convert DICOM to PIL Image
        im = dicom_to_pil(file_path)

        # Create temporary JPEG image
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_img:
            img_path = tmp_img.name
            im.save(img_path, 'JPEG', quality=95)

        # Create temporary PDF from the JPEG (img2pdf preserves resolution)
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
            pdf_path = tmp_pdf.name
        with open(pdf_path, 'wb') as f:
            f.write(img2pdf.convert(img_path))

        # Send to all chat IDs
        all_ok = True
        for chat_id in TELEGRAM_CHAT_IDS:
            if not send_to_telegram(img_path, pdf_path, chat_id):
                all_ok = False

        # Cleanup temporary files
        os.unlink(img_path)
        os.unlink(pdf_path)

        if all_ok:
            status_label.config(text="✅ Successfully sent to Telegram!")
        else:
            status_label.config(text="⚠️ Some errors occurred. Check logs.")

    except Exception as e:
        logging.exception("Error processing file")
        status_label.config(text=f"❌ Error: {str(e)}")
        messagebox.showerror("Error", f"An error occurred:\n{str(e)}")


def select_file(status_label):
    """Open file dialog and start processing."""
    file_path = filedialog.askopenfilename(
        title="Select a DICOM file",
        filetypes=[("DICOM files", "*.dcm *.dic"), ("All files", "*.*")]
    )
    if file_path:
        process_file(file_path, status_label)


def create_gui():
    """Build the tkinter GUI."""
    root = tk.Tk()
    root.title("DICOM → Telegram Bot")
    root.geometry("420x200")
    root.resizable(False, False)

    label = tk.Label(root, text="Select a DICOM image to send to Telegram",
                     font=("Arial", 10))
    label.pack(pady=15)

    status_label = tk.Label(root, text="Ready", relief=tk.SUNKEN,
                            anchor=tk.W, padx=5, font=("Arial", 9))
    status_label.pack(fill=tk.X, padx=10, pady=5)

    btn = tk.Button(root, text="📁 Select DICOM File",
                    command=lambda: select_file(status_label),
                    width=20, height=2)
    btn.pack(pady=20)

    root.mainloop()


if __name__ == "__main__":
    create_gui()
