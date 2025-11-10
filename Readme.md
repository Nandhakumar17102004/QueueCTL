# QueueCTL 🚀

A CLI-based background job queue system built with Python. QueueCTL manages background jobs with worker processes, handles retries using exponential backoff, and maintains a Dead Letter Queue (DLQ) for permanently failed jobs.

> **Built for**: Backend Developer Internship Assignment  
> **Tech Stack**: Python 3.8+, SQLite, Click, Threading

---

## 📋 Table of Contents

- [Features]
- [QuickStart]
- [Installation]
- [Usage Examples]
- [Architecture]
- [CLI Commands]
- [Configuration]
- [Testing]
- [Why This Implementation is Reliable]
- [ProjectStructure]
- [DesignDecisions]
- [FutureEnhancements]

---

## ✨ Features

### Core Functionality
- ✅ **Job Enqueueing**: Add background jobs to the queue with custom commands
- ✅ **Multiple Workers**: Run multiple concurrent workers to process jobs in parallel
- ✅ **Priority Queue**: Higher priority jobs are processed first
- ✅ **Scheduled Jobs**: Delay job execution by seconds/minutes/hours
- ✅ **Automatic Retries**: Failed jobs retry automatically with exponential backoff
- ✅ **Dead Letter Queue (DLQ)**: Permanently failed jobs move to DLQ for manual inspection
- ✅ **Job Timeout**: Prevent runaway jobs with configurable timeouts
- ✅ **Persistent Storage**: Jobs survive system restarts using SQLite
- ✅ **Graceful Shutdown**: Workers finish current jobs before stopping
- ✅ **Real-time Status**: Monitor queue status and worker activity
- ✅ **Comprehensive Logging**: Track all job events and execution metrics

### Production-Ready Features
- 🔒 **Thread-safe Operations**: Safe concurrent access to job queue
- 🔄 **Duplicate Prevention**: Job locking prevents duplicate execution
- 📊 **Metrics Collection**: Track job counts, execution times, success rates
- ⚙️ **Configurable Settings**: Customize retry behavior, timeouts, backoff rates
- 🧪 **Fully Tested**: 7 comprehensive integration tests with 100% pass rate

---

## 🚀 Quick Start

### 1. Install Dependencies

pip install -r requirements.txt
```

### 2. Run Your First Job

# Enqueue a simple job
python cli.py enqueue --job "echo 'Hello QueueCTL!'"

# Start a worker to process it
python cli.py worker start --count 1

# Check the status
python cli.py status
```

That's it! Your first job is now running. 🎉

---

## 📦 Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Step 1: Clone or Download

# If you have the project files, navigate to the directory
cd queuectl
```

### Step 2: Install Dependencies

pip install click tabulate
```

### Step 3: Verify Installation

python cli.py --help
```

You should see the QueueCTL help menu with all available commands.

---

## 💡 Usage Examples

### Basic Job Execution

# Simple command
python cli.py enqueue --job "ls -la"

# Command with output
python cli.py enqueue --job "python myscript.py"

# Shell commands
python cli.py enqueue --job "echo 'Processing data...' && sleep 5"
```

### Priority Jobs

# Low priority (default: 0)
python cli.py enqueue --job "backup.sh" --priority 0

# High priority (processes first)
python cli.py enqueue --job "critical_task.py" --priority 10

# Medium priority
python cli.py enqueue --job "report.py" --priority 5
```

### Scheduled Jobs

# Run after 10 seconds
python cli.py enqueue --job "cleanup.sh" --delay 10

# Run after 1 hour (3600 seconds)
python cli.py enqueue --job "hourly_report.py" --delay 3600

# Run after 1 day (86400 seconds)
python cli.py enqueue --job "daily_backup.sh" --delay 86400
```

### Custom Retry Settings

# Retry up to 5 times on failure
python cli.py enqueue --job "flaky_api.py" --max-retries 5

# 30 second timeout per attempt
python cli.py enqueue --job "long_task.py" --timeout 30

# Worker Management

# Start 3 workers
python cli.py worker start --count 3

# Stop all workers (graceful shutdown)
python cli.py worker stop

# Check worker status
python cli.py status
```

### Job Monitoring

# See all pending jobs
python cli.py list-jobs pending --limit 50

# See completed jobs
python cli.py list-jobs completed --limit 20

# See failed jobs
python cli.py list-jobs failed
```

### Dead Letter Queue

# View DLQ jobs
python cli.py dlq list

# Retry a specific job from DLQ
python cli.py dlq retry --job-id abc12345

# Clear DLQ (if you implement this)
python cli.py dlq clear
```

### Configuration

# View current settings
python cli.py config-cmd show

# Change max retries globally
python cli.py config-cmd set --key max_retries --value 5

# Change backoff rate
python cli.py config-cmd set --key retry_backoff_base --value 2
```

