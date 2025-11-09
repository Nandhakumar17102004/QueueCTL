import logging
import os
from pathlib import Path
from datetime import datetime

class QueueLogger:
    
    def __init__(self, log_path: str = "logs/queuectl.log"):
        self.log_path = log_path
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.logger = logging.getLogger('queuectl')
        self.logger.setLevel(logging.INFO)
        
        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(logging.INFO)
        
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)
    
    def info(self, message: str):
        """Log info message."""
        self.logger.info(message)
    
    def error(self, message: str):
        """Log error message."""
        self.logger.error(message)
    
    def warning(self, message: str):
        """Log warning message."""
        self.logger.warning(message)
    
    def log_job_event(self, job_id: str, state: str, details: str = ""):
        """Log job state change."""
        self.info(f"job={job_id} state={state} {details}")
    
    def log_execution(self, job_id: str, duration: float, success: bool, output: str = ""):
        """Log job execution result with proper encoding handling."""
        status = "success" if success else "failure"
        
        if output:
            try:
                clean_output = output.encode('ascii', 'replace').decode('ascii')
            except:
                clean_output = "[Output contains non-ASCII characters]"
        else:
            clean_output = ""
        

        self.info(f"job={job_id} execution={status} duration={duration:.2f}s output={clean_output[:100]}")
