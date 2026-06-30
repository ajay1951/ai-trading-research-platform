import sqlite3
import os
import threading
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

@dataclass
class Order:
    id: int
    symbol: str
    side: str
    total_qty: float
    filled_qty: float
    status: str
    created_at: str

class OrderManagementSystem:
    """
    Durable Order Management System backed by SQLite.
    Tracks order lifecycles (Pending, Partial, Filled, Canceled).
    """
    def __init__(self, db_path: str = "oms.db"):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self, '_local'):
            self._local = threading.local()
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            total_qty REAL NOT NULL,
            filled_qty REAL DEFAULT 0.0,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS executions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            fill_price REAL NOT NULL,
            fill_qty REAL NOT NULL,
            fee REAL DEFAULT 0.0,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id)
        )
        ''')
        
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tca_metrics (
            order_id INTEGER PRIMARY KEY,
            arrival_price REAL,
            slippage_bps REAL,
            market_impact REAL,
            FOREIGN KEY(order_id) REFERENCES orders(id)
        )
        ''')
        
        conn.commit()

    def create_order(self, symbol: str, side: str, total_qty: float) -> int:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        cursor.execute('''
            INSERT INTO orders (symbol, side, total_qty, status, created_at, updated_at)
            VALUES (?, ?, ?, 'PENDING', ?, ?)
        ''', (symbol, side, total_qty, now, now))
        conn.commit()
        return cursor.lastrowid

    def execute_order(self, order_id: int, fill_price: float, fill_qty: float, fee: float = 0.0) -> str:
        conn = self._get_conn()
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        # Insert execution
        cursor.execute('''
            INSERT INTO executions (order_id, fill_price, fill_qty, fee, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (order_id, fill_price, fill_qty, fee, now))
        
        # Update order status
        cursor.execute('SELECT total_qty, filled_qty FROM orders WHERE id = ?', (order_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"Order {order_id} not found")
            
        total_qty = row['total_qty']
        new_filled_qty = row['filled_qty'] + fill_qty
        
        if new_filled_qty >= total_qty:
            status = 'FILLED'
        else:
            status = 'PARTIAL'
            
        cursor.execute('''
            UPDATE orders
            SET filled_qty = ?, status = ?, updated_at = ?
            WHERE id = ?
        ''', (new_filled_qty, status, now, order_id))
        
        conn.commit()
        return status

    def get_order(self, order_id: int) -> Optional[Order]:
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM orders WHERE id = ?', (order_id,))
        row = cursor.fetchone()
        if row:
            return Order(
                id=row['id'],
                symbol=row['symbol'],
                side=row['side'],
                total_qty=row['total_qty'],
                filled_qty=row['filled_qty'],
                status=row['status'],
                created_at=row['created_at']
            )
        return None

# Global OMS Instance
oms = OrderManagementSystem()
