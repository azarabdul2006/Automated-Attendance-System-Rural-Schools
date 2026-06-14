import os
import cv2
import numpy as np
import face_recognition
import mediapipe as mp
import pandas as pd
from datetime import datetime
import time
import threading
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import traceback

# -----------------------
# Configuration
# -----------------------
attendance_xlsx = "attendance.xlsx"      # main workbook (kept append-only)
attendance_log_csv = "attendance_log.csv"  # append-only CSV queue (fast, safe)
admin_password = "admin123"

# lock to protect xlsx merge operation
file_lock = threading.Lock()

# ensure base files exist
def ensure_files():
    # ensure xlsx exists (create empty if missing)
    if not os.path.exists(attendance_xlsx):
        df = pd.DataFrame(columns=["Name", "Date", "Time", "Photo"])
        try:
            df.to_excel(attendance_xlsx, index=False)
        except Exception:
            # If writing xlsx fails (e.g. Excel open), still ensure CSV exists so we don't lose data
            pass
    # ensure csv exists
    if not os.path.exists(attendance_log_csv):
        pd.DataFrame(columns=["Name", "Date", "Time", "Photo"]).to_csv(attendance_log_csv, index=False)

ensure_files()

# -----------------------
# Helpers
# -----------------------
def append_to_csv_queue(name, date_str, time_str, photo_path):
    """Fast, safe append to CSV queue."""
    row = {"Name": name, "Date": date_str, "Time": time_str, "Photo": photo_path}
    header = not os.path.exists(attendance_log_csv) or os.path.getsize(attendance_log_csv) == 0
    # Use newline='' to avoid extra blank lines on Windows
    try:
        pd.DataFrame([row]).to_csv(attendance_log_csv, mode="a", header=header, index=False)
        return True
    except Exception as e:
        print("Failed to write to CSV queue:", e)
        traceback.print_exc()
        return False

def try_append_xlsx(name, date_str, time_str, photo_path, attempts=3, delay=0.6):
    """
    Try to append the row to attendance_xlsx (best-effort).
    Returns True if written to xlsx, False otherwise.
    """
    new_row = pd.DataFrame([[name, date_str, time_str, photo_path]],
                           columns=["Name", "Date", "Time", "Photo"])
    for attempt in range(attempts):
        try:
            with file_lock:
                # read existing xlsx (if exists) and append
                if os.path.exists(attendance_xlsx):
                    existing = pd.read_excel(attendance_xlsx)
                else:
                    existing = pd.DataFrame(columns=["Name", "Date", "Time", "Photo"])
                updated = pd.concat([existing, new_row], ignore_index=True)
                # write via a temp file then atomic replace where possible
                tmp = attendance_xlsx + ".tmp"
                updated.to_excel(tmp, index=False)
                try:
                    os.replace(tmp, attendance_xlsx)
                except Exception:
                    # fallback: try direct write
                    updated.to_excel(attendance_xlsx, index=False)
            return True
        except PermissionError:
            # xlsx likely opened in Excel — wait and retry
            print(f"PermissionError when writing XLSX (attempt {attempt+1}/{attempts})")
            time.sleep(delay)
        except Exception as e:
            print("Unexpected error trying to append xlsx:", e)
            traceback.print_exc()
            time.sleep(delay)
    return False

def read_merged_attendance():
    """
    Read attendance_xlsx (if readable) and append queued CSV rows on top.
    Returns a merged DataFrame (xlsx rows first, then queued CSV rows).
    """
    # read xlsx if possible
    with file_lock:
        try:
            if os.path.exists(attendance_xlsx):
                df_xlsx = pd.read_excel(attendance_xlsx)
            else:
                df_xlsx = pd.DataFrame(columns=["Name", "Date", "Time", "Photo"])
        except Exception:
            df_xlsx = pd.DataFrame(columns=["Name", "Date", "Time", "Photo"])
    # read CSV (queued rows)
    try:
        if os.path.exists(attendance_log_csv):
            df_csv = pd.read_csv(attendance_log_csv)
        else:
            df_csv = pd.DataFrame(columns=["Name", "Date", "Time", "Photo"])
    except Exception:
        df_csv = pd.DataFrame(columns=["Name", "Date", "Time", "Photo"])
    # merged view (xlsx first, queued after)
    merged = pd.concat([df_xlsx, df_csv], ignore_index=True)
    return merged

