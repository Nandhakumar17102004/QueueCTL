"""
SQLite-based persistent storage for job queue system.
Handles all database operations with thread-safe locking.
"""

import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import threading
import time


class Storage:
    """Thread-safe SQLite storage for job persistence."""
    
    def __init__(self, db_path: str = "data/queuectl.db"):
        self.db_path = db_path
        self.lock = threading.RLock()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _get_connection(self):
        """Get database connection with timeout and ensure it's properly closed."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """Initialize database schema."""
        with self.lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                
                # Jobs table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS jobs (
                        id TEXT PRIMARY KEY,
                        command TEXT NOT NULL,
                        state TEXT NOT NULL DEFAULT 'pending',
                        priority INTEGER DEFAULT 0,
                        run_at REAL,
                        attempts INTEGER DEFAULT 0,
                        max_retries INTEGER DEFAULT 3,
                        timeout INTEGER DEFAULT 300,
                        output TEXT,
                        error TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        completed_at REAL,
                        worker_id TEXT,
                        lock_token TEXT,
                        lock_expires REAL
                    )
                """)
                
                # Metrics table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        metric_type TEXT NOT NULL,
                        value REAL NOT NULL,
                        timestamp REAL NOT NULL
                    )
                """)
                
                # Create indexes for performance
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_state ON jobs(state)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_priority ON jobs(priority DESC)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_run_at ON jobs(run_at)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_worker ON jobs(worker_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_lock_expires ON jobs(lock_expires)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_updated_at ON jobs(updated_at)")
                
                conn.commit()
            finally:
                conn.close()
    
    def enqueue_job(self, job: Dict[str, Any]) -> bool:
        """Add job to database."""
        with self.lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO jobs (
                        id, command, state, priority, run_at, max_retries,
                        timeout, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job['id'],
                    job['command'],
                    'pending',
                    job.get('priority', 0),
                    job.get('run_at'),
                    job.get('max_retries', 3),
                    job.get('timeout', 300),
                    job['created_at'],
                    job['updated_at']
                ))
                
                conn.commit()
                return True
            except Exception as e:
                print(f"Error enqueueing job: {e}")
                return False
            finally:
                conn.close()
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Retrieve job by ID."""
        with self.lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
    
    def get_and_lock_next_job(self, worker_id: str, lock_duration: int = 60) -> Optional[Dict]:
        """
        Atomically finds and locks the next pending job in a single operation.
        FIXED: No race condition between SELECT and UPDATE.
        """
        with self.lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                now = datetime.now().timestamp()
                expires = now + lock_duration
                
                # Single atomic operation to find AND lock the next job
                cursor.execute("""
                    UPDATE jobs 
                    SET worker_id = ?, lock_token = ?, lock_expires = ?, 
                        state = 'processing', updated_at = ?
                    WHERE id = (
                        SELECT id FROM jobs 
                        WHERE state = 'pending' 
                        AND (run_at IS NULL OR run_at <= ?)
                        ORDER BY priority DESC, created_at ASC 
                        LIMIT 1
                    )
                    RETURNING *
                """, (worker_id, worker_id, expires, now, now))
                
                row = cursor.fetchone()
                conn.commit()
                
                if row:
                    return dict(row)
                else:
                    return None
                    
            except Exception as e:
                print(f"Error getting and locking job: {e}")
                return None
            finally:
                conn.close()
    
    def cleanup_stale_locks(self, timeout_seconds: int = 300) -> int:
        """Release locks from crashed workers. Returns number of jobs unlocked."""
        with self.lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cutoff = datetime.now().timestamp() - timeout_seconds
                
                cursor.execute("""
                    UPDATE jobs 
                    SET state = 'pending', worker_id = NULL, 
                        lock_token = NULL, lock_expires = NULL
                    WHERE state = 'processing' 
                    AND lock_expires < ?
                """, (cutoff,))
                
                count = cursor.rowcount
                conn.commit()
                return count
            except Exception as e:
                print(f"Error cleaning stale locks: {e}")
                return 0
            finally:
                conn.close()
    
    def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update job state and attributes."""
        with self.lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                
                updates['updated_at'] = datetime.now().timestamp()
                
                set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
                values = list(updates.values()) + [job_id]
                
                cursor.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
                conn.commit()
                success = cursor.rowcount > 0
                return success
            except Exception as e:
                print(f"Error updating job: {e}")
                return False
            finally:
                conn.close()
    
    def get_pending_jobs(self, limit: int = 10) -> List[Dict]:
        """Get next batch of pending jobs ordered by priority and run_at."""
        with self.lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                now = datetime.now().timestamp()
                
                cursor.execute("""
                    SELECT * FROM jobs 
                    WHERE state = 'pending' 
                    AND (run_at IS NULL OR run_at <= ?)
                    ORDER BY priority DESC, created_at ASC
                    LIMIT ?
                """, (now, limit))
                
                jobs = [dict(row) for row in cursor.fetchall()]
                return jobs
            finally:
                conn.close()
    
    def get_failed_jobs(self, limit: int = 100) -> List[Dict]:
        """Get failed jobs (DLQ)."""
        with self.lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM jobs WHERE state = 'dead'
                    ORDER BY updated_at DESC LIMIT ?
                """, (limit,))
                jobs = [dict(row) for row in cursor.fetchall()]
                return jobs
            finally:
                conn.close()
    
    def get_jobs_by_state(self, state: str, limit: int = 100) -> List[Dict]:
        """Get jobs by state."""
        with self.lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM jobs WHERE state = ?
                    ORDER BY updated_at DESC LIMIT ?
                """, (state, limit))
                jobs = [dict(row) for row in cursor.fetchall()]
                return jobs
            finally:
                conn.close()
    
    def record_metric(self, metric_type: str, value: float) -> bool:
        """Record a metric for monitoring."""
        with self.lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO metrics (metric_type, value, timestamp)
                    VALUES (?, ?, ?)
                """, (metric_type, value, datetime.now().timestamp()))
                conn.commit()
                return True
            except Exception:
                return False
            finally:
                conn.close()
    
    def get_metrics(self, metric_type: str, seconds: int = 3600) -> List[Dict]:
        """Get metrics from last N seconds."""
        with self.lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cutoff = datetime.now().timestamp() - seconds
                
                cursor.execute("""
                    SELECT * FROM metrics 
                    WHERE metric_type = ? AND timestamp > ?
                    ORDER BY timestamp DESC
                """, (metric_type, cutoff))
                
                metrics = [dict(row) for row in cursor.fetchall()]
                return metrics
            finally:
                conn.close()