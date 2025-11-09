"""
CLI interface for QueueCTL job queue system.
Handles all user commands: enqueue, worker, status, dlq, config, etc.
"""

import sys
import click
import json
import signal
import time
from tabulate import tabulate
from datetime import datetime
from core.storage import Storage
from core.config_manager import ConfigManager
from core.queue_manager import QueueManager
from core.worker_manager import WorkerManager
from utils.logger import QueueLogger


# Global instances
config = ConfigManager()
storage = Storage(config.get('db_path'))
logger = QueueLogger(config.get('log_path'))
queue_manager = QueueManager(storage, config, logger)
worker_manager = WorkerManager(queue_manager, logger, config)

# Handle graceful shutdown
def signal_handler(sig, frame):
    click.echo("\nShutting down...")
    worker_manager.stop_all_workers()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)


@click.group()
def cli():
    """QueueCTL - Background Job Queue System"""
    pass


@cli.command()
@click.option('--job', '-j', required=True, help='Job command to execute')
@click.option('--priority', '-p', type=int, default=0, help='Job priority (higher = sooner)')
@click.option('--delay', '-d', type=int, help='Delay in seconds before running')
@click.option('--max-retries', '-r', type=int, help='Max retries on failure')
@click.option('--timeout', '-t', type=int, help='Job timeout in seconds')
def enqueue(job, priority, delay, max_retries, timeout):
    """Enqueue a new job"""
    try:
        if delay:
            job_id = queue_manager.schedule_job(
                job, 
                delay_seconds=delay,
                priority=priority,
                max_retries=max_retries,
                timeout=timeout
            )
            run_at = datetime.fromtimestamp(
                datetime.now().timestamp() + delay
            ).strftime('%Y-%m-%d %H:%M:%S')
            click.echo(f"Job scheduled: {job_id} (will run at {run_at})")
        else:
            job_id = queue_manager.enqueue(
                job,
                priority=priority,
                max_retries=max_retries,
                timeout=timeout
            )
            click.echo(f"Job enqueued: {job_id}")
    except ValueError as e:
        click.echo(f"Validation error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error enqueueing job: {e}", err=True)
        sys.exit(1)


@cli.group()
def worker():
    """Worker management commands"""
    pass


@worker.command()
@click.option('--count', '-c', type=int, default=1, help='Number of workers')
def start(count):
    """Start worker(s)"""
    if count <= 0:
        click.echo("Worker count must be positive", err=True)
        sys.exit(1)
        
    try:
        worker_manager.start_workers(count)
        click.echo(f"Started {count} workers. Press Ctrl+C to stop.")
        
        # Clean up stale locks on startup
        stale_count = storage.cleanup_stale_locks()
        if stale_count > 0:
            click.echo(f"Cleaned up {stale_count} stale job locks")
        
        # Keep running until interrupted
        try:
            # signal.pause is not available on Windows; sleep in a loop instead
            while True:
                time.sleep(1)  # Use sleep instead of signal.pause on Windows
        except KeyboardInterrupt:
            click.echo("\nShutting down workers...")
            worker_manager.stop_all_workers()
            
    except Exception as e:
        click.echo(f"Error starting workers: {e}", err=True)
        sys.exit(1)


@worker.command()
def stop():
    """Stop all workers gracefully"""
    try:
        worker_manager.stop_all_workers()
        click.echo("All workers stopped")
    except Exception as e:
        click.echo(f"Error stopping workers: {e}", err=True)
        sys.exit(1)


@cli.command()
def status():
    """Show system status"""
    try:
        metrics = queue_manager.get_metrics_summary()
        worker_status = worker_manager.get_worker_status()
        
        # Job metrics table
        job_data = [
            ['Pending', metrics['pending']],
            ['Processing', metrics['processing']],
            ['Completed', metrics['completed']],
            ['Failed', metrics['failed']],
            ['Dead Letter Queue', metrics['dead']],
            ['Total', metrics['total']]
        ]
        
        click.echo("\n=== Job Queue Status ===")
        click.echo(tabulate(job_data, headers=['State', 'Count'], tablefmt='grid'))
        
        # Worker status table
        worker_data = []
        for worker_id, info in worker_status['workers'].items():
            current_job = info['current_job'] or '(idle)'
            status = "Running" if info['running'] else "Stopped"
            worker_data.append([worker_id, status, current_job])
        
        click.echo("\n=== Worker Status ===")
        if worker_data:
            click.echo(tabulate(
                worker_data,
                headers=['Worker ID', 'Status', 'Current Job'],
                tablefmt='grid'
            ))
        else:
            click.echo("No workers running")
        
        click.echo(f"\n{worker_status['active']}/{worker_status['total']} workers active")
        
    except Exception as e:
        click.echo(f"Error getting status: {e}", err=True)
        sys.exit(1)


@cli.group()
def list_jobs():
    """List jobs by state"""
    pass


@list_jobs.command()
@click.option('--limit', '-l', type=int, default=20, help='Limit results')
def pending(limit):
    """List pending jobs"""
    try:
        jobs = storage.get_jobs_by_state('pending', limit=limit)
        _display_jobs(jobs, "Pending Jobs")
    except Exception as e:
        click.echo(f"Error listing jobs: {e}", err=True)
        sys.exit(1)


@list_jobs.command()
@click.option('--limit', '-l', type=int, default=20, help='Limit results')
def completed(limit):
    """List completed jobs"""
    try:
        jobs = storage.get_jobs_by_state('completed', limit=limit)
        _display_jobs(jobs, "Completed Jobs")
    except Exception as e:
        click.echo(f"Error listing jobs: {e}", err=True)
        sys.exit(1)


@list_jobs.command()
@click.option('--limit', '-l', type=int, default=20, help='Limit results')
def failed(limit):
    """List failed jobs"""
    try:
        jobs = storage.get_jobs_by_state('failed', limit=limit)
        _display_jobs(jobs, "Failed Jobs")
    except Exception as e:
        click.echo(f"Error listing jobs: {e}", err=True)
        sys.exit(1)


@cli.group()
def dlq():
    """Dead Letter Queue management"""
    pass


@dlq.command()
@click.option('--limit', '-l', type=int, default=20, help='Limit results')
def list(limit):
    """List dead letter jobs"""
    try:
        jobs = storage.get_failed_jobs(limit=limit)
        _display_jobs(jobs, "Dead Letter Queue")
    except Exception as e:
        click.echo(f"Error listing DLQ: {e}", err=True)
        sys.exit(1)


@dlq.command()
@click.option('--job-id', '-j', required=True, help='Job ID to retry')
def retry(job_id):
    """Retry a dead letter job"""
    try:
        if queue_manager.retry_dead_letter_job(job_id):
            click.echo(f"Job {job_id} retried (moved to pending)")
        else:
            click.echo(f"Failed to retry job {job_id} - job not found or not in DLQ", err=True)
            sys.exit(1)
    except Exception as e:
        click.echo(f"Error retrying job: {e}", err=True)
        sys.exit(1)


@cli.group()
def config_cmd():
    """Configuration management"""
    pass


@config_cmd.command()
def show():
    """Show current configuration"""
    try:
        cfg = config.get_all()
        click.echo("\n=== Current Configuration ===")
        for key, value in cfg.items():
            click.echo(f"{key}: {value}")
    except Exception as e:
        click.echo(f"Error reading config: {e}", err=True)
        sys.exit(1)


@config_cmd.command()
@click.option('--key', '-k', required=True, help='Config key')
@click.option('--value', '-v', required=True, help='Config value')
def set(key, value):
    """Set configuration value"""
    try:
        # Try to parse as number
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass
        
        if config.set(key, value):
            click.echo(f"{key} = {value}")
        else:
            click.echo(f"Failed to set config", err=True)
            sys.exit(1)
    except ValueError as e:
        click.echo(f"Invalid config value: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error setting config: {e}", err=True)
        sys.exit(1)


@cli.command()
def cleanup():
    """Clean up stale job locks"""
    try:
        count = storage.cleanup_stale_locks()
        click.echo(f"Cleaned up {count} stale job locks")
    except Exception as e:
        click.echo(f"Error cleaning locks: {e}", err=True)
        sys.exit(1)


def _display_jobs(jobs: list, title: str):
    """Helper to display jobs in table format"""
    if not jobs:
        click.echo(f"No {title.lower()}")
        return
    
    click.echo(f"\n=== {title} ===")
    
    job_data = []
    for job in jobs:
        created = datetime.fromtimestamp(job['created_at']).strftime('%Y-%m-%d %H:%M:%S')
        job_data.append([
            job['id'][:8],
            job['command'][:50],
            job['state'],
            job['attempts'],
            created
        ])
    
    click.echo(tabulate(
        job_data,
        headers=['ID', 'Command', 'State', 'Attempts', 'Created'],
        tablefmt='grid'
    ))


if __name__ == '__main__':
    cli()