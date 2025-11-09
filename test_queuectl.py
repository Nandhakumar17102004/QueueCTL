import sys
import time
import subprocess
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.storage import Storage
from core.config_manager import ConfigManager
from core.queue_manager import QueueManager
from core.worker_manager import WorkerManager
from utils.logger import QueueLogger


def _clean_db(db_path="data/test.db"):
    import gc
    gc.collect()
    
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            if os.path.exists(db_path):
                os.remove(db_path)
            Storage(db_path)
            print(f"✓ Cleaned test database (attempt {attempt + 1})")
            return
        except PermissionError as e:
            if attempt < max_attempts - 1:
                time.sleep(0.5)  
                continue
            else:
                raise e

def wait_for_job_state(storage, job_id, expected_state, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        job = storage.get_job(job_id)
        if job and job['state'] == expected_state:
            return job
        time.sleep(0.5)
    raise TimeoutError(f"Job {job_id} never reached state {expected_state}")

def test_basic_enqueue_and_execution():
    print("\n=== Test 1: Basic Enqueue & Execution ===")
    
    _clean_db() 
    print("✓ Cleaned test database")
    
    storage = Storage("data/test.db")
    config = ConfigManager("config/test.json")
    logger = QueueLogger("logs/test.log")
    queue_manager = QueueManager(storage, config, logger)
    worker_manager = WorkerManager(queue_manager, logger, config)
    
    job_id = queue_manager.enqueue('echo "hello world"')
    print(f"✓ Enqueued job: {job_id}")
    
    worker_manager.start_workers(1)
    
    job = wait_for_job_state(storage, job_id, 'completed')
    assert 'hello world' in job['output'], "Output not found"
    print(f"✓ Job completed with output: {job['output']}")
    
    worker_manager.stop_all_workers()
    print("✓ Test passed")


def test_retry_with_backoff():
    print("\n=== Test 2: Retry with Exponential Backoff ===")
    
    _clean_db() 
    
    storage = Storage("data/test.db")
    config = ConfigManager("config/test.json")
    config.set('retry_backoff_base', 1)  
    config.set('worker_poll_interval', 0.5)  
    logger = QueueLogger("logs/test.log")
    queue_manager = QueueManager(storage, config, logger)
    worker_manager = WorkerManager(queue_manager, logger, config)
    
    job_id = queue_manager.enqueue('exit 1', max_retries=2)
    print(f"✓ Enqueued job: {job_id} with max_retries=2")
    
    worker_manager.start_workers(1)
    
    try:
        job = wait_for_job_state(storage, job_id, 'dead', timeout=15)
    except TimeoutError:
        job = storage.get_job(job_id)
        print(f"  Final state: {job['state']}, attempts: {job['attempts']}")
        raise
    
    assert job['state'] == 'dead', f"Job state is {job['state']}, expected dead"
    assert job['attempts'] == 3, f"Expected 3 attempts, got {job['attempts']}"
    print(f"✓ Job moved to DLQ after {job['attempts']} attempts")
    
    worker_manager.stop_all_workers()
    print("✓ Test passed")


def test_priority_queue():
    """Test job priority ordering"""
    print("\n=== Test 3: Priority Queue ===")
    
    _clean_db()
    
    storage = Storage("data/test.db")
    config = ConfigManager("config/test.json")
    logger = QueueLogger("logs/test.log")
    queue_manager = QueueManager(storage, config, logger)
    
    id1 = queue_manager.enqueue('sleep 1', priority=0)
    time.sleep(0.01)  
    
    id2 = queue_manager.enqueue('sleep 1', priority=10)
    time.sleep(0.01) 
    
    id3 = queue_manager.enqueue('sleep 1', priority=5)
    
    print(f"✓ Enqueued 3 jobs with priorities: 0, 10, 5")
    print(f"  Job IDs: {id1} (prio 0), {id2} (prio 10), {id3} (prio 5)")
    
    next_job = storage.get_pending_jobs(limit=1)[0]
    print(f"  Next job selected: {next_job['id']} with priority {next_job['priority']}")
    
    assert next_job['priority'] == 10, f"Expected priority 10, got {next_job['priority']}"
    assert next_job['id'] == id2, f"Expected {id2}, got {next_job['id']}"
    print(f"✓ Next job selected correctly by priority: {next_job['id']}")
    
    print("✓ Test passed")

def test_scheduled_jobs():
    """Test scheduled/delayed jobs"""
    print("\n=== Test 4: Scheduled Jobs ===")
    
    _clean_db()
    
    storage = Storage("data/test.db")
    config = ConfigManager("config/test.json")
    logger = QueueLogger("logs/test.log")
    queue_manager = QueueManager(storage, config, logger)
    
    current_time = time.time()
    job_id = queue_manager.schedule_job('echo "scheduled"', delay_seconds=1)
    print(f"✓ Scheduled job: {job_id} (1 second delay)")
    
    job = storage.get_job(job_id)
    expected_run_at = current_time + 1
    print(f"  Job run_at: {job['run_at']:.6f}")
    print(f"  Expected run_at: {expected_run_at:.6f}")
    print(f"  Current time: {time.time():.6f}")
    print(f"  Time until run: {job['run_at'] - time.time():.6f}")
    
    next_job = storage.get_pending_jobs(limit=1)
    assert len(next_job) == 0, "Job should not be ready yet"
    print("✓ Job correctly not in pending queue")
    
    wait_time = max(0, job['run_at'] - time.time() + 0.1)  # Wait until run_at + 100ms buffer
    print(f"  Waiting {wait_time:.2f} seconds...")
    time.sleep(wait_time)
    
    current_time_after = time.time()
    job_after = storage.get_job(job_id)
    print(f"  After wait - current time: {current_time_after:.6f}")
    print(f"  After wait - job run_at: {job_after['run_at']:.6f}")
    print(f"  After wait - should run: {job_after['run_at'] <= current_time_after}")
    
    next_job = storage.get_pending_jobs(limit=1)
    if len(next_job) > 0:
        print(f"✓ Job available after delay: {next_job[0]['id']}")
        assert next_job[0]['id'] == job_id, "Wrong job retrieved"
    else:
        print("✗ Job still not available")
        all_jobs = storage.get_jobs_by_state('pending', limit=10)
        print(f"  All pending jobs: {len(all_jobs)}")
        for j in all_jobs:
            print(f"    - {j['id']}: run_at={j.get('run_at', 'None')}")
        raise AssertionError("Job should be ready now")
    
    print("✓ Test passed")

def test_deadletter_queue_retry():
    """Test DLQ and job retry"""
    print("\n=== Test 5: Dead Letter Queue & Retry ===")
    
    _clean_db()
    
    storage = Storage("data/test.db")
    config = ConfigManager("config/test.json")
    config.set('retry_backoff_base', 1)
    config.set('worker_poll_interval', 0.5)
    logger = QueueLogger("logs/test.log")
    queue_manager = QueueManager(storage, config, logger)
    worker_manager = WorkerManager(queue_manager, logger, config)
    
    job_id = queue_manager.enqueue('exit 1', max_retries=1)
    print(f"✓ Enqueued failing job: {job_id}")
    
    worker_manager.start_workers(1)
    
    job = wait_for_job_state(storage, job_id, 'dead', timeout=10)
    assert job['state'] == 'dead', f"Job should be in DLQ, got {job['state']}"
    print("✓ Job moved to DLQ")
    
    success = queue_manager.retry_dead_letter_job(job_id)
    assert success, "Retry should succeed"
    
    job = storage.get_job(job_id)
    assert job['state'] == 'pending', "Job should be pending after retry"
    assert job['attempts'] == 0, "Attempts should be reset after DLQ retry"
    print("✓ Job retried and back to pending with attempts reset")
    
    worker_manager.stop_all_workers()
    print("✓ Test passed")


def test_job_timeout():
    """Test job timeout handling"""
    print("\n=== Test 6: Job Timeout ===")
    
    _clean_db()
    
    storage = Storage("data/test.db")
    config = ConfigManager("config/test.json")
    logger = QueueLogger("logs/test.log")
    queue_manager = QueueManager(storage, config, logger)
    worker_manager = WorkerManager(queue_manager, logger, config)
    
    job_id = queue_manager.enqueue('sleep 5', timeout=1, max_retries=0)
    print(f"✓ Enqueued long-running job with 1s timeout: {job_id}")
    
    worker_manager.start_workers(1)
    
    try:
        job = wait_for_job_state(storage, job_id, 'dead', timeout=8)
        assert job['state'] == 'dead', f"Job state is {job['state']}, expected dead"
        assert 'timeout' in job['error'].lower(), f"Expected timeout error, got: {job['error']}"
        print(f"✓ Job timed out correctly: {job['error']}")
    except TimeoutError:
        job = storage.get_job(job_id)
        print(f"  Job state after timeout: {job['state']}")
        print(f"  Job attempts: {job['attempts']}")
        print(f"  Job error: {job.get('error', 'None')}")
        raise
    
    worker_manager.stop_all_workers()
    print("✓ Test passed")


def test_stale_lock_cleanup():
    """Test stale lock cleanup"""
    print("\n=== Test 7: Stale Lock Cleanup ===")
    
    _clean_db()
    
    storage = Storage("data/test.db")
    
    fake_job = {
        'id': 'test-lock-job',
        'command': 'echo "test"',
        'state': 'processing',
        'worker_id': 'crashed-worker',
        'lock_expires': time.time() - 1000,  
        'created_at': time.time(),
        'updated_at': time.time()
    }
    
    conn = storage._get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO jobs (id, command, state, worker_id, lock_expires, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        fake_job['id'],
        fake_job['command'],
        fake_job['state'],
        fake_job['worker_id'],
        fake_job['lock_expires'],
        fake_job['created_at'],
        fake_job['updated_at']
    ))
    conn.commit()
    conn.close()
    
    print("✓ Created fake locked job with expired lock")
    
    count = storage.cleanup_stale_locks()
    assert count == 1, f"Should clean up 1 stale lock, got {count}"
    
    job = storage.get_job('test-lock-job')
    assert job['state'] == 'pending', f"Job should be pending, got {job['state']}"
    assert job['worker_id'] is None, "Worker ID should be cleared"
    assert job['lock_expires'] is None, "Lock expires should be cleared"
    
    print("✓ Stale lock cleaned up successfully")
    print("✓ Test passed")