---

## 🏗️ Architecture

### System Design

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Interface                        │
│                          (cli.py)                            │
└──────────────────────────┬──────────────────────────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
┌───────▼────────┐                   ┌────────▼────────┐
│ Queue Manager  │                   │ Worker Manager  │
│ - Enqueue jobs │                   │ - Start workers │
│ - Schedule     │                   │ - Execute jobs  │
│ - Retry logic  │                   │ - Handle errors │
└───────┬────────┘                   └────────┬────────┘
        │                                     │
        └──────────────┬──────────────────────┘
                       │
              ┌────────▼─────────┐
              │   Storage Layer  │
              │   (SQLite DB)    │
              │  - Jobs table    │
              │  - Metrics table │
              └──────────────────┘
```

### Job Lifecycle

```
┌─────────┐
│ PENDING │  ← New job or scheduled job becomes ready
└────┬────┘
     │
     │ Worker picks up job
     ▼
┌────────────┐
│ PROCESSING │  ← Worker executes command
└─────┬──────┘
      │
      ├─────────────┐
      │             │
   SUCCESS        FAILURE
      │             │
      ▼             ▼
┌───────────┐  ┌─────────┐
│ COMPLETED │  │ FAILED  │  ← Retry with exponential backoff
└───────────┘  └────┬────┘
                    │
                    │ After max_retries exhausted
                    ▼
               ┌────────┐
               │  DEAD  │  ← Moves to Dead Letter Queue
               └────────┘
```

### Key Components

1. **CLI Layer** (`cli.py`)
   - User interface using Click framework
   - Command parsing and validation
   - Pretty output formatting with tabulate

2. **Queue Manager** (`core/queue_manager.py`)
   - Job enqueueing and scheduling
   - Retry logic with exponential backoff
   - Dead letter queue management
   - Metrics collection

3. **Worker Manager** (`core/worker_manager.py`)
   - Worker thread lifecycle management
   - Job execution with subprocess
   - Timeout handling
   - Graceful shutdown coordination

4. **Storage Layer** (`core/storage.py`)
   - SQLite database operations
   - Thread-safe job locking
   - Job state persistence
   - Metrics storage

5. **Configuration** (`core/config_manager.py`)
   - JSON-based configuration
   - Runtime setting updates
   - Default value management

6. **Logging** (`utils/logger.py`)
   - Structured event logging
   - File and console output
   - Execution metrics tracking

---

## 🎮 CLI Commands

### Job Management

| Command | Description | Example |
|---------|-------------|---------|
| `enqueue` | Add a new job to the queue | `python cli.py enqueue --job "echo test"` |
| `worker start` | Start one or more workers | `python cli.py worker start --count 3` |
| `worker stop` | Stop all workers gracefully | `python cli.py worker stop` |
| `status` | Show system status | `python cli.py status` |

### Job Listing

| Command | Description | Example |
|---------|-------------|---------|
| `list-jobs pending` | List pending jobs | `python cli.py list-jobs pending` |
| `list-jobs completed` | List completed jobs | `python cli.py list-jobs completed --limit 50` |
| `list-jobs failed` | List failed jobs | `python cli.py list-jobs failed` |

### Dead Letter Queue

| Command | Description | Example |
|---------|-------------|---------|
| `dlq list` | View DLQ jobs | `python cli.py dlq list` |
| `dlq retry` | Retry a DLQ job | `python cli.py dlq retry --job-id abc123` |

### Configuration

| Command | Description | Example |
|---------|-------------|---------|
| `config-cmd show` | Display all settings | `python cli.py config-cmd show` |
| `config-cmd set` | Update a setting | `python cli.py config-cmd set --key max_retries --value 5` |

---

## ⚙️ Configuration

### Default Settings
```json
{
  "max_retries": 3,
  "retry_backoff_base": 2,
  "job_timeout": 300,
  "worker_poll_interval": 1,
  "max_concurrent_jobs": 4,
  "db_path": "data/queuectl.db",
  "log_path": "logs/queuectl.log",
  "config_path": "config/queuectl.json"
}
```

### Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| `max_retries` | 3 | Number of retry attempts before DLQ |
| `retry_backoff_base` | 2 | Base for exponential backoff (2^attempts) |
| `job_timeout` | 300 | Seconds before job is killed |
| `worker_poll_interval` | 1 | Seconds between queue checks |
| `max_concurrent_jobs` | 4 | Max workers that can run |
| `db_path` | `data/queuectl.db` | SQLite database location |
| `log_path` | `logs/queuectl.log` | Log file location |

### Exponential Backoff Explained

With `retry_backoff_base = 2`:
- Attempt 1: Fails → retry after **1 second** (2^0)
- Attempt 2: Fails → retry after **2 seconds** (2^1)
- Attempt 3: Fails → retry after **4 seconds** (2^2)
- Attempt 4: Fails → retry after **8 seconds** (2^3)
- After max_retries → moves to **Dead Letter Queue**

---

## 🧪 Testing

### Run All Tests

cd scripts
python test_queuectl.py
```