def merge_csv_into_xlsx():
    """
    Attempt to move queued CSV rows into the main xlsx file.
    If merge succeeds, delete/empty the CSV.
    Returns (True, message) on success, (False, message) on failure.
    """
    # read queued rows
    if not os.path.exists(attendance_log_csv) or os.path.getsize(attendance_log_csv) == 0:
        return True, "No queued attendance to merge."

    try:
        df_queue = pd.read_csv(attendance_log_csv)
    except Exception as e:
        return False, f"Failed to read queue CSV: {e}"

    # attempt to merge into xlsx
    try:
        with file_lock:
            if os.path.exists(attendance_xlsx):
                df_main = pd.read_excel(attendance_xlsx)
            else:
                df_main = pd.DataFrame(columns=["Name", "Date", "Time", "Photo"])
            df_new = pd.concat([df_main, df_queue], ignore_index=True)
            tmp = attendance_xlsx + ".tmp"
            df_new.to_excel(tmp, index=False)
            try:
                os.replace(tmp, attendance_xlsx)
            except Exception:
                df_new.to_excel(attendance_xlsx, index=False)
        # success — clear CSV
        # safer: write an empty CSV with header
        pd.DataFrame(columns=["Name", "Date", "Time", "Photo"]).to_csv(attendance_log_csv, index=False)
        return True, f"Merged {len(df_queue)} queued rows into {attendance_xlsx}."
    except PermissionError:
        return False, f"Permission denied when trying to write {attendance_xlsx}. Close the file in Excel and try again."
    except Exception as e:
        traceback.print_exc()
        return False, f"Unexpected error during merge: {e}"

