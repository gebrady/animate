#!/usr/bin/env python3
"""
Tests for Landsat GIF Animator using USGS EarthExplorer
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
        required_modes = ['rgb', 'false_color', 'ndvi']
        for mode in required_modes:
            self.assertIn(mode, LandsatAnimator.VISUALIZATION_MODES)
            config = LandsatAnimator.VISUALIZATION_MODES[mode]
            self.assertIn('description', config)
    
    def test_visualization_mode_rgb(self):
        """Test RGB visualization mode configuration"""
        rgb_config = LandsatAnimator.VISUALIZATION_MODES['rgb']
        self.assertEqual(rgb_config['bands'], ['B4', 'B3', 'B2'])
    
    def test_visualization_mode_ndvi(self):
        """Test NDVI visualization mode configuration"""
        ndvi_config = LandsatAnimator.VISUALIZATION_MODES['ndvi']
        self.assertIn('expression', ndvi_config)
        self.assertIn('bands', ndvi_config)
    
    def test_api_url_defined(self):
        """Test that M2M API URL is defined"""
        self.assertIsNotNone(LandsatAnimator.M2M_API_URL)
        self.assertTrue(LandsatAnimator.M2M_API_URL.startswith('https://'))
    
    def test_landsat_dataset_defined(self):
        """Test that Landsat dataset is defined"""
        self.assertIsNotNone(LandsatAnimator.LANDSAT_DATASET)
        self.assertEqual(LandsatAnimator.LANDSAT_DATASET, 'landsat_ot_c2_l2')
    
    def tearDown(self):
        """Clean up after tests"""
        # Remove test output directory if it was created
        if os.path.exists('output') and not os.listdir('output'):
            shutil.rmtree('output')


if __name__ == '__main__':
    unittest.main()
