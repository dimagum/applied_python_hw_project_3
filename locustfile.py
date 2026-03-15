from locust import HttpUser, task, between
import random
import string

class ShortenerLoadTest(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        res = self.client.post("/links/shorten", json={"original_url": "https://locust.io"})
        if res.status_code == 200:
            self.short_code = res.json().get("short_code")
        else:
            self.short_code = None

    @task(1)
    def test_create_link(self):
        rand_str = ''.join(random.choices(string.ascii_letters, k=5))
        self.client.post("/links/shorten", json={"original_url": f"https://example.com/{rand_str}"})

    @task(3)
    def test_redirect(self):
        if self.short_code:
            self.client.get(f"/{self.short_code}", name="/[short_code] redirect")
