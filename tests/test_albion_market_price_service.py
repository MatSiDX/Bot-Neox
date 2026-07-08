import unittest

from services.albion_market_price_service import (
    AlbionMarketPriceConfig,
    AlbionMarketPriceError,
    AlbionMarketPriceService,
)


class FakePriceRepository:
    def __init__(self):
        self.rows = {}

    def get_many(self, *, server, location, item_unique_names, quality=1):
        return {
            item: self.rows[(server, location, item, quality)]
            for item in item_unique_names
            if (server, location, item, quality) in self.rows
        }

    def save(self, *, server, location, item_unique_name, quality, price, price_type, available, raw, error=""):
        row = {
            "server": server,
            "location": location,
            "item_unique_name": item_unique_name,
            "quality": quality,
            "price": price,
            "price_type": price_type,
            "available": available,
            "raw": raw,
            "updated_at": "2099-01-01T00:00:00Z",
            "error": error,
        }
        self.rows[(server, location, item_unique_name, quality)] = row
        return row

    def invalidate(self, **kwargs):
        return 0


class FakePriceClient:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.calls = []

    def fetch_prices(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.rows


class AlbionMarketPriceServiceTests(unittest.TestCase):
    def setUp(self):
        self.config = AlbionMarketPriceConfig(
            server="west",
            locations=("Black Market", "Caerleon"),
            qualities=(1,),
            cache_ttl_seconds=3600,
            timeout_seconds=3,
        )

    def test_enriches_loot_from_api_and_stores_cache(self):
        repository = FakePriceRepository()
        client = FakePriceClient([
            {
                "item_id": "T4_BAG",
                "city": "Black Market",
                "quality": 1,
                "sell_price_min": 1250,
                "buy_price_max": 900,
            }
        ])
        service = AlbionMarketPriceService(repository=repository, client=client, config=self.config)

        loot = service.enrich_loot({
            "records": [{"item_unique_name": "T4_BAG"}],
            "players": [{
                "player_name": "Neox",
                "items": [{"item_unique_name": "T4_BAG", "quantity": 2}],
            }],
        })

        item = loot["players"][0]["items"][0]
        self.assertEqual(item["price"], 1250)
        self.assertTrue(item["price_available"])
        self.assertEqual(item["total_price"], 2500)
        self.assertEqual(loot["pricing"]["source"], "api")
        self.assertEqual(len(client.calls), 1)

    def test_uses_fresh_cache_without_network(self):
        repository = FakePriceRepository()
        repository.save(
            server="west",
            location="Black Market",
            item_unique_name="T4_BAG",
            quality=1,
            price=777,
            price_type="sell_min",
            available=True,
            raw={},
        )
        repository.save(
            server="west",
            location="Caerleon",
            item_unique_name="T4_BAG",
            quality=1,
            price=888,
            price_type="sell_min",
            available=True,
            raw={},
        )
        client = FakePriceClient()
        service = AlbionMarketPriceService(repository=repository, client=client, config=self.config)

        prices, status = service.get_prices(["T4_BAG"])

        self.assertEqual(prices["T4_BAG"]["price"], 777)
        self.assertEqual(status["source"], "cache")
        self.assertEqual(client.calls, [])

    def test_partial_available_cache_fetches_all_markets_before_selecting_cheapest(self):
        repository = FakePriceRepository()
        repository.save(
            server="west",
            location="Black Market",
            item_unique_name="T4_BAG",
            quality=1,
            price=1000,
            price_type="sell_min",
            available=True,
            raw={},
        )
        client = FakePriceClient([
            {
                "item_id": "T4_BAG",
                "city": "Black Market",
                "quality": 1,
                "sell_price_min": 1000,
            },
            {
                "item_id": "T4_BAG",
                "city": "Caerleon",
                "quality": 1,
                "sell_price_min": 600,
            },
        ])
        service = AlbionMarketPriceService(repository=repository, client=client, config=self.config)

        prices, status = service.get_prices(["T4_BAG"])

        self.assertEqual(prices["T4_BAG"]["price"], 600)
        self.assertEqual(prices["T4_BAG"]["location"], "Caerleon")
        self.assertEqual(status["source"], "api")
        self.assertEqual(len(client.calls), 1)

    def test_marks_item_without_price_when_api_fails(self):
        service = AlbionMarketPriceService(
            repository=FakePriceRepository(),
            client=FakePriceClient(error=AlbionMarketPriceError("timeout")),
            config=self.config,
        )

        loot = service.enrich_loot({
            "records": [{"item_unique_name": "T5_BAG"}],
            "players": [{
                "player_name": "Neox",
                "items": [{"item_unique_name": "T5_BAG", "quantity": 1}],
            }],
        })

        item = loot["players"][0]["items"][0]
        self.assertIsNone(item["price"])
        self.assertFalse(item["price_available"])
        self.assertEqual(item["total_price"], 0)
        self.assertEqual(loot["pricing"]["missing_items"], 1)
        self.assertEqual(loot["pricing"]["errors"], ["timeout"])

    def test_uses_fresh_negative_cache_without_network(self):
        repository = FakePriceRepository()
        for location in ("Black Market", "Caerleon"):
            repository.save(
                server="west",
                location=location,
                item_unique_name="T6_BAG",
                quality=1,
                price=None,
                price_type="",
                available=False,
                raw={},
            )
        client = FakePriceClient()
        service = AlbionMarketPriceService(repository=repository, client=client, config=self.config)

        prices, status = service.get_prices(["T6_BAG"])

        self.assertEqual(prices, {})
        self.assertEqual(status["source"], "cache")
        self.assertEqual(status["missing_items"], 1)
        self.assertEqual(client.calls, [])

    def test_prefers_available_city_price_over_black_market_zero(self):
        repository = FakePriceRepository()
        client = FakePriceClient([
            {
                "item_id": "T8_RANDOM_DUNGEON_SOLO_TOKEN_ID2@2",
                "city": "Black Market",
                "quality": 1,
                "sell_price_min": 0,
                "buy_price_max": 0,
            },
            {
                "item_id": "T8_RANDOM_DUNGEON_SOLO_TOKEN_ID2@2",
                "city": "Caerleon",
                "quality": 1,
                "sell_price_min": 250000,
                "buy_price_max": 200000,
            },
        ])
        service = AlbionMarketPriceService(repository=repository, client=client, config=self.config)

        loot = service.enrich_loot({
            "records": [{"item_unique_name": "T8_RANDOM_DUNGEON_SOLO_TOKEN_ID2@2"}],
            "players": [{
                "player_name": "Gont8",
                "items": [{
                    "item_unique_name": "T8_RANDOM_DUNGEON_SOLO_TOKEN_ID2@2",
                    "quantity": 1,
                    "quality": 1,
                }],
            }],
        })

        item = loot["players"][0]["items"][0]
        self.assertEqual(item["price"], 250000)
        self.assertEqual(item["price_location"], "Caerleon")
        self.assertTrue(item["price_available"])

    def test_partial_negative_cache_does_not_block_api_lookup(self):
        repository = FakePriceRepository()
        repository.save(
            server="west",
            location="Black Market",
            item_unique_name="T8_RANDOM_DUNGEON_SOLO_TOKEN_ID2@2",
            quality=1,
            price=None,
            price_type="",
            available=False,
            raw={},
        )
        client = FakePriceClient([
            {
                "item_id": "T8_RANDOM_DUNGEON_SOLO_TOKEN_ID2@2",
                "city": "Caerleon",
                "quality": 1,
                "sell_price_min": 250000,
            },
        ])
        service = AlbionMarketPriceService(repository=repository, client=client, config=self.config)

        prices, status = service.get_prices(["T8_RANDOM_DUNGEON_SOLO_TOKEN_ID2@2"])

        self.assertEqual(prices["T8_RANDOM_DUNGEON_SOLO_TOKEN_ID2@2"]["price"], 250000)
        self.assertEqual(status["source"], "api")
        self.assertEqual(len(client.calls), 1)

    def test_uses_loot_estimated_value_when_api_has_no_price(self):
        service = AlbionMarketPriceService(
            repository=FakePriceRepository(),
            client=FakePriceClient([
                {
                    "item_id": "T8_RANDOM_DUNGEON_SOLO_TOKEN_ID2@2",
                    "city": "Black Market",
                    "quality": 1,
                    "sell_price_min": 0,
                    "buy_price_max": 0,
                },
                {
                    "item_id": "T8_RANDOM_DUNGEON_SOLO_TOKEN_ID2@2",
                    "city": "Caerleon",
                    "quality": 1,
                    "sell_price_min": 0,
                    "buy_price_max": 0,
                },
            ]),
            config=self.config,
        )

        loot = service.enrich_loot({
            "records": [{"item_unique_name": "T8_RANDOM_DUNGEON_SOLO_TOKEN_ID2@2"}],
            "players": [{
                "player_name": "Gont8",
                "items": [{
                    "item_unique_name": "T8_RANDOM_DUNGEON_SOLO_TOKEN_ID2@2",
                    "quantity": 1,
                    "quality": 1,
                    "raw_records": [{
                        "loot": {
                            "item": {
                                "average_est_market_value": 123456,
                            },
                        },
                    }],
                }],
            }],
        })

        item = loot["players"][0]["items"][0]
        self.assertEqual(item["price"], 123456)
        self.assertEqual(item["price_status"], "loot_estimate")
        self.assertEqual(item["price_location"], "Estimado del loot")
        self.assertTrue(item["price_available"])

    def test_keeps_prices_separated_by_quality(self):
        config = AlbionMarketPriceConfig(
            server="west",
            locations=("Black Market",),
            qualities=(1, 3),
            cache_ttl_seconds=3600,
            timeout_seconds=3,
        )
        service = AlbionMarketPriceService(
            repository=FakePriceRepository(),
            client=FakePriceClient([
                {
                    "item_id": "T4_BAG",
                    "city": "Black Market",
                    "quality": 1,
                    "sell_price_min": 100,
                },
                {
                    "item_id": "T4_BAG",
                    "city": "Black Market",
                    "quality": 3,
                    "sell_price_min": 300,
                },
            ]),
            config=config,
        )

        loot = service.enrich_loot({
            "records": [{"item_unique_name": "T4_BAG"}],
            "players": [{
                "player_name": "Neox",
                "items": [
                    {"item_unique_name": "T4_BAG", "quantity": 1, "quality": 1},
                    {"item_unique_name": "T4_BAG", "quantity": 1, "quality": 3},
                ],
            }],
        })

        prices = [item["price"] for item in loot["players"][0]["items"]]
        self.assertEqual(prices, [100, 300])


if __name__ == "__main__":
    unittest.main()