### Test Coverage

QueueCTL includes 7 comprehensive integration tests:

1. **Basic Enqueue & Execution** ✓
   - Tests job creation and successful execution
   - Verifies output capture

2. **Retry with Exponential Backoff** ✓
   - Tests automatic retry mechanism
   - Verifies exponential delay between retries
   - Confirms DLQ movement after exhausted retries

3. **Priority Queue** ✓
   - Tests job ordering by priority
   - Verifies higher priority jobs execute first

4. **Scheduled Jobs** ✓
   - Tests delayed job execution
   - Verifies jobs don't run before scheduled time
   - Confirms jobs become available after delay

5. **Dead Letter Queue & Retry** ✓
   - Tests DLQ functionality
   - Verifies manual retry from DLQ
   - Confirms attempts counter reset

6. **Job Timeout** ✓
   - Tests timeout enforcement
   - Verifies long-running jobs are killed
   - Confirms timeout error handling

7. **Stale Lock Cleanup** ✓
   - Tests expired lock detection
   - Verifies jobs can be reclaimed
   - Ensures no permanent blocking

### Expected Output
```
Starting QueueCTL Integration Tests
==================================================
✓ All tests passed!
📊 FINAL TEST SUMMARY:
Pending: 1, Processing: 0, Completed: 0, Failed: 0, DLQ: 0
```

---

## 🛡️ Why This Implementation is Reliable

### 1. **Robust Error Handling**
- ✅ All database operations wrapped in try-catch blocks
- ✅ Failed jobs automatically retry with exponential backoff
- ✅ Jobs that exceed timeout are gracefully terminated
- ✅ Exceptions don't crash the worker threads
- ✅ SQLite transaction rollback on errors

### 2. **Thread Safety**
- ✅ RLock (reentrant lock) on all database operations
- ✅ Job locking prevents duplicate execution by multiple workers
- ✅ Lock expiration prevents permanent blocking
- ✅ Atomic state transitions (pending → processing → completed)
- ✅ Thread-safe worker management

### 3. **Data Persistence**
- ✅ SQLite ensures jobs survive system crashes
- ✅ All state changes immediately committed to disk
- ✅ Database indexes for fast query performance
- ✅ No in-memory job loss during restarts
- ✅ Metrics persist for historical analysis

### 4. **Fault Tolerance**
- ✅ Workers can be stopped/restarted without job loss
- ✅ Stale locks automatically cleaned up
- ✅ Failed jobs don't block the queue
- ✅ Dead Letter Queue captures all permanent failures
- ✅ Graceful shutdown completes current jobs

### 5. **Comprehensive Testing**
- ✅ 7 integration tests covering all features
- ✅ Tests verify correctness under various scenarios
- ✅ Edge cases tested (timeouts, retries, priorities)
- ✅ Database cleanup between tests
- ✅ 100% test pass rate

### 6. **Production Best Practices**
- ✅ Structured logging for debugging
- ✅ Configurable settings via JSON
- ✅ Clean separation of concerns
- ✅ Clear error messages and status codes
- ✅ Metrics for monitoring and alerting

### 7. **Proven Reliability Mechanisms**

**Job State Machine**
```
Every job follows a strict state machine with validation:
- State transitions are atomic
- Invalid transitions are prevented
- All transitions are logged
```

**Lock Mechanism**
```
Jobs use lock_expires timestamp:
- Lock acquired before processing
- Lock expires after timeout
- Expired locks can be reclaimed
- Prevents duplicate execution
```

**Exponential Backoff**
```
Retries use increasing delays:
- Prevents overwhelming failing systems
- Gives temporary issues time to resolve
- Configurable base and max retries
```

---

## 📁 Project Structure

```
queuectl/
│
├── core/                          # Core business logic
│   ├── __pycache__/              # Python cache files
│   ├── __init__.py               # Package initializer
│   ├── config_manager.py         # Configuration management
│   ├── queue_manager.py          # Job queue logic
│   ├── storage.py                # SQLite database operations
│   └── worker_manager.py         # Worker thread management
│
├── data/                         # Database storage
│   ├── queuectl.db              # Production database
│   └── test.db                  # Test database
│
├── logs/                        # Log files
│   ├── queuectl.log            # Production logs
│   └── test.log                # Test logs
│
├── scripts/                     # Test and utility scripts
│   ├── config/                 # Test configuration
│   │   └── test.json          # Test settings
│   ├── data/                  # Test database directory
│   │   └── test.db           # Test database
│   ├── logs/                 # Test logs directory
│   └── test_queuectl.py      # Integration test suite
│
├── utils/                      # Utility modules
│   ├── __pycache__/           # Python cache
│   ├── __init__.py            # Package initializer
│   └── logger.py              # Logging system
│
├── __init__.py                # Root package initializer
├── cli.py                     # CLI interface (main entry point)
├── Documentation.md           # Documentation
├── requirements.txt           # Requirements
├── Readme.md                  # Readme 
├── setup.py                   # Package setup configuration
└── show_status.py            # Quick status viewer utility
```