# -----------------------
# Attendance (camera loop)
# -----------------------
def start_attendance_system():
    try:
        print("🔍 Loading known faces...")
        known_encodings = []
        known_names = []

        if not os.path.exists("known_faces"):
            os.makedirs("known_faces")

        for filename in os.listdir("known_faces"):
            if filename.lower().endswith((".jpg", ".png", ".jpeg")):
                path = os.path.join("known_faces", filename)
                img = face_recognition.load_image_file(path)
                if img.dtype != np.uint8:
                    img = np.ascontiguousarray(img, dtype=np.uint8)
                enc = face_recognition.face_encodings(img)
                if enc:
                    known_encodings.append(enc[0])
                    known_names.append(os.path.splitext(filename)[0])
                else:
                    print(f"⚠ No face found in {filename}. Skipping...")

        if not known_encodings:
            messagebox.showwarning("No Faces", "No known faces found in 'known_faces/' folder.")
            return

        mp_face_mesh = mp.solutions.face_mesh
        face_mesh = mp_face_mesh.FaceMesh(refine_landmarks=True, max_num_faces=1)
        LEFT_EYE = [33, 160, 158, 133, 153, 144]
        RIGHT_EYE = [362, 385, 387, 263, 373, 380]

        def ear(landmarks, eye_pts, w, h):
            pts = [(int(landmarks[i].x * w), int(landmarks[i].y * h)) for i in eye_pts]
            A = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
            B = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
            C = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))
            if C == 0:
                return 0.0
            return (A + B) / (2.0 * C)

        if not os.path.exists("captures"):
            os.makedirs("captures")

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("Camera Error", "Could not open camera.")
            return

        blink_counter = 0
        blink_trigger = 3
        last_blink_time = 0
        attendance_done = set()

        print("🚀 Starting system... Blink 3 times quickly to mark attendance")

        while True:
            ret, frame = cap.read()
            if not ret:
                print("Camera read failed, exiting attendance loop.")
                break

            h, w = frame.shape[:2]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)

            if results.multi_face_landmarks:
                for face_landmarks in results.multi_face_landmarks:
                    left = ear(face_landmarks.landmark, LEFT_EYE, w, h)
                    right = ear(face_landmarks.landmark, RIGHT_EYE, w, h)
                    avg_ear = (left + right) / 2.0

                    if avg_ear < 0.22:
                        nowt = time.time()
                        if nowt - last_blink_time < 1.5:
                            blink_counter += 1
                        else:
                            blink_counter = 1
                        last_blink_time = nowt

                        cv2.putText(frame, f"Blink #{blink_counter}", (30, 80),
                                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

                        if blink_counter >= blink_trigger:
                            face_locs = face_recognition.face_locations(rgb)
                            face_encs = face_recognition.face_encodings(rgb, face_locs)
                            for (t, r, b, l), fe in zip(face_locs, face_encs):
                                matches = face_recognition.compare_faces(known_encodings, fe)
                                name = "Unknown"
                                if True in matches:
                                    idx = matches.index(True)
                                    name = known_names[idx]

                                now = datetime.now()
                                date_str = now.strftime("%Y-%m-%d")
                                time_str = now.strftime("%H-%M-%S")

                                if name not in attendance_done:
                                    # save capture (best-effort)
                                    photo_path = ""
                                    try:
                                        photo_path = f"captures/{name}_{date_str}_{time_str}.jpg"
                                        cv2.imwrite(photo_path, frame)
                                    except Exception:
                                        photo_path = ""

                                    # append to CSV queue (always)
                                    append_to_csv_queue(name, date_str, time_str, photo_path)
                                    # try best-effort to append to xlsx too (non-blocking)
                                    written = try_append_xlsx(name, date_str, time_str, photo_path)
                                    if not written:
                                        print("Saved to CSV queue (xlsx write failed or locked).")
                                    attendance_done.add(name)
                                    print(f"✅ {name} marked at {date_str} {time_str}")
                                    cv2.putText(frame, "Attendance Recorded!", (50, 400),
                                                cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 0), 3)
                            blink_counter = 0

            cv2.putText(frame, "Blink 3 times fast to mark attendance", (30, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)

            cv2.imshow("Attendance System", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break

        cap.release()
        cv2.destroyAllWindows()
    except Exception as e:
        print("Attendance loop error:", e)
        traceback.print_exc()
        try:
            messagebox.showerror("Attendance Error", str(e))
        except Exception:
            pass

# run attendance in separate thread to keep GUI responsive
def start_attendance_thread():
    t = threading.Thread(target=start_attendance_system, daemon=True)
    t.start()
    messagebox.showinfo("Started", "Teacher Attendance started (camera running in background).")

# -----------------------
# Admin Panel (read-only + merge)
# -----------------------
def open_admin_panel():
    admin_win = tk.Toplevel(root)
    admin_win.title("Administrator Login")
    admin_win.geometry("320x180")
    tk.Label(admin_win, text="Enter Admin Password:", font=("Arial", 12)).pack(pady=12)
    pwd = tk.Entry(admin_win, show="*", width=28)
    pwd.pack(pady=5)

    def verify():
        if pwd.get().strip() == admin_password:
            admin_win.destroy()
            show_admin_data()
        else:
            messagebox.showerror("Access Denied", "Invalid administrator password!")

    tk.Button(admin_win, text="Login", command=verify, bg="#28a745", fg="white", width=12).pack(pady=12)

def show_admin_data():
    merged = read_merged_attendance()
    admin_data_window = tk.Toplevel(root)
    admin_data_window.title("Administrator Panel (Read-Only)")
    admin_data_window.geometry("950x600")

    frame = ttk.Frame(admin_data_window)
    frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    cols = list(merged.columns) if not merged.empty else ["Name","Date","Time","Photo"]
    tree = ttk.Treeview(frame, columns=cols, show="headings")
    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=200, anchor="center")

    for _, r in merged.iterrows():
        vals = [r.get(c, "") for c in cols]
        tree.insert("", tk.END, values=vals)

    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)

    # Buttons: Export CSV (current merged view) and Merge queued CSV -> xlsx
    def export_csv_btn():
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV files","*.csv")],
                                            title="Export merged data to CSV")
        if not path:
            return
        try:
            merged.to_csv(path, index=False)
            messagebox.showinfo("Exported", f"Exported merged data to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export: {e}")

    def merge_btn():
        ok = messagebox.askyesno("Merge queued data", "This will try to merge queued attendance rows from "
                                                      f"'{attendance_log_csv}' into '{attendance_xlsx}'.\n\n"
                                                      "Make sure the Excel file is closed. Proceed?")
        if not ok:
            return
        success, msg = merge_csv_into_xlsx()
        if success:
            messagebox.showinfo("Merge Result", msg)
            # refresh view
            admin_data_window.destroy()
            show_admin_data()
        else:
            messagebox.showerror("Merge Failed", msg)

    btn_frame = ttk.Frame(admin_data_window)
    btn_frame.pack(fill=tk.X, pady=(0,10))
    ttk.Button(btn_frame, text="Export Merged CSV", command=export_csv_btn).pack(side=tk.LEFT, padx=8)
    ttk.Button(btn_frame, text="Merge queued CSV → XLSX", command=merge_btn).pack(side=tk.LEFT, padx=8)
    ttk.Button(btn_frame, text="Refresh", command=lambda: (admin_data_window.destroy(), show_admin_data())).pack(side=tk.RIGHT, padx=8)

# -----------------------
# Main GUI
# -----------------------
root = tk.Tk()
root.title("Face Recognition Attendance System")
root.geometry("420x320")

tk.Label(root, text="Login Interface", font=("Arial", 18, "bold")).pack(pady=18)

tk.Button(root, text="👩‍🏫 Start Attendance (Teacher)", command=start_attendance_thread,
          bg="#007bff", fg="white", font=("Arial", 12), width=28).pack(pady=10)

tk.Button(root, text="👨‍💼 Login as Administrator", command=open_admin_panel,
          bg="#6c757d", fg="white", font=("Arial", 12), width=28).pack(pady=6)

tk.Button(root, text="Exit", command=root.destroy, bg="#dc3545", fg="white",
          font=("Arial", 12), width=28).pack(pady=18)

root.mainloop()