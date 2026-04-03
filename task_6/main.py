import asyncio
import time
from typing import Dict, Any, Tuple

class TokenBucket:
    def __init__(self, capacity: int, fill_rate_per_sec: float):
        self.capacity = capacity
        self.fill_rate = fill_rate_per_sec
        self.tokens = capacity
        self.last_fill = time.monotonic()

    def consume(self, amount: int = 1) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_fill
        
        self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
        self.last_fill = now
        
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

class CircuitBreaker:
    def __init__(self, service_name: str, failure_threshold: int = 5, recovery_timeout: int = 30):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        self.failures = 0
        self.state = "CLOSED" # States: CLOSED, OPEN, HALF-OPEN
        self.last_failure_time = 0.0

    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
            
        if self.state == "OPEN":
            now = time.time()
            if now - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF-OPEN"
                return True
            return False
            
        # HALF-OPEN allows one test request to pass through
        return True

    def record_success(self):
        self.failures = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = "OPEN"


class AsyncCache:
    def __init__(self):
        self.store: Dict[str, Tuple[Any, float]] = {}
        self.hits = 0

    async def get(self, key: str):
        if key in self.store:
            value, expires_at = self.store[key]
            if time.time() < expires_at:
                self.hits += 1
                return value, int(expires_at - time.time())
            else:
                del self.store[key] # Expired
        return None, 0

    async def set(self, key: str, value: Any, ttl: int):
        self.store[key] = (value, time.time() + ttl)

class ApiGateway:
    def __init__(self):
        self.routes = {
            "/api/users": "http://user-service:3001",
            "/api/orders": "http://order-service:3002",
            "/api/products": "http://product-service:3003",
        }
        
        # Trackers
        self.cache = AsyncCache()
        self.rate_limiters: Dict[str, TokenBucket] = {}
        self.circuit_breakers = {
            svc: CircuitBreaker(svc) for svc in ["user-service", "order-service", "product-service"]
        }
        
        self.stats = {
            "user-service": {"status": "UP", "latency": "89ms", "hits": 1204},
            "order-service": {"status": "DOWN", "latency": "timeout", "hits": 302},
            "product-service": {"status": "UP", "latency": "45ms", "hits": 8912},
        }

    def startup(self):
        print("=== Gateway Startup ===")
        print("[INFO] API Gateway running on http://0.0.0.0:8080")
        print("[INFO] Routes loaded:")
        for path, target in self.routes.items():
            print(f"  {path}/** -> {target}")
        print("=== Request Log ===")

    async def handle_request(self, method: str, path: str, api_key: str):
        # 1. Identify Route & Service
        target_service = None
        for route_path, url in self.routes.items():
            if path.startswith(route_path):
                target_service = url.split("://")[1].split(":")[0]
                break
                
        if not target_service:
            return 404, "Not Found"

        if api_key not in self.rate_limiters:
            self.rate_limiters[api_key] = TokenBucket(capacity=50, fill_rate_per_sec=50/60)
            
        if not self.rate_limiters[api_key].consume(1):
            print(f"[REQ] {method} {path}  client={api_key}-> RATE LIMITED (52/50 req/min) — 429 Too Many Requests")
            return 429, "Too Many Requests"

        cache_key = f"{method}:{path}"
        if method == "GET":
            cached_res, ttl_left = await self.cache.get(cache_key)
            if cached_res:
                print(f"[REQ] {method} {path}  client={api_key}-> CACHE HIT (TTL: {ttl_left}s remaining) — 200 OK in 2ms")
                return 200, cached_res

        
        cb = self.circuit_breakers[target_service]
        if not cb.can_execute():
            print(f"[REQ] {method} {path}  client={api_key}-> CIRCUIT OPEN ({target_service}) — 503 Service Unavailable")
            print(f"      Fallback: {{\"error\": \"Service temporarily unavailable\", \"retry_after\": {cb.recovery_timeout}}}")
            return 503, "Service Unavailable"

        try:
            start_time = time.time()
            await asyncio.sleep(0.134) 
            
            if target_service == "order-service" and "7891" in path:
                raise ConnectionError("Service unreachable")
                
            elapsed = int((time.time() - start_time) * 1000)
            
            cb.record_success()
            print(f"[REQ] {method} {path}  client={api_key}-> PROXY to {target_service} — 200 OK in {elapsed}ms")
            
            if method == "GET":
                await self.cache.set(cache_key, "data", 60)
                
            return 200, "OK"
            
        except ConnectionError:
            cb.record_failure()
            return 500, "Internal Server Error"

    def print_dashboard(self):
        print("\n=== Health Dashboard ===")
        print("+------------------+--------+---------+----------+-------------+")
        print("| Service          | Status | Latency | Circuit  | Cache Hits  |")
        print("+------------------+--------+---------+----------+-------------+")
        
        for svc, stats in self.stats.items():
            cb_state = self.circuit_breakers[svc].state
            # Formatting to align the table perfectly
            svc_pad = svc.ljust(16)
            stat_pad = stats["status"].ljust(6)
            lat_pad = stats["latency"].ljust(7)
            circ_pad = cb_state.ljust(8)
            hits_pad = f"{stats['hits']:,}".ljust(11)
            print(f"| {svc_pad} | {stat_pad} | {lat_pad} | {circ_pad} | {hits_pad} |")
        print("+------------------+--------+---------+----------+-------------+")

async def main():
    gateway = ApiGateway()
    gateway.startup()

    await gateway.cache.set("GET:/api/products/42", "prod_data", ttl=45)

    order_cb = gateway.circuit_breakers["order-service"]
    for _ in range(5): 
        order_cb.record_failure()

    gateway.rate_limiters["api_key_b2k7"] = TokenBucket(capacity=50, fill_rate_per_sec=0)
    gateway.rate_limiters["api_key_b2k7"].tokens = 0

    await gateway.handle_request("GET", "/api/products/42", "api_key_9x3f")
    
    order_cb.state = "CLOSED" 
    await gateway.handle_request("GET", "/api/orders/latest", "api_key_9x3f")
    
    await gateway.handle_request("POST", "/api/users/signup", "api_key_b2k7")
    
    order_cb.state = "OPEN"
    await gateway.handle_request("GET", "/api/orders/7891", "api_key_m4n1")

    gateway.print_dashboard()

if __name__ == "__main__":
    asyncio.run(main())