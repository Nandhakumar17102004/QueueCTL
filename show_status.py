import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from core.storage import Storage
from core.config_manager import ConfigManager

def show_compact_status():
    config = ConfigManager()
    storage = Storage(config.get('db_path'))
    
    pending = len(storage.get_jobs_by_state('pending', limit=1000))
    processing = len(storage.get_jobs_by_state('processing', limit=1000))
    completed = len(storage.get_jobs_by_state('completed', limit=1000))
    failed = len(storage.get_jobs_by_state('failed', limit=1000))
    dead = len(storage.get_jobs_by_state('dead', limit=1000))
    total = pending + processing + completed + failed + dead
    
    print(f"Pending: {pending}, Processing: {processing}, Completed: {completed}, Failed: {failed}, DLQ: {dead}, Total: {total}")

if __name__ == '__main__':

    show_compact_status()
