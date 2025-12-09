#!/usr/bin/env python3
"""
Tests for Landsat GIF Animator
"""

import unittest
from animate import LandsatAnimator
import os
import shutil


class TestLandsatAnimator(unittest.TestCase):
    """Test cases for LandsatAnimator"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.animator = LandsatAnimator()
        
    def test_get_coordinates_from_latlong(self):
        """Test coordinate parsing from lat,long string"""
        lat, lon = self.animator.get_coordinates("37.7749,-122.4194")
        self.assertAlmostEqual(lat, 37.7749, places=4)
        self.assertAlmostEqual(lon, -122.4194, places=4)
    
    def test_get_coordinates_from_city(self):
        """Test geocoding from city name"""
        try:
            lat, lon = self.animator.get_coordinates("San Francisco")
            # San Francisco is approximately at these coordinates
            self.assertAlmostEqual(lat, 37.7749, delta=0.5)
            self.assertAlmostEqual(lon, -122.4194, delta=0.5)
        except ValueError as e:
            # Skip test if geocoding service is unavailable
            if "Error geocoding location" in str(e):
                self.skipTest("Geocoding service unavailable")
    
    def test_output_directory_created(self):
        """Test that output directory is created"""
        self.assertTrue(os.path.exists(self.animator.output_dir))
    
    def test_visualization_modes_defined(self):
        """Test that all visualization modes are properly defined"""
        required_modes = ['rgb', 'false_color', 'ndvi', 'panchromatic', 'built_up', 'snow']
        for mode in required_modes:
            self.assertIn(mode, LandsatAnimator.VISUALIZATION_MODES)
            config = LandsatAnimator.VISUALIZATION_MODES[mode]
            self.assertIn('description', config)
    
    def test_visualization_mode_rgb(self):
        """Test RGB visualization mode configuration"""
        rgb_config = LandsatAnimator.VISUALIZATION_MODES['rgb']
        self.assertEqual(rgb_config['bands'], ['B4', 'B3', 'B2'])
        self.assertEqual(rgb_config['min'], 0)
        self.assertEqual(rgb_config['max'], 0.3)
    
    def test_visualization_mode_ndvi(self):
        """Test NDVI visualization mode configuration"""
        ndvi_config = LandsatAnimator.VISUALIZATION_MODES['ndvi']
        self.assertIn('expression', ndvi_config)
        self.assertIn('palette', ndvi_config)
        self.assertEqual(ndvi_config['min'], -1)
        self.assertEqual(ndvi_config['max'], 1)
    
    def tearDown(self):
        """Clean up after tests"""
        # Remove test output directory if it was created
        if os.path.exists('output') and not os.listdir('output'):
            shutil.rmtree('output')


if __name__ == '__main__':
    unittest.main()