### Key Files Explained

**Core Modules**
- `cli.py` - Main CLI interface, all user commands
- `core/queue_manager.py` - Job lifecycle, retry logic, DLQ
- `core/worker_manager.py` - Worker threads, job execution
- `core/storage.py` - Database operations, job persistence
- `core/config_manager.py` - Settings management

**Configuration**
- `config/queuectl.json` - Runtime configuration (auto-generated)
- `scripts/config/test.json` - Test-specific settings

**Data & Logs**
- `data/queuectl.db` - SQLite database with jobs & metrics
- `logs/queuectl.log` - Structured event logs
- `data/test.db` - Temporary test database

**Testing**
- `scripts/test_queuectl.py` - 7 integration tests
- Tests cover: enqueue, retry, priority, scheduling, DLQ, timeout

---

## 🎯 Design Decisions

### Why SQLite?
- ✅ Zero configuration, embedded database
- ✅ ACID compliance ensures data integrity
- ✅ Perfect for single-machine job queues
- ✅ No separate database server needed
- ✅ Easy backup (single file)

### Why Threading Over Multiprocessing?
- ✅ Shared memory access to SQLite
- ✅ Lower overhead for I/O-bound job execution
- ✅ Simpler worker coordination
- ✅ Graceful shutdown easier to implement
- ⚠️ Trade-off: CPU-bound jobs may be limited by GIL

### Why Click for CLI?
- ✅ Clean, declarative command definitions
- ✅ Automatic help text generation
- ✅ Type validation and error handling
- ✅ Subcommand support (worker, dlq, config)
- ✅ Industry standard for Python CLIs

### Why Exponential Backoff?
- ✅ Prevents hammering failing services
- ✅ Gives transient issues time to resolve
- ✅ Reduces system load during outages
- ✅ Industry best practice (AWS, Google use this)

### Why Job Locking?
- ✅ Prevents duplicate execution by multiple workers
- ✅ Handles worker crashes (lock expires)
- ✅ Enables horizontal scaling (multiple workers)
- ✅ Simple to implement and reason about

---

## 🚧 Assumptions & Trade-offs

### Assumptions
1. **Single Machine**: Designed for one server (not distributed)
2. **Trusted Commands**: Jobs run arbitrary shell commands
3. **Small to Medium Scale**: Optimized for <10,000 jobs/day
4. **Sequential Execution**: Jobs don't depend on each other

### Trade-offs
1. **SQLite vs Redis**
   - ✅ Simpler setup, no external dependencies
   - ⚠️ Lower throughput than Redis

2. **Threading vs Multiprocessing**
   - ✅ Lower memory overhead
   - ⚠️ Python GIL limits CPU-bound job parallelism

3. **In-process Workers vs Separate Processes**
   - ✅ Easier management and graceful shutdown
   - ⚠️ Worker crash could affect all jobs

4. **Simple Locking vs Distributed Locks**
   - ✅ Sufficient for single-machine use case
   - ⚠️ Can't scale across multiple machines

---

## 🔮 Future Enhancements

### Planned Features
- [ ] **Web Dashboard**: Real-time job monitoring UI
- [ ] **Job Dependencies**: Support for job chains (A → B → C)
- [ ] **Recurring Jobs**: Cron-like scheduling
- [ ] **Job Cancellation**: Kill running jobs via CLI
- [ ] **Webhook Notifications**: Alert on job completion/failure
- [ ] **Job History Export**: Export metrics to CSV/JSON
- [ ] **Docker Support**: Containerized deployment
- [ ] **Worker Health Checks**: Detect and restart hung workers
- [ ] **Priority Classes**: Named priority levels (low, medium, high, critical)
- [ ] **Rate Limiting**: Throttle job execution per time window

### Scalability Improvements
- [ ] **Redis Backend**: Optional Redis storage for high throughput
- [ ] **Distributed Workers**: Multi-machine worker support
- [ ] **Job Sharding**: Partition jobs across databases
- [ ] **Async I/O**: Use asyncio for better concurrency

---
---

**Happy Queueing! 🚀**


For questions or issues, please review the test output and logs in `logs/queuectl.log`.
