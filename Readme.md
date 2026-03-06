# CNC Control System - Project #3

Simple web-based CNC control interface for Raspberry Pi 5.

## Setup

1. Install dependencies:
bash
pip install -r requirements.txt


2. Create static directory and move index.html:
bash
mkdir static
mv index.html static/


3. Run server:
bash
python server.py


4. Open browser:

http://<raspberry-pi-ip>:8080


## Features

- *Manual Jogging*: X, Y, Z, A, B axes with adjustable step size
- *Position Display*: Real-time axis positions
- *G-code Upload*: Upload and preview toolpaths in 3D
- *G-code Execution*: Send parsed commands to FPGA
- *FPGA Firmware Update*: Flash .bit/.mcs files
- *Software Update*: Update Raspberry Pi software

## Architecture

### Backend (server.py)
- FastAPI web server on port 8080
- REST endpoints for file uploads and control
- WebSocket for real-time position updates
- Abstract FPGA interface (FPGAController class)
- G-code parser (GCodeParser class)

### Frontend (index.html)
- WebGL 3D preview using Three.js
- WebSocket client for real-time updates
- Manual jog controls
- File upload interfaces

### FPGA Communication
The FPGAController class provides abstract methods:
- send_command(command: dict) - Send motion/control commands
- get_position() - Get current logical position
- flash_firmware(filepath: str) - Trigger firmware update

*Replace these methods with actual FPGA communication protocol.*

## API Endpoints

- POST /api/upload/gcode - Upload G-code file
- POST /api/upload/firmware - Upload FPGA firmware
- POST /api/update/software - Upload software update
- POST /api/jog - Manual jog command
- GET /api/position - Get current position
- POST /api/run - Execute uploaded G-code
- WS /ws - WebSocket for real-time updates

## File Structure


.
├── server.py          # Backend server
├── requirements.txt   # Python dependencies
├── static/
│   └── index.html    # Web interface
└── uploads/          # Uploaded files (auto-created)


## Notes

- FPGA communication is abstracted - implement actual protocol in FPGAController
- Position updates are logical, not real-time guaranteed
- No authentication - local network use only
- G-code parser handles G0/G1 linear moves (extend as needed)