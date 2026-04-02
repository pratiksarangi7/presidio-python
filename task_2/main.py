import json
import asyncio
import aiosqlite
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import Dict, Set

app = FastAPI()

DB_FILE = "chat.db"

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT,
                receiver TEXT,
                room TEXT,
                content TEXT,
                timestamp DATETIME
            )
        ''')
        await db.commit()

asyncio.create_task(init_db())

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.rooms: Dict[str, Set[str]] = {}
        self.presence: Dict[str, str] = {}

    async def connect(self, websocket: WebSocket, username: str):
        await websocket.accept()
        self.active_connections[username] = websocket
        self.presence[username] = "online"
        await self.broadcast_presence()

    async def disconnect(self, username: str):
        if username in self.active_connections:
            del self.active_connections[username]
        self.presence[username] = "offline"
        for room in self.rooms.values():
            room.discard(username)
        await self.broadcast_presence()

    async def join_room(self, username: str, room: str):
        if room not in self.rooms:
            self.rooms[room] = set()
        self.rooms[room].add(username)

    async def send_private(self, message: dict, receiver: str):
        if receiver in self.active_connections:
            await self.active_connections[receiver].send_json(message)

    async def broadcast_room(self, message: dict, room: str):
        if room in self.rooms:
            for user in self.rooms[room]:
                if user in self.active_connections:
                    await self.active_connections[user].send_json(message)

    async def broadcast_presence(self):
        msg = {"type": "presence", "data": self.presence}
        for connection in self.active_connections.values():
            await connection.send_json(msg)

manager = ConnectionManager()

@app.get("/")
async def get():
    with open("index.html", "r") as f:
        return HTMLResponse(f.read())

@app.get("/history/{room}")
async def get_history(room: str):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT sender, content, timestamp FROM messages WHERE room = ? ORDER BY timestamp ASC", (room,)) as cursor:
            rows = await cursor.fetchall()
            return [{"sender": row[0], "content": row[1], "timestamp": row[2]} for row in rows]

@app.websocket("/ws/{username}")
async def websocket_endpoint(websocket: WebSocket, username: str):
    await manager.connect(websocket, username)
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            msg_type = payload.get("type")

            if msg_type == "join":
                room = payload["room"]
                await manager.join_room(username, room)
                
            elif msg_type == "chat":
                room = payload.get("room")
                content = payload["content"]
                
                # Save to DB
                async with aiosqlite.connect(DB_FILE) as db:
                    await db.execute("INSERT INTO messages (sender, room, content, timestamp) VALUES (?, ?, ?, ?)",
                                     (username, room, content, datetime.now()))
                    await db.commit()

                await manager.broadcast_room({
                    "type": "chat",
                    "sender": username,
                    "content": content,
                    "room": room
                }, room)
                
            elif msg_type == "private":
                receiver = payload["receiver"]
                content = payload["content"]
                
                async with aiosqlite.connect(DB_FILE) as db:
                    await db.execute("INSERT INTO messages (sender, receiver, content, timestamp) VALUES (?, ?, ?, ?)",
                                     (username, receiver, content, datetime.now()))
                    await db.commit()

                msg = {"type": "private", "sender": username, "content": content}
                await manager.send_private(msg, receiver)
                await websocket.send_json(msg) # Send copy to self
                
            elif msg_type == "typing":
                room = payload.get("room")
                if room:
                    await manager.broadcast_room({"type": "typing", "sender": username, "room": room}, room)

    except WebSocketDisconnect:
        await manager.disconnect(username)