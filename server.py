from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import uvicorn
import json
from pathlib import Path

app = FastAPI()

UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


# ── AXIS CONFIGURATION ─────────────────────────────────────
class AxisConfig:
    """
    Single source of truth for which axes are active.
    Maximum supported: 4 axes (X Y Z A).
    B axis is not used in this project.
    """
    ALL_AXES     = ["X", "Y", "Z", "A"]
    VALID_COUNTS = {
        2: ["X", "Y"],
        3: ["X", "Y", "Z"],
        4: ["X", "Y", "Z", "A"],
    }

    def __init__(self):
        self.count  = 4
        self.active = list(self.VALID_COUNTS[4])

    def set_count(self, count: int) -> dict:
        if count not in self.VALID_COUNTS:
            return {"error": f"Invalid axis count {count}. Must be 2, 3, or 4."}
        self.count  = count
        self.active = list(self.VALID_COUNTS[count])
        return None

    def is_active(self, axis: str) -> bool:
        return axis in self.active

    def filter_position(self, full_pos: dict) -> dict:
        return {ax: full_pos[ax] for ax in self.active if ax in full_pos}

    def as_response(self) -> dict:
        return {"count": self.count, "axes": self.active}


axis_config = AxisConfig()


# ── FPGA INTERFACE (abstract) ──────────────────────────────
class FPGAController:
    def __init__(self):
        # Track X Y Z A only — B axis removed.
        self.position = {"X": 0.0, "Y": 0.0, "Z": 0.0, "A": 0.0}

    def send_command(self, command: dict):
        """Send command to FPGA — abstract; replace with real SPI/UART call."""
        if command.get("type") == "jog":
            axis     = command.get("axis")
            distance = command.get("distance", 0.0)
            if axis in self.position:
                self.position[axis] += distance

        elif command.get("type") == "linear_move":
            target = command.get("target", {})
            for ax in ("X", "Y", "Z", "A"):
                if ax in target:
                    self.position[ax] = target[ax]

        print(f"FPGA Command: {command}")

    def get_position(self) -> dict:
        return dict(self.position)

    def flash_firmware(self, filepath: str) -> dict:
        print(f"Flashing FPGA firmware: {filepath}")
        return {"status": "success", "message": f"Firmware flashed: {Path(filepath).name}"}

    def reset(self, axes: list[str] | None = None):
        targets = axes if axes is not None else list(self.position.keys())
        for ax in targets:
            if ax in self.position:
                self.position[ax] = 0.0


fpga = FPGAController()


# ── G-CODE PARSER ──────────────────────────────────────────
class GCodeParser:
    """
    Parses a subset of G-code for CNC visualisation.

    Supported motion codes: G0 / G00 (rapid), G1 / G01 (feed).
    Supported axis letters: X Y Z A  (F = feedrate).
    All other lines (G2, G3, M-codes, comments) are skipped silently.

    The active_axes parameter filters which axes are included in
    toolpath and commands — inactive axes are ignored even if present
    in the G-code file.
    """

    MOTION_CODES = {"G0", "G1", "G00", "G01"}
    ALL_AXES     = {"X", "Y", "Z", "A"}
    RAPID_CODES  = {"G0", "G00"}

    def parse(self, gcode_text: str, active_axes: list[str]) -> dict:
        active_set = set(active_axes)  # fast membership test
        lines      = gcode_text.strip().split("\n")
        toolpath   = []
        commands   = []

        # Current position — only active axes, all start at 0
        pos = {ax: 0.0 for ax in active_axes}

        for raw in lines:
            line = raw.split(";")[0].split("(")[0].strip()
            if not line:
                continue

            parts = line.split()
            if not parts:
                continue

            cmd = parts[0].upper()
            if cmd not in self.MOTION_CODES:
                continue

            # Extract coordinates — only for active axes
            coords: dict[str, float] = {}
            feedrate = 100.0
            for token in parts[1:]:
                if not token:
                    continue
                letter = token[0].upper()
                if letter in active_set:
                    try:
                        coords[letter] = float(token[1:])
                    except ValueError:
                        pass
                elif letter == "F":
                    try:
                        feedrate = float(token[1:])
                    except ValueError:
                        pass

            # Skip lines that only move inactive axes
            if not coords:
                continue

            new_pos = {**pos, **coords}

            toolpath.append({
                "from": dict(pos),
                "to":   dict(new_pos),
                "type": "rapid" if cmd in self.RAPID_CODES else "feed",
            })

            commands.append({
                "type":     "linear_move",
                "target":   dict(new_pos),
                "feedrate": feedrate,
            })

            pos = new_pos

        return {"toolpath": toolpath, "commands": commands}


parser = GCodeParser()


# ── REST ENDPOINTS ─────────────────────────────────────────

# ── Axis configuration ─────────────────────────────────────

