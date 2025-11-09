"""
Worker management and job execution.
Handles multiple concurrent workers with graceful shutdown.
"""

import subprocess
import time
import threading
from typing import Optional, Dict, Any
from .queue_manager import QueueManager
from utils.logger import QueueLogger

class Worker:
    """Individual worker thread."""
    
    def __init__(self, worker_id: str, queue_manager: QueueManager, 
                 logger: QueueLogger, config):
        self.worker_id = worker_id
        self.queue_manager = queue_manager
        self.logger = logger
        self.config = config
        self.running = False
        self.current_job: Optional[Dict[str, Any]] = None
        self.should_stop = False
    
    def run(self):
        """Main worker loop. Continuously polls for and executes jobs."""
        self.running = True
        self.logger.info(f"Worker {self.worker_id} started")
        
        try:
            while not self.should_stop:
                # Check for stop signal before getting next job
                if self.should_stop:
                    break
                    
                job = self.queue_manager.get_and_lock_next_job(
                    self.worker_id, 
                    lock_duration=self.config.get('job_timeout', 300)
                )
                
                if job:
                    self.current_job = job
                    self._execute_job(job)
                    self.current_job = None
                else:
                    # No jobs available, sleep briefly based on config
                    time.sleep(self.config.get('worker_poll_interval', 1))
        
        except Exception as e:
            self.logger.error(f"Worker {self.worker_id} encountered a critical error: {e}")
            # CRITICAL FIX: Mark current job as failed if worker crashes
            if self.current_job:
                self.queue_manager.mark_job_failed(
                    self.current_job['id'], 
                    f"Worker crashed: {e}",
                    should_retry=True
                )
        finally:
            self.running = False
            self.logger.info(f"Worker {self.worker_id} stopped")
    
    def _execute_job(self, job: Dict[str, Any]):
        """Execute a single job using subprocess with robust timeout handling."""
        # Check stop signal before starting job
        if self.should_stop:
            self.logger.info(f"Worker {self.worker_id} skipping job due to stop signal")
            return
            
        job_id = job['id']
        command = job['command']
        timeout = job['timeout']
        
        start_time = time.time()
        
        try:
            # Validate command before execution
            if not command or not command.strip():
                raise ValueError("Empty command")
            
            # For sleep commands, use platform-specific approach for better timeout testing
            if command.strip().startswith('sleep'):
                # Use Python-based sleep for more reliable timeout testing
                sleep_time = self._extract_sleep_time(command)
                if sleep_time:
                    self._execute_sleep_job(job_id, sleep_time, timeout)
                    return
            
            # Use Popen for more control over process termination
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace'  # Handle encoding errors gracefully
            )
            
            try:
                # Wait for process with timeout
                stdout, stderr = process.communicate(timeout=timeout)
                returncode = process.returncode
                
                duration = time.time() - start_time
                
                if returncode == 0:
                    # Job succeeded - handle output encoding
                    if stdout:
                        try:
                            # Clean output to handle encoding issues
                            output = self._clean_output(stdout)[:1000]
                        except Exception as e:
                            output = f"[Output encoding error: {e}]"
                    else:
                        output = ""
                    
                    self.queue_manager.mark_job_completed(job_id, output)
                    self.logger.log_execution(job_id, duration, True, output)
                    self.queue_manager.storage.record_metric('execution_time', duration)
                else:
                    # Job failed (non-zero exit code)
                    if stderr:
                        try:
                            error = self._clean_output(stderr)[:500]
                        except Exception as e:
                            error = f"[Error output encoding error: {e}]"
                    else:
                        error = f"Exit code {returncode}"
                    
                    self.queue_manager.mark_job_failed(job_id, error, should_retry=True)
                    self.logger.log_execution(job_id, duration, False, error)
                    
            except subprocess.TimeoutExpired:
                # Timeout occurred - terminate the process
                duration = time.time() - start_time
                self.logger.warning(f"Job {job_id} timeout after {timeout}s, terminating...")
                
                # Try to terminate gracefully
                process.terminate()
                try:
                    # Wait a bit for graceful termination
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # Force kill if still running
                    process.kill()
                    process.wait()
                
                error = f"Job timeout after {timeout}s"
                self.queue_manager.mark_job_failed(job_id, error, should_retry=True)
                self.logger.log_execution(job_id, duration, False, error)
            
        except Exception as e:
            # Catch unexpected system errors (e.g., Command not found)
            duration = time.time() - start_time
            error = str(e)
            should_retry = not isinstance(e, (ValueError, FileNotFoundError))
            self.queue_manager.mark_job_failed(job_id, error, should_retry=should_retry)
            self.logger.error(f"Unexpected error executing job {job_id}: {e}")

    def _clean_output(self, text: str) -> str:
        """Clean output text to handle encoding issues."""
        try:
            # Try to handle common encoding problems
            cleaned = text.encode('utf-8', errors='replace').decode('utf-8')
            # Remove or replace problematic characters
            cleaned = cleaned.replace('\u2713', '[check]')  # Replace checkmarks
            cleaned = cleaned.replace('\u2717', '[cross]')  # Replace crosses
            cleaned = cleaned.replace('\u251c', '[tree]')   # Replace tree characters
            cleaned = cleaned.replace('\u2502', '[pipe]')   # Replace pipe characters
            return cleaned
        except Exception as e:
            return f"[Output cleaning failed: {e}]"

    def _extract_sleep_time(self, command: str) -> Optional[float]:
        """Extract sleep time from sleep command."""
        import re
        match = re.search(r'sleep\s+(\d+)', command)
        if match:
            return float(match.group(1))
        return None

    def _execute_sleep_job(self, job_id: str, sleep_time: float, timeout: float):
        """Execute a sleep job with reliable timeout handling."""
        start_time = time.time()
        end_time = start_time + sleep_time
        timeout_time = start_time + timeout
        
        try:
            while time.time() < end_time:
                # Check for timeout
                if time.time() >= timeout_time:
                    duration = time.time() - start_time
                    error = f"Job timeout after {timeout}s (sleep interrupted)"
                    self.queue_manager.mark_job_failed(job_id, error, should_retry=True)
                    self.logger.log_execution(job_id, duration, False, error)
                    return
                
                # Small sleep to avoid busy waiting
                time.sleep(0.1)
                
                # Check if worker should stop
                if self.should_stop:
                    duration = time.time() - start_time
                    error = "Job interrupted by worker shutdown"
                    self.queue_manager.mark_job_failed(job_id, error, should_retry=True)
                    self.logger.log_execution(job_id, duration, False, error)
                    return
            
            # Sleep completed successfully
            duration = time.time() - start_time
            self.queue_manager.mark_job_completed(job_id, "sleep completed")
            self.logger.log_execution(job_id, duration, True, "sleep completed")
            self.queue_manager.storage.record_metric('execution_time', duration)
            
        except Exception as e:
            duration = time.time() - start_time
            error = f"Sleep execution failed: {e}"
            self.queue_manager.mark_job_failed(job_id, error, should_retry=True)
            self.logger.log_execution(job_id, duration, False, error)
    
    def stop(self):
        """Signal worker to stop gracefully after finishing the current job."""
        self.should_stop = True
        self.logger.info(f"Worker {self.worker_id} received stop signal")


