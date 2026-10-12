import asyncio

from app.market_data.models import Quote
from app.market_data.service import MarketDataService


class FakeRouter:
    def __init__(self):
        self.calls = 0

    async def get_quote(self, symbol):
        self.calls += 1
        await asyncio.sleep(0)
        return Quote(provider="test", symbol=symbol, price=101.0)

    def chain_for(self, capability):
        return ["test"]


async def _run():
    router = FakeRouter()
    first = MarketDataService(router=router)
    second = MarketDataService(router=router)
    one, two = await asyncio.gather(first.get_quote("CACHE_TEST_X"), second.get_quote("CACHE_TEST_X"))
    three = await first.get_quote("CACHE_TEST_X")
    return router.calls, one, two, three


def test_same_quote_request_is_cached_and_coalesced():
    calls, one, two, three = asyncio.run(_run())
    assert calls == 1
    assert one.price == two.price == three.price == 101.0
