import os
import sys
import subprocess

def print_status(msg, status="OK"):
    if status == "OK":
        print(f"[\033[92mOK\033[0m] {msg}")
    elif status == "FAIL":
        print(f"[\033[91mFAIL\033[0m] {msg}")
    elif status == "WARN":
        print(f"[\033[93mWARN\033[0m] {msg}")

def main():
    print("Running Pre-flight Checks...")
    
    # 1. Change working directory to orm_collection so .env is found
    orm_collection_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'orm_collection'))
    os.chdir(orm_collection_dir)
    sys.path.insert(0, orm_collection_dir)
    
    # 2. Check Environment Variables
    try:
        from app.core.config import settings
        print_status("Environment variables loaded")
    except Exception as e:
        print_status(f"Failed to load environment variables: {e}", "FAIL")
        sys.exit(1)
        
    # 3. Check PostgreSQL
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            dbname=settings.DB_NAME,
            connect_timeout=3
        )
        conn.close()
        print_status("PostgreSQL is reachable")
    except Exception as e:
        print_status(f"PostgreSQL connection failed: {e}", "FAIL")
        sys.exit(1)
        
    # 4. Check Redis
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_timeout=3)
        r.ping()
        print_status("Redis is reachable")
    except Exception as e:
        print_status(f"Redis connection failed: {e}", "FAIL")
        sys.exit(1)

    # 5. Check Celery Broker Configuration
    try:
        from app.core.celery_app import celery_app
        broker_url = celery_app.conf.broker_url
        if not broker_url.startswith("redis://"):
            print_status(f"Celery broker is NOT Redis! Current broker: {broker_url}", "FAIL")
            sys.exit(1)
        print_status("Celery configured to use Redis broker")
    except Exception as e:
        print_status(f"Celery configuration check failed: {e}", "FAIL")
        sys.exit(1)
        
    # 6. Database Migrations
    try:
        print("Running database migrations...")
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'orm_collection')),
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print_status(f"Alembic migrations failed:\n{result.stderr}", "FAIL")
            sys.exit(1)
        print_status("Database schema is up to date")
    except Exception as e:
        print_status(f"Migration check failed: {e}", "FAIL")
        sys.exit(1)
        
    print("\nAll pre-flight checks passed!")
    sys.exit(0)

if __name__ == "__main__":
    main()
