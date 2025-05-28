import unittest
import gui_app
from unittest.mock import patch # Added

class TestGUI(unittest.TestCase):
    def setUp(self):
        gui_app.app.config['TESTING'] = True
        # gui_app.py sets a default SECRET_KEY, so flash messages should work.
        self.client = gui_app.app.test_client()

    def test_dashboard_route(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_health_route(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)

    @patch('gui_app.main.main')
    def test_manual_run_post_success(self, mock_main_main):
        mock_main_main.return_value = True # Simulate main.main succeeding

        form_data = {
            'date': '2023-10-26',
            'dry_run': 'true', # Form values are strings
            'force_download': 'false'
        }
        response = self.client.post('/run', data=form_data)

        self.assertEqual(response.status_code, 200) # The /run route renders the dashboard template
        mock_main_main.assert_called_once_with(
            target_date_str='2023-10-26',
            dry_run=True,      # main.main expects boolean
            force_download=False # main.main expects boolean
        )
        # Check for flash message in response
        self.assertIn(b'Manual run for 2023-10-26: Success', response.data)

if __name__ == "__main__":
    unittest.main()
