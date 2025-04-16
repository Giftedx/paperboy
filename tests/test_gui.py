import unittest
import gui_app

class TestGUI(unittest.TestCase):
    def setUp(self):
        gui_app.app.config['TESTING'] = True
        self.client = gui_app.app.test_client()

    def test_dashboard_route(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_health_route(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)

if __name__ == "__main__":
    unittest.main()
