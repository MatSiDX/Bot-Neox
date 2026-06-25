import unittest

from repositories.pagination import page_metadata, page_response


class PaginationTests(unittest.TestCase):
    def test_page_metadata_clamps_page_to_total_pages(self):
        payload = page_metadata(page=8, page_size=10, total_items=21)

        self.assertEqual(payload["page"], 3)
        self.assertEqual(payload["total_pages"], 3)
        self.assertEqual(payload["total_items"], 21)

    def test_page_response_keeps_extra_payload(self):
        payload = page_response(
            [{"id": 1}],
            page=1,
            page_size=25,
            total_items=1,
            item_key="records",
            extra={"summary": {"closed": 2}},
        )

        self.assertEqual(payload["records"], [{"id": 1}])
        self.assertEqual(payload["items"], [{"id": 1}])
        self.assertEqual(payload["summary"], {"closed": 2})


if __name__ == "__main__":
    unittest.main()
