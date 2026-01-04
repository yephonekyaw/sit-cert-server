"""
Windows-compatible startup script for FastAPI and Celery
Manages both services with proper logging and error handling
"""

import multiprocessing
import subprocess
import sys
import time
import signal
from pathlib import Path

# Add the parent directory to Python path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils.logging import get_logger

logger = get_logger()


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def run_fastapi_app():
    """Run FastAPI server"""
    try:
        logger.info("Starting FastAPI server process")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--reload",
            ],
            check=True,
            cwd=str(Path(__file__).parent.parent),
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"FastAPI process failed with return code {e.returncode}: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("FastAPI process interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error in FastAPI process: {e}")
        sys.exit(1)


def run_celery_worker():
    """Run Celery worker with Windows-compatible settings"""
    try:
        logger.info("Starting Celery worker process")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "app.celery",
                "worker",
                "--loglevel=info",
                "--pool=solo",
            ],
            check=True,
            cwd=str(Path(__file__).parent.parent),
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Celery process failed with return code {e.returncode}: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Celery process interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error in Celery process: {e}")
        sys.exit(1)


def check_redis_connection():
    """Check if Redis server is accessible"""
    try:
        import redis
        from app.config.settings import settings

        r = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=(
                settings.REDIS_PASSWORD if hasattr(settings, "REDIS_PASSWORD") else None
            ),
            socket_connect_timeout=5,
        )
        r.ping()
        logger.info("Redis connection successful")
        return True
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        logger.error("Please ensure Redis server is running")
        return False


def monitor_processes(processes):
    """Monitor running processes and handle failures"""
    logger.info("Starting process monitoring")

    while True:
        for process in processes:
            if not process.is_alive():
                exit_code = process.exitcode
                logger.error(
                    f"{process.name} process died unexpectedly with exit code: {exit_code}"
                )

                # Terminate remaining processes
                terminate_processes(processes)
                sys.exit(1)

        time.sleep(1)


def terminate_processes(processes):
    """Gracefully terminate all processes"""
    logger.info("Initiating graceful shutdown of all services")

    # Send termination signal to all processes
    for process in processes:
        if process.is_alive():
            logger.info(f"Terminating {process.name} process")
            process.terminate()

    # Wait for graceful shutdown
    for process in processes:
        try:
            process.join(timeout=10)
            if process.is_alive():
                logger.warning(
                    f"{process.name} did not terminate gracefully, force killing"
                )
                process.kill()
                process.join()
            else:
                logger.info(f"{process.name} terminated successfully")
        except Exception as e:
            logger.error(f"Error terminating {process.name}: {e}")


def main():
    """Main function to start and manage FastAPI and Celery services"""
    # Required for Windows multiprocessing
    multiprocessing.freeze_support()

    # Setup signal handlers
    setup_signal_handlers()

    logger.info("=" * 60)
    logger.info("Starting SIT Cert Services (FastAPI + Celery)")
    logger.info("=" * 60)
    logger.info("Press Ctrl+C to stop all services")

    # Check Redis connection before starting services
    if not check_redis_connection():
        logger.error("Cannot start services without Redis connection")
        sys.exit(1)

    processes = []

    try:
        # Start FastAPI server
        logger.info("Starting FastAPI server on http://localhost:8000")
        fastapi_process = multiprocessing.Process(
            target=run_fastapi_app, name="FastAPI", daemon=False
        )
        fastapi_process.start()
        processes.append(fastapi_process)

        # Give FastAPI a moment to start
        logger.info("Waiting for FastAPI to initialize...")
        time.sleep(3)

        # Start Celery worker
        logger.info("Starting Celery worker")
        celery_process = multiprocessing.Process(
            target=run_celery_worker, name="Celery", daemon=False
        )
        celery_process.start()
        processes.append(celery_process)

        logger.info("Both services started successfully")
        logger.info("FastAPI server: http://localhost:8000")
        logger.info("FastAPI documentation: http://localhost:8000/docs")
        logger.info("-" * 60)

        # Monitor processes
        monitor_processes(processes)

    except KeyboardInterrupt:
        logger.info("Shutdown signal received")
    except Exception as e:
        logger.error(f"Unexpected error in main process: {e}")
    finally:
        terminate_processes(processes)
        logger.info("All services stopped successfully")


if __name__ == "__main__":
    main()