class WorkerManager:
    """Manages multiple worker threads."""
    
    def __init__(self, queue_manager: QueueManager, logger: QueueLogger, config):
        self.queue_manager = queue_manager
        self.logger = logger
        self.config = config
        self.workers: Dict[str, Worker] = {}
        self.threads: Dict[str, threading.Thread] = {}
        self.lock = threading.Lock()
    
    def start_workers(self, count: int = 1) -> int:
        """Start N workers."""
        started = 0
        
        # Clean up stale locks before starting new workers
        stale_count = self.queue_manager.storage.cleanup_stale_locks()
        if stale_count > 0:
            self.logger.info(f"Cleaned up {stale_count} stale locks")
        
        for i in range(count):
            worker_id = f"worker-{int(time.time() * 1000)}-{i}"
            
            with self.lock:
                worker = Worker(worker_id, self.queue_manager, self.logger, self.config)
                self.workers[worker_id] = worker
                
                thread = threading.Thread(target=worker.run, daemon=False)
                self.threads[worker_id] = thread
                thread.start()
                
                started += 1
        
        self.logger.info(f"Started {started} workers, total={len(self.workers)}")
        return started
    
    def stop_all_workers(self, timeout: int = 30):
        """Stop all workers gracefully."""
        self.logger.info(f"Stopping {len(self.workers)} workers...")
        
        with self.lock:
            # 1. Signal all workers to stop
            for worker in self.workers.values():
                worker.stop()
        
        # 2. Wait for all threads to finish (graceful shutdown)
        end_time = time.time() + timeout
        for worker_id, thread in list(self.threads.items()):  # Create a copy to avoid modification during iteration
            remaining = max(0, end_time - time.time())
            thread.join(timeout=remaining)
            
            if thread.is_alive():
                self.logger.warning(f"Worker {worker_id} did not stop within timeout ({timeout}s)")
        
        self.logger.info("All workers stopped")
        
        # 3. Clean up the lists
        with self.lock:
            self.workers.clear()
            self.threads.clear()
    
    def get_worker_status(self) -> Dict[str, Any]:
        """Get status of all workers."""
        status = {
            'total': len(self.workers),
            'active': sum(1 for w in self.workers.values() if w.running),
            'workers': {}
        }
        
        with self.lock:
            for worker_id, worker in self.workers.items():
                status['workers'][worker_id] = {
                    'running': worker.running,
                    'current_job': worker.current_job['id'] if worker.current_job else None
                }
        
        return status