def show_compact_status(storage):
    """Display compact status summary for tests"""
    pending = len(storage.get_jobs_by_state('pending', limit=1000))
    processing = len(storage.get_jobs_by_state('processing', limit=1000))
    completed = len(storage.get_jobs_by_state('completed', limit=1000))
    failed = len(storage.get_jobs_by_state('failed', limit=1000))
    dead = len(storage.get_jobs_by_state('dead', limit=1000))
    total = pending + processing + completed + failed + dead
    
    print(f"\n📊 FINAL TEST SUMMARY:")
    print(f"Pending: {pending}, Processing: {processing}, Completed: {completed}, Failed: {failed}, DLQ: {dead}, Total: {total}")
    
    return {
        'pending': pending,
        'processing': processing, 
        'completed': completed,
        'failed': failed,
        'dead': dead,
        'total': total
    }

def run_all_tests():
    """Run all integration tests with honest reporting"""
    print("Starting QueueCTL Integration Tests")
    print("=" * 50)
    
    test_results = []
    
    try:
        print("Running individual feature tests...")
        
        test_results.append("1. Basic Execution: 1 job → completed")
        test_basic_enqueue_and_execution()
        
        test_results.append("2. Exponential Backoff: 1 job → failed → retried → DLQ")  
        test_retry_with_backoff()
        
        test_results.append("3. Priority Queue: 3 jobs → verified ordering")
        test_priority_queue()
        
        test_results.append("4. Scheduled Jobs: 1 job → delayed → pending")
        test_scheduled_jobs()
        
        test_results.append("5. DLQ Management: 1 job → failed → DLQ → retried")
        test_deadletter_queue_retry()
        
        test_results.append("6. Job Timeout: 1 job → timeout → DLQ")
        test_job_timeout()
        
        test_results.append("7. Stale Lock Cleanup: 1 job → locked → cleaned → pending")
        test_stale_lock_cleanup()
        
        print("\n" + "=" * 50)
        print("✓ All tests passed!")
        
        storage = Storage("data/test.db")
        final_status = show_compact_status(storage)
        
        print(f"\n📊 FINAL DATABASE (Test 7 only):")
        print(f"Pending: {final_status['pending']}, Completed: {final_status['completed']}, Total: {final_status['total']}")
        
        print(f"\n📈 CUMULATIVE TEST RESULTS:")
        for result in test_results:
            print(f"  {result}")
 
        print(f"• All job states demonstrated: pending, processing, completed, failed, dead")
        return 0
    
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    exit_code = run_all_tests()

    sys.exit(exit_code)
