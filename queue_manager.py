"""
Main queue management logic.
Handles job lifecycle: pending -> processing -> completed/failed/dead
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import math
from .storage import Storage
from .config_manager import ConfigManager
from utils.logger import QueueLogger

class QueueManager:
    """Manages the job queue and lifecycle."""
    
    def __init__(self, storage: Storage, config: ConfigManager, logger: QueueLogger):
        self.storage = storage
        self.config = config
        self.logger = logger
    
    def enqueue(self, command: str, priority: int = 0, run_at: Optional[float] = None,
                max_retries: Optional[int] = None, timeout: Optional[int] = None) -> str:
        """Enqueue a new job with validation."""
        # Input validation
        if not command or not command.strip():
            raise ValueError("Command cannot be empty")
        
        if max_retries is not None and max_retries < 0:
            raise ValueError("max_retries must be >= 0")
            
        if timeout is not None and timeout <= 0:
            raise ValueError("timeout must be > 0")
        
        job_id = str(uuid.uuid4())[:8]
        now = datetime.now().timestamp()
        
        # Round the run_at timestamp for consistent SQL comparison
        if run_at is not None:
            run_at = round(run_at, 3)  
            
        job = {
            'id': job_id,
            'command': command.strip(),
            'priority': priority,
            'run_at': run_at,
            'max_retries': max_retries or self.config.get('max_retries', 3),
            'timeout': timeout or self.config.get('job_timeout', 300),
            'created_at': now,
            'updated_at': now
        }
        
        if self.storage.enqueue_job(job):
            self.logger.log_job_event(job_id, 'pending', f"command={command[:50]}")
            self.storage.record_metric('jobs_enqueued', 1)
            return job_id
        else:
            raise Exception("Failed to enqueue job")
    
    def schedule_job(self, command: str, delay_seconds: int, **kwargs) -> str:
        """Schedule a job to run after delay."""
        if delay_seconds < 0:
            raise ValueError("Delay cannot be negative")
            
        run_at = datetime.now().timestamp() + delay_seconds
        return self.enqueue(command, run_at=run_at, **kwargs)

    def get_and_lock_next_job(self, worker_id: str, lock_duration: int = 60) -> Optional[Dict]:
        """
        Atomically retrieves a pending job and sets its state to 'processing' (locking it).
        This method delegates the atomic logic to the Storage layer.
        """
        job = self.storage.get_and_lock_next_job(worker_id, lock_duration)
        
        if job:
            self.logger.log_job_event(job['id'], 'processing', f"worker={worker_id}")
            return job
        
        return None
    
    def mark_job_completed(self, job_id: str, output: str = "") -> bool:
        """Mark job as completed."""
        updates = {
            'state': 'completed',
            'completed_at': datetime.now().timestamp(),
            'output': output,
            'worker_id': None
        }
        
        success = self.storage.update_job(job_id, updates)
        if success:
            self.logger.log_job_event(job_id, 'completed', f"output={output[:100]}")
            self.storage.record_metric('jobs_completed', 1)
        return success
    
    def mark_job_failed(self, job_id: str, error: str = "", should_retry: bool = True) -> bool:
        """Mark job as failed and handle retry logic."""
        job = self.storage.get_job(job_id)
        if not job:
            return False
        
        attempts = job['attempts'] + 1
        max_retries = job['max_retries']
        
        # FIXED: Correct retry logic - attempts includes current failure
        if should_retry and attempts <= max_retries:
            # Calculate exponential backoff: base ^ (attempts) seconds
            base = self.config.get('retry_backoff_base', 2)
            delay = base ** attempts  # attempts starts from 1 for first retry
            run_at = datetime.now().timestamp() + delay
            
            # Keep job in 'pending' state with future run_at for retry
            updates = {
                'state': 'pending',
                'attempts': attempts,
                'error': error,
                'run_at': run_at,
                'worker_id': None
            }
            
            self.logger.log_job_event(
                job_id, 'failed', 
                f"attempt={attempts}/{max_retries}, retry_in={delay}s, error={error[:50]}"
            )
        else:
            # Move to dead letter queue
            updates = {
                'state': 'dead',
                'attempts': attempts,
                'error': error,
                'completed_at': datetime.now().timestamp(),
                'worker_id': None
            }
            
            self.logger.log_job_event(
                job_id, 'dead',
                f"max_retries_exhausted, final_error={error[:50]}"
            )
            self.storage.record_metric('jobs_dead', 1)
        
        success = self.storage.update_job(job_id, updates)
        self.storage.record_metric('jobs_failed', 1)
        return success
    
    def retry_dead_letter_job(self, job_id: str) -> bool:
        """Retry a job from the dead letter queue."""
        job = self.storage.get_job(job_id)
        if not job or job['state'] != 'dead':
            return False
        
        updates = {
            'state': 'pending',
            'attempts': 0,
            'error': None,
            'run_at': None,
            'worker_id': None
        }
        
        success = self.storage.update_job(job_id, updates)
        if success:
            self.logger.log_job_event(job_id, 'pending', "retried from DLQ")
        return success
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get system metrics summary."""
        pending = len(self.storage.get_jobs_by_state('pending', limit=1000))
        processing = len(self.storage.get_jobs_by_state('processing', limit=1000))
        completed = len(self.storage.get_jobs_by_state('completed', limit=1000))
        failed = len(self.storage.get_jobs_by_state('failed', limit=1000))
        dead = len(self.storage.get_jobs_by_state('dead', limit=1000))
        
        return {
            'pending': pending,
            'processing': processing,
            'completed': completed,
            'failed': failed,
            'dead': dead,
            'total': pending + processing + completed + failed + dead
        }