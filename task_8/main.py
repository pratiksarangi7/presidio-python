import asyncio
import json
import random
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import pandas as pd
import numpy as np

app = FastAPI()

# Configuration
WINDOW_SIZE = 300  # 300 seconds = 5 minutes of data points (at 1 sec intervals)
THRESHOLD_Z = 2.0  # Alert threshold for Z-score

# In-memory storage for sensor data
sensor_data = {
    "temperature": pd.Series(dtype=float),
    "vibration": pd.Series(dtype=float)
}

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass

manager = ConnectionManager()

async def generate_sensor_data():
    """Background task simulating IoT data ingestion and processing."""
    while True:
        # Simulate normal sensor readings
        new_temp = random.normalvariate(mu=25.0, sigma=2.0)  # Baseline ~25°C
        new_vib = random.normalvariate(mu=5.0, sigma=1.0)    # Baseline ~5 mm/s

        # Randomly inject anomalies (5% chance)
        if random.random() < 0.05:
            new_temp += random.choice([10, -10])
        if random.random() < 0.05:
            new_vib += random.choice([5, -5])

        current_time = pd.Timestamp.now()

        # Append new data to our pandas Series
        sensor_data["temperature"].loc[current_time] = new_temp
        sensor_data["vibration"].loc[current_time] = new_vib

        # Enforce rolling window size to prevent memory leaks
        if len(sensor_data["temperature"]) > WINDOW_SIZE:
            sensor_data["temperature"] = sensor_data["temperature"].iloc[-WINDOW_SIZE:]
            sensor_data["vibration"] = sensor_data["vibration"].iloc[-WINDOW_SIZE:]

        # Calculate statistics
        stats = {}
        for sensor in ["temperature", "vibration"]:
            series = sensor_data[sensor]
            if len(series) > 2:
                mean = series.mean()
                std = series.std()
                std = std if std > 0 else 1e-6 # Prevent division by zero
                current_val = series.iloc[-1]
                
                z_score = (current_val - mean) / std
                is_anomaly = abs(z_score) > THRESHOLD_Z

                stats[sensor] = {
                    "value": round(current_val, 2),
                    "moving_average": round(mean, 2),
                    "z_score": round(z_score, 2),
                    "is_anomaly": bool(is_anomaly)
                }
            else:
                # Not enough data for stats yet
                stats[sensor] = {
                    "value": round(series.iloc[-1], 2),
                    "moving_average": round(series.iloc[-1], 2),
                    "z_score": 0.0,
                    "is_anomaly": False
                }

        payload = {
            "timestamp": current_time.strftime("%H:%M:%S"),
            "sensors": stats
        }

        # Push to all connected WebSocket clients
        await manager.broadcast(json.dumps(payload))
        
        # Stream interval
        await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    # Start the data generation loop in the background when the server starts
    asyncio.create_task(generate_sensor_data())

@app.get("/")
async def get():
    # Serve the HTML frontend
    with open("index.html", "r") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection open; we only send data, so we wait for disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)