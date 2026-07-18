"""Offline tests for the direct-USGS Sentinel path."""
import unittest
from unittest.mock import patch

import requests

from landanimate import Scene, m2m_download_plan, m2m_sentinel_search


class M2MSentinelTests(unittest.TestCase):
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
