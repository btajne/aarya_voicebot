import tkinter as tk
from PIL import Image, ImageTk, ImageSequence

# --- Window setup ---
root = tk.Tk()
root.title("Voice Bot Animation")
root.configure(bg="black")
root.attributes("-fullscreen", True)

root.bind("<Escape>", lambda e: root.destroy())

# --- Load GIF ---
gif_path = "Audio&Voice-A-002_black.gif"
im = Image.open(gif_path)

# --- Screen size ---
screen_width = root.winfo_screenwidth()
screen_height = root.winfo_screenheight()

lbl = tk.Label(root, bg="black")
lbl.pack(fill="both", expand=True)

# --- Animation loop ---
def animate(counter):
    try:
        im.seek(counter)
        frame = im.copy().convert("RGBA").resize((screen_width, screen_height))
        frame = ImageTk.PhotoImage(frame)
        lbl.config(image=frame)
        lbl.image = frame
        counter += 1

        # Speed factor — smaller = faster
        speed_factor = 0.6  # try 0.5 or 0.4 for faster animation
        delay = int(im.info.get('duration', 50) * speed_factor)

        root.after(delay, animate, counter)
    except EOFError:
        animate(0)

# --- Start animation ---
animate(0)
root.mainloop()

