"""Offline tests for the direct-USGS Sentinel path."""
import unittest
from unittest.mock import patch

import requests

from landanimate import Scene, coverage_contains_bbox, m2m_download_plan, m2m_sentinel_search, usable_frame_fraction


class M2MSentinelTests(unittest.TestCase):
    def test_coverage_requires_the_whole_aoi(self):
        coverage = {"type": "Polygon", "coordinates": [[
            [-118, 33], [-117, 33], [-117, 35], [-118, 35], [-118, 33],
        ]]}
        self.assertTrue(coverage_contains_bbox(coverage, (-117.8, 33.2, -117.2, 34.8)))
        self.assertFalse(coverage_contains_bbox(coverage, (-117.8, 33.2, -116.8, 34.8)))

    def test_usable_frame_fraction_rejects_large_black_borders(self):
        frame = __import__("numpy").zeros((10, 10, 3), dtype="uint8")
        frame[:5] = 50
        self.assertEqual(usable_frame_fraction(frame), 0.5)

    def test_searches_both_usgs_sentinel_inventories(self):
        calls = []

        def fake_call(_session, endpoint, payload):
            calls.append((endpoint, payload))
            if endpoint == "dataset-search":
                return [
                    {"datasetAlias": "sentinel_2a", "datasetName": "Sentinel-2A"},
                    {"datasetAlias": "sentinel_2b", "datasetName": "Sentinel-2B"},
                ]
            if payload["datasetName"] == "sentinel_2a":
                return {"results": [{
                    "entityId": "A", "displayId": "S2A_TEST",
                    "temporalCoverage": {"startDate": "2024-01-02T10:00:00Z"}, "cloudCover": 3,
                }]}
            return {"results": []}

        with patch("landanimate.m2m_call", side_effect=fake_call):
            scenes = m2m_sentinel_search(requests.Session(), (-75, 40, -74, 41), "2024-01-01", "2024-12-31", 10)

        self.assertEqual([(scene.dataset, scene.entity_id) for scene in scenes], [("sentinel_2a", "A")])
        self.assertEqual([payload["datasetName"] for endpoint, payload in calls if endpoint == "scene-search"], ["sentinel_2a", "sentinel_2b"])
        self.assertEqual(calls[0][0], "dataset-search")

    def test_download_plan_uses_the_available_usgs_product(self):
        scene = Scene("S2A_TEST", "sentinel", "2024-01-02", 3, {}, "sentinel_2a", "A")

        def fake_call(_session, endpoint, _payload):
            if endpoint == "download-options":
                return [
                    {"entityId": "A", "available": False, "id": "browse"},
                    {"entityId": "A", "available": True, "id": "full"},
                ]
            if endpoint == "download-request":
                return {"availableDownloads": [{"entityId": "A", "productId": "full", "url": "https://example.test/file.zip"}]}
            self.fail(f"unexpected endpoint: {endpoint}")

        with patch("landanimate.m2m_call", side_effect=fake_call):
            plan = m2m_download_plan(requests.Session(), [scene])

        self.assertEqual(plan[0]["url"], "https://example.test/file.zip")


if __name__ == "__main__":
    unittest.main()
