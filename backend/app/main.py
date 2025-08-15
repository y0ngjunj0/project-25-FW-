# ====== FastAPI: /ingest (single/batch) & retrieval (SQLite) ======
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
import sqlite3

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FSR Ingest")

# CORS (dev: allow all; tighten for prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "data.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            value INTEGER NOT NULL,
            ts_server TEXT NOT NULL,
            ts_client TEXT
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_measurements_device_id ON measurements(device_id, id)")
    conn.commit()
    conn.close()

init_db()

class Measurement(BaseModel):
    device_id: str = Field(..., min_length=1)
    value: Optional[int] = Field(None, ge=0, le=4096)      # ESP32: 12-bit range
    values: Optional[List[int]] = None                     # Batch values
    ts: Optional[datetime] = None                          # Optional client timestamp

    # v2: use model_validator instead of root_validator
    @model_validator(mode="after")
    def check_exclusive_fields(self):
        has_value = self.value is not None
        has_values = self.values is not None
        if has_value == has_values:  # both given or both missing
            raise ValueError("Exactly one of 'value' or 'values' must be provided.")
        return self

    # v2: use field_validator (replaces validator(..., each_item=True))
    @field_validator("values")
    @classmethod
    def validate_values(cls, v):
        if v is None:
            return v
        for item in v:
            if not (0 <= item <= 4096):
                raise ValueError("each value in 'values' must be in range 0..4095")
        return v

store: List[dict] = []

def insert_row(device_id: str, value: int, ts_server: str, ts_client: Optional[str]):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        INSERT INTO measurements (device_id, value, ts_server, ts_client)
        VALUES (?, ?, ?, ?)
    """, (device_id, value, ts_server, ts_client))
    conn.commit()
    conn.close()

@app.post("/ingest")
def ingest(m: Measurement):
    ts_server = datetime.now(timezone.utc).isoformat()
    ts_client = m.ts.isoformat() if m.ts else None

    if m.values is not None:
        # expand and store each channel, but respond with values only
        for idx, val in enumerate(m.values):
            dev = f"{m.device_id}-ch{idx}"
            rec = {
                "device_id": dev,
                "value": val,
                "ts_server": ts_server,
                "ts_client": ts_client
            }
            store.append(rec)
            insert_row(rec["device_id"], rec["value"], rec["ts_server"], rec["ts_client"])

        # log without id/count
        print(f"[INGEST/BATCH] values={m.values}, ts_server={ts_server}")

        # respond with sensor values only (JSON array)
        return m.values

    else:
        rec = {
            "device_id": m.device_id,
            "value": m.value,   # type: ignore
            "ts_server": ts_server,
            "ts_client": ts_client
        }
        store.append(rec)
        insert_row(rec["device_id"], rec["value"], rec["ts_server"], rec["ts_client"])

        # log without id
        print(f"[INGEST] value={m.value}, ts_server={ts_server}")

        # respond with the single sensor value only (plain number)
        return m.value


@app.get("/latest")
def latest(device_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT device_id, value, ts_server, ts_client
        FROM measurements
        WHERE device_id = ?
        ORDER BY id DESC
        LIMIT 1
    """, (device_id,))
    row = c.fetchone()
    conn.close()

    if row:
        return {
            "device_id": row[0],
            "value": row[1],
            "ts_server": row[2],
            "ts_client": row[3]
        }
    raise HTTPException(404, f"No data for device_id={device_id}")

@app.get("/all")
def all_records(device_id: Optional[str] = None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    if device_id:
        c.execute("""
            SELECT device_id, value, ts_server, ts_client
            FROM measurements
            WHERE device_id = ?
            ORDER BY id DESC
        """, (device_id,))
    else:
        c.execute("""
            SELECT device_id, value, ts_server, ts_client
            FROM measurements
            ORDER BY id DESC
        """)

    rows = c.fetchall()
    conn.close()

    return [
        {
            "device_id": r[0],
            "value": r[1],
            "ts_server": r[2],
            "ts_client": r[3]
        }
        for r in rows
    ]
