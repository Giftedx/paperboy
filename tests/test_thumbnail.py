#!/usr/bin/env python3
"""
Tests for the thumbnail generation functionality.
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from thumbnail import generate_thumbnail

class TestThumbnailGeneration(unittest.TestCase):
    """Test cases for thumbnail generation."""
    
    def test_generate_thumbnail_invalid_format(self):
        """Test thumbnail generation with an invalid format."""
        source_path = "dummy.xyz"
        output_path = "dummy_thumbnail.jpg"
        file_format = "xyz"
        
        # Should return False for invalid format
        result = generate_thumbnail(source_path, output_path, file_format)
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()