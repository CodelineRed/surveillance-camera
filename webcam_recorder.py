import cv2
import io
import tkinter as tk
from tkinter import messagebox, filedialog
import threading
import time
import os
import datetime
import collections
from PIL import Image, ImageTk # Import Image and ImageTk from Pillow

class WebcamRecorderApp:
    def __init__(self, master):
        self.master = master
        master.title("Webcam Recorder")
        master.geometry("800x600")

        # --- Recording parameters ---
        self.output_directory = "clips" # Default output directory
        self.max_recording_time_minutes = 10 # Total max recording duration in minutes
        self.clip_duration_seconds = 60 # Duration of each clip in seconds (1 minute)

        # Calculate max clips based on total duration and clip duration
        self.max_clips = self.max_recording_time_minutes * 60 // self.clip_duration_seconds
        # Using a deque to manage clip filenames for easy oldest file removal
        self.recorded_clips = collections.deque(maxlen=self.max_clips)

        # --- Webcam parameters ---
        self.cap = None
        self.fps = 20.0
        self.frames = self.fps * self.clip_duration_seconds
        self.current_frames = 0
        self.codec = ('mp4', 'mp4v')
        self.is_recording = False
        self.recording_thread = None # No longer strictly needed for frame processing, but kept for future threading needs
        self.current_clip_start_time = None
        self.current_clip_writer = None
        self.fourcc = cv2.VideoWriter_fourcc(*self.codec[1]) # Codec for files

        # --- Remove all old clips ---
        self.remove_all_clips()

        # --- GUI Elements ---
        self.create_widgets()
        self.update_webcam_feed() # Start displaying webcam feed immediately

    # see: https://raspberrypi.stackexchange.com/a/118473
    def is_raspberrypi(self):
        try:
            with io.open('/sys/firmware/devicetree/base/model', 'r') as m:
                if 'raspberry pi' in m.read().lower(): return True
        except Exception: pass
        return False
    
    def create_widgets(self):
        # Frame for webcam feed
        self.video_label = tk.Label(self.master)
        self.video_label.grid(row=0, column=0, padx=5, pady=5, rowspan=30, sticky="n")

        self.record_button = tk.Button(self.master, text="Start Recording", command=self.toggle_recording, width=15, height=2, bg="green", fg="white")
        self.record_button.grid(row=0, column=1, padx=5, pady=5, sticky="nw")

        self.directory_button = tk.Button(self.master, text="Select Clips Directory", command=self.select_output_directory, width=20, height=2)
        self.directory_button.grid(row=1, column=1, padx=5, pady=5, sticky="nw")

        # Label to display current output directory
        self.directory_label = tk.Label(self.master, justify="left", text=f"Clips Directory:\n{self.output_directory}")
        self.directory_label.grid(row=2, column=1, padx=5, pady=5, sticky="nw")
    
    def create_widgets_2(self):
        # Frame for webcam feed
        self.video_frame = tk.Frame(self.master, bg="black", width=640, height=480)
        self.video_frame.pack(pady=10)
        self.video_label = tk.Label(self.video_frame)
        self.video_label.pack()

        # Frame for control buttons
        control_frame = tk.Frame(self.master)
        control_frame.pack(pady=10)

        self.record_button = tk.Button(control_frame, text="Start Recording", command=self.toggle_recording, width=15, height=2, bg="green", fg="white")
        self.record_button.pack(side=tk.LEFT, padx=10)

        self.directory_button = tk.Button(control_frame, text="Select Clips Directory", command=self.select_output_directory, width=20, height=2)
        self.directory_button.pack(side=tk.LEFT, padx=10)

        # Label to display current output directory
        self.directory_label = tk.Label(self.master, text=f"Clips Directory: {self.output_directory}")
        self.directory_label.pack(pady=5)

    def open_webcam(self):
        """Attempts to open the default webcam."""
        if self.cap is None or not self.cap.isOpened():
            if self.is_raspberrypi():
                self.cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
            else:
                self.cap = cv2.VideoCapture(0)

            if not self.cap.isOpened():
                messagebox.showerror("Webcam Error", "Could not open webcam. Please check if it's connected and not in use.")
                return False
            # Try to set a resolution, not strictly necessary but can help
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            self.fps = self.cap.get(cv2.CAP_PROP_FPS)
            self.frames = int(self.fps * self.clip_duration_seconds)
            print(f"Open webcam with {self.fps} fps")
        return True

    def update_webcam_feed(self):
        """Continuously updates the webcam feed in the GUI using Pillow."""
        if not self.open_webcam():
            self.master.after(5000, self.update_webcam_feed) # Try again after a short delay
            return

        ret, frame = self.cap.read()
        if ret:
            # OpenCV captures in BGR, Pillow expects RGB
            cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Convert NumPy array to Pillow Image
            img_pil = Image.fromarray(cv2image)
            
            # Convert Pillow Image to Tkinter PhotoImage
            img_tk = ImageTk.PhotoImage(image=img_pil)
            
            self.video_label.config(image=img_tk)
            self.video_label.image = img_tk # Keep a reference to prevent garbage collection

            # If recording is active, write the frame
            if self.is_recording and self.current_clip_writer:
                self.current_clip_writer.write(frame)
                self.current_frames += 1
                # self.check_clip_duration()
                self.check_clip_frames()

        self.master.after(10, self.update_webcam_feed) # Call itself after 10ms for continuous update

    def toggle_recording(self):
        """Starts or stops the recording process."""
        if not self.open_webcam():
            return # Cannot start recording if webcam is not open

        if self.is_recording:
            self.stop_recording()
            self.record_button.config(text="Start Recording", bg="green")
        else:
            # Ensure output directory exists
            os.makedirs(self.output_directory, exist_ok=True)
            self.is_recording = True
            self.record_button.config(text="Stop Recording", bg="red")
            messagebox.showinfo("Recording Started", "Recording has started. Clips will be saved to " + self.output_directory)
            self.start_new_clip()
            # Recording frames is now handled by update_webcam_feed
            # The threading is mostly for the long-running video stream
            # but actual frame processing and writing happens in the main thread now
            # to avoid potential issues with OpenCV and threading.

    def start_new_clip(self):
        """Starts a new video clip file."""
        if self.current_clip_writer:
            self.current_clip_writer.release() # Release previous writer

        # Manage max clips
        if len(self.recorded_clips) >= self.max_clips:
            oldest_clip = self.recorded_clips.popleft() # Get and remove the oldest clip name
            if os.path.exists(oldest_clip):
                os.remove(oldest_clip) # Delete the oldest file
                print(f"Removed oldest clip: {oldest_clip}")

        # Create new filename
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(self.output_directory, f"{timestamp}.{self.codec[0]}")

        # Get webcam properties for video writer
        frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        if self.fps == 0: # Fallback if FPS is not detected properly, e.g. on some virtual webcams
            self.fps = 20.0 # Default to 20 FPS

        self.frames = int(self.fps * self.clip_duration_seconds)
        self.current_frames = 0

        # Ensure frame dimensions are not zero
        if frame_width == 0 or frame_height == 0:
            messagebox.showerror("Webcam Error", "Could not determine webcam resolution. Please ensure webcam is functioning.")
            self.stop_recording()
            return
            
        self.current_clip_writer = cv2.VideoWriter(filename, self.fourcc, self.fps, (frame_width, frame_height))
        
        # Check if VideoWriter was opened successfully
        if not self.current_clip_writer.isOpened():
            messagebox.showerror("Recording Error", f"Could not open video writer for {filename}. Ensure codecs are installed (e.g., FFMPEG for {self.codec[1]}).")
            self.stop_recording()
            return

        self.current_clip_start_time = time.time()
        self.recorded_clips.append(filename) # Add new clip to the deque
        print(f"Started new clip: {filename} ({self.fps} fps / {self.clip_duration_seconds} sec)")

    def check_clip_duration(self):
        """Checks if the current clip has reached its duration and starts a new one."""
        if self.current_clip_start_time and (time.time() - self.current_clip_start_time) >= self.clip_duration_seconds:
            self.start_new_clip()

    def check_clip_frames(self):
        """Checks if the current clip has reached its duration and starts a new one."""
        if self.current_frames == self.frames:
            self.start_new_clip()

    def remove_all_clips(self):
        """Removes all old clips"""
        files = os.listdir(self.output_directory)
        for file in files:
            file = os.path.join(self.output_directory, file)
            if file.endswith(self.codec[0]):
                os.remove(file)
                print(f"Removed clip: {file}")

    def stop_recording(self):
        """Stops the current recording and releases resources."""
        self.is_recording = False
        if self.current_clip_writer:
            self.current_clip_writer.release()
            self.current_clip_writer = None
        messagebox.showinfo("Recording Stopped", "Recording has stopped.")
        print("Recording stopped.")

    def select_output_directory(self):
        """Allows the user to select a custom output directory."""
        directory_selected = filedialog.askdirectory()
        if directory_selected:
            self.output_directory = directory_selected
            self.directory_label.config(text=f"Output Directory:\n{self.output_directory}")
            messagebox.showinfo("Directory Selected", f"New output directory: {self.output_directory}")

    def on_closing(self):
        """Handles cleanup when the window is closed."""
        print("Application closing...")
        self.stop_recording() # Ensure recording is stopped
        if self.cap and self.cap.isOpened():
            self.cap.release() # Release webcam
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = WebcamRecorderApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing) # Handle window close event
    root.geometry("820x500")
    root.mainloop()
