import threading
import logging
from app.utils.redis_client import redis_client
from app.services.matching_engine import engine_instance
from app.core.db import SessionLocal

logger = logging.getLogger(__name__)

def redis_listener_thread():
    try:
        pubsub = redis_client.pubsub()
        pubsub.subscribe('keyword_updated')
        
        logger.info("Started Redis Pub/Sub listener for keyword_updated events.")
        
        for message in pubsub.listen():
            if message['type'] == 'message':
                logger.info("Received keyword_updated event. Refreshing Matching Engine...")
                db = SessionLocal()
                try:
                    engine_instance.refresh_processor(db)
                except Exception as e:
                    logger.error(f"Failed to refresh matching engine: {e}")
                finally:
                    db.close()
    except Exception as e:
        logger.warning(f"Could not connect to Redis Pub/Sub. Skipping listener thread. Error: {e}")

def start_pubsub_listener():
    thread = threading.Thread(target=redis_listener_thread, daemon=True)
    thread.start()
    return thread
