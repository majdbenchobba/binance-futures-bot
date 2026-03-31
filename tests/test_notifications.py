import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import notifications


class NotificationsTest(unittest.TestCase):
    @patch("notifications.requests.post")
    def test_send_alert_posts_json_payload_to_webhook(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with patch.object(notifications, "ALERT_WEBHOOK_URL", "https://example.com/hook"):
            sent = notifications.send_alert(
                "something happened",
                level="error",
                context={"event": "trade_error", "symbol": "ETHUSDT"},
                log_message=False,
            )

        self.assertTrue(sent)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["message"], "something happened")
        self.assertEqual(kwargs["json"]["context"]["symbol"], "ETHUSDT")

    @patch("notifications.requests.post")
    def test_send_alert_returns_false_without_webhook(self, mock_post):
        with patch.object(notifications, "ALERT_WEBHOOK_URL", ""):
            sent = notifications.send_alert("local only", log_message=False)

        self.assertFalse(sent)
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
