# Automated Attendance System for Rural Schools

## Overview

The Automated Attendance System for Rural Schools is an attendance management solution that uses Face Recognition and Blink Detection to automatically record attendance. The system is designed to reduce manual attendance work, prevent proxy attendance, and support schools with limited internet connectivity.

## Features

* Face Recognition based attendance marking
* Blink Detection for anti-spoofing protection
* Automatic attendance recording
* Administrator login and dashboard
* Attendance export to Excel and CSV
* Offline operation support
* Real-time camera monitoring
* Attendance photo capture and storage
* User-friendly graphical interface using Tkinter

## Technologies Used

* Python
* OpenCV
* Face Recognition Library
* MediaPipe
* NumPy
* Pandas
* OpenPyXL
* Tkinter

## Project Structure

```text
Automated-Attendance-System-Rural-Schools/
│
├── program.py
├── requirements.txt
├── README.md
├── .gitignore
├── known_faces/
├── captures/
├── attendance.xlsx
└── attendance_log.csv
```

## Installation

### Clone the Repository

```bash
git clone https://github.com/your-username/Automated-Attendance-System-Rural-Schools.git
cd Automated-Attendance-System-Rural-Schools
```

### Create Virtual Environment

```bash
python -m venv .venv
```

### Activate Virtual Environment

#### Windows

```bash
.venv\Scripts\activate
```

#### Linux/macOS

```bash
source .venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

1. Add registered users' images to the `known_faces` folder.
2. Run the application:

```bash
python program.py
```

3. Click **Start Attendance**.
4. Blink three times to verify liveness.
5. Attendance will be recorded automatically.

## Security Features

* Face Recognition Authentication
* Blink-Based Liveness Detection
* Administrator Access Control
* Offline Data Storage
* Attendance Record Protection

## Benefits

* Eliminates manual attendance registers
* Prevents proxy attendance
* Saves teachers' time
* Reduces paperwork
* Supports rural schools with limited internet access
* Improves attendance accuracy

## Future Enhancements

* Cloud Synchronization
* Mobile Application
* SMS Notifications for Parents
* Student Attendance Analytics
* Multi-School Management System

## Author

**Abdul Kani**

Cybersecurity Enthusiast | Python Developer | AI & Face Recognition Projects

## License

This project is developed for educational and research purposes.
