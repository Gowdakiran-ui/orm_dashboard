import sys
import os
import unittest
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from unittest.mock import patch, MagicMock
from app.workers.collection_tasks import fetch_feed_task
from app.workers.search_tasks import execute_search_task

class TestCollectionReliability(unittest.TestCase):

    @patch('app.workers.collection_tasks.RSSAdapter')
    @patch('app.workers.collection_tasks.SessionLocal')
    @patch('app.workers.collection_tasks.fetch_feed_task.retry')
    def test_rss_404_backoff(self, mock_retry, mock_db, mock_rss):
        # Setup mock db and feed
        mock_session = MagicMock()
        mock_db.return_value = mock_session
        mock_feed = MagicMock()
        mock_feed.id = "test-rss"
        mock_feed.feed_url = "http://test.com/404"
        mock_session.query().filter().first.return_value = mock_feed

        # Setup 404 Exception
        mock_rss_instance = mock_rss.return_value
        mock_rss_instance.fetch.side_effect = Exception("HTTP Error 404 fetching feed")

        # Mock request context for retries
        fetch_feed_task.request_stack.push(MagicMock(retries=1))
        
        mock_retry.side_effect = Exception("Retry Triggered")

        with self.assertRaises(Exception) as context:
            fetch_feed_task("test-rss")
            
        fetch_feed_task.request_stack.pop()
            
        self.assertEqual(str(context.exception), "Retry Triggered")
        mock_retry.assert_called_once()

    @patch('app.workers.search_tasks.RedditAdapter')
    @patch('app.workers.search_tasks.SessionLocal')
    @patch('app.workers.search_tasks.execute_search_task.retry')
    def test_reddit_429_backoff(self, mock_retry, mock_db, mock_reddit):
        mock_session = MagicMock()
        mock_db.return_value = mock_session
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_session.query().filter().first.return_value = mock_config

        mock_reddit_instance = mock_reddit.return_value
        mock_reddit_instance.search.side_effect = Exception("Reddit 429 Rate Limit Exceeded")

        execute_search_task.request_stack.push(MagicMock(retries=2))
        mock_retry.side_effect = Exception("Retry Triggered")

        with self.assertRaises(Exception) as context:
            execute_search_task("reddit", "apple", "kw-1")
            
        execute_search_task.request_stack.pop()
            
        self.assertEqual(str(context.exception), "Retry Triggered")
        mock_retry.assert_called_once()

    @patch('app.workers.search_tasks.YouTubeAdapter')
    @patch('app.workers.search_tasks.SessionLocal')
    @patch('app.workers.search_tasks.execute_search_task.retry')
    def test_youtube_quota_backoff(self, mock_retry, mock_db, mock_yt):
        mock_session = MagicMock()
        mock_db.return_value = mock_session
        mock_config = MagicMock()
        mock_config.enabled = True
        mock_session.query().filter().first.return_value = mock_config

        mock_yt_instance = mock_yt.return_value
        mock_yt_instance.search.side_effect = Exception("YouTube Quota Exceeded")

        execute_search_task.request_stack.push(MagicMock(retries=0))
        mock_retry.side_effect = Exception("Retry Triggered")

        with self.assertRaises(Exception) as context:
            execute_search_task("youtube", "apple", "kw-1")
            
        execute_search_task.request_stack.pop()
            
        self.assertEqual(str(context.exception), "Retry Triggered")
        mock_retry.assert_called_once()

if __name__ == '__main__':
    unittest.main()
