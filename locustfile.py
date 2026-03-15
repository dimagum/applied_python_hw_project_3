from locust import HttpUser, task, between
import random
import string

class ShortenerLoadTest(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.short_code = None
        unique_url = f"https://start.com/{random.randint(1, 1000000)}"

        with self.client.post("/links/shorten", json={"original_url": unique_url}, catch_response=True) as res:
            if res.status_code == 200:
                self.short_code = res.json().get("short_code")
                res.success()
            else:
                res.failure(f"Failed to create start link: {res.status_code}")

    @task(1)
    def test_create_link(self):
        rand_str = ''.join(random.choices(string.ascii_letters, k=6))
        self.client.post("/links/shorten", json={"original_url": f"https://example.com/{rand_str}"})

    @task(3)
    def test_redirect(self):
        if self.short_code:
            with self.client.get(f"/{self.short_code}", name="/[short_code] redirect", allow_redirects=False, catch_response=True) as res:
                if res.status_code in [307, 301, 302]:
                    res.success()
                elif res.status_code == 404:
                    res.failure("Link disappeared (404)")
                elif res.status_code >= 500:
                    res.failure(f"Server Error ({res.status_code}) - Database likely locked")