@app.get("/api/config/axes")
async def get_axis_config():
    """Return the current axis configuration."""
    return axis_config.as_response()


@app.post("/api/config/axes")
async def set_axis_config(data: dict):
    """
    Set the active axis count.
    Body: {"count": 3}
    Returns the new config plus the filtered current position.
    """
    count = data.get("count")
    if not isinstance(count, int):
        return JSONResponse({"error": "count must be an integer"}, status_code=400)

    err = axis_config.set_count(count)
    if err:
        return JSONResponse(err, status_code=400)

    # Zero axes that just became inactive so position stays consistent
    inactive = [ax for ax in AxisConfig.ALL_AXES if not axis_config.is_active(ax)]
    fpga.reset(inactive)

    return {
        **axis_config.as_response(),
        "position": axis_config.filter_position(fpga.get_position()),
    }


# ── Motion endpoints ────────────────────────────────────────

@app.post("/api/upload/gcode")
async def upload_gcode(file: UploadFile):
    filepath = UPLOAD_DIR / file.filename
    content  = await file.read()
    filepath.write_bytes(content)

    # Parse only with currently active axes
    parsed = parser.parse(content.decode("utf-8"), axis_config.active)
    return {
        "filename":      file.filename,
        "toolpath":      parsed["toolpath"],
        "command_count": len(parsed["commands"]),
        "active_axes":   axis_config.active,
    }


@app.post("/api/upload/firmware")
async def upload_firmware(file: UploadFile):
    if not file.filename.lower().endswith((".bit", ".mcs")):
        return JSONResponse({"error": "Invalid firmware format. Use .bit or .mcs"}, status_code=400)

    filepath = UPLOAD_DIR / file.filename
    content  = await file.read()
    filepath.write_bytes(content)

    result = fpga.flash_firmware(str(filepath))
    return result


@app.post("/api/update/software")
async def update_software(file: UploadFile):
    filepath = UPLOAD_DIR / file.filename
    content  = await file.read()
    filepath.write_bytes(content)

    print(f"Software update triggered: {filepath}")
    return {"status": "success", "message": f"Software update queued: {file.filename}"}


@app.post("/api/jog")
async def jog_axis(data: dict):
    """
    Single-step jog.
    Rejects jog commands targeting an inactive axis — prevents
    the frontend and backend from getting out of sync.
    """
    axis = data.get("axis")
    if not axis or not axis_config.is_active(axis):
        return JSONResponse(
            {"error": f"Axis '{axis}' is not active in the current {axis_config.count}-axis config."},
            status_code=400,
        )

    fpga.send_command({
        "type":     "jog",
        "axis":     axis,
        "distance": data.get("distance", 0.0),
    })

    return {"position": axis_config.filter_position(fpga.get_position())}


@app.post("/api/reset")
async def reset_position():
    """Reset only the active axes to zero."""
    fpga.reset(axis_config.active)
    return {"position": axis_config.filter_position(fpga.get_position())}


@app.get("/api/position")
async def get_position():
    """Return position for active axes only."""
    return axis_config.filter_position(fpga.get_position())


@app.post("/api/run")
async def run_gcode(data: dict):
    """Execute a previously uploaded G-code file with the current active axes."""
    filename = data.get("filename")
    if not filename:
        return JSONResponse({"error": "filename required"}, status_code=400)

    filepath = UPLOAD_DIR / filename
    if not filepath.exists():
        return JSONResponse({"error": "File not found"}, status_code=404)

    parsed = parser.parse(filepath.read_text(), axis_config.active)

    for cmd in parsed["commands"]:
        fpga.send_command(cmd)

    return {
        "status":        "running",
        "commands_sent": len(parsed["commands"]),
        "position":      axis_config.filter_position(fpga.get_position()),
        "active_axes":   axis_config.active,
    }


# ── WEBSOCKET ──────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    # Send config immediately on connect so frontend syncs
    await websocket.send_json({
        "type":     "config",
        "config":   axis_config.as_response(),
        "position": axis_config.filter_position(fpga.get_position()),
    })

    try:
        while True:
            raw  = await websocket.receive_text()
            msg  = json.loads(raw)
            kind = msg.get("type")

            if kind == "jog":
                axis = msg.get("axis")
                if axis and axis_config.is_active(axis):
                    fpga.send_command(msg)
                await websocket.send_json({
                    "position": axis_config.filter_position(fpga.get_position())
                })

            elif kind == "get_position":
                await websocket.send_json({
                    "position": axis_config.filter_position(fpga.get_position())
                })

            elif kind == "get_config":
                await websocket.send_json({
                    "type":   "config",
                    "config": axis_config.as_response(),
                })

    except WebSocketDisconnect:
        print("Client disconnected")


# ── STATIC FILES ───────────────────────────────────────────
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, reload=False)