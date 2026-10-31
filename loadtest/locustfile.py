"""Load test for POST /chat.

Each virtual user is one of the seeded demo accounts. It logs in once (tokens are cached per account, so the
slow password check does not distort the chat numbers), then has short conversations: a few messages, then a new
conversation. The mix is mostly "show a class list", some searches, some "which classes are there", a little
off-topic. It never changes data: with LLM_PROVIDER=fake the scripted model calls read tools only, and the real
Claude run uses the same read-only messages.

Run (server must be up, see loadtest/README.md):
    locust -f loadtest/locustfile.py --headless -u 20 -r 5 -t 2m --host http://127.0.0.1:8000

Think time between messages: THINK_MIN / THINK_MAX seconds (default 1 and 3). Use 0 and 0 to push the server
as hard as the virtual users can.
"""

import os
import random

from locust import HttpUser, between, task

DEMO_PASSWORD = "demo1234"
MESSAGES_PER_CONVERSATION = int(os.environ.get("MESSAGES_PER_CONVERSATION", "5"))

# (email, a class this user may see, can the user ask "show class X"?)
ACCOUNTS = [
    ("aigul@luwo.test", "4А", True),
    ("bakyt@luwo.test", "3А", True),
    ("admin1@luwo.test", "4Б", True),
    ("admin2@luwo.test", "4А", True),
    ("root@luwo.test", "4А", False),  # a superadmin must also name the school, so skip the roster request
]
NAMES = ["Амир", "Алина", "Данияр", "Эрмек", "Касымов"]

_tokens: dict[str, str] = {}  # email -> JWT, shared by all virtual users of this process


class ChatUser(HttpUser):
    wait_time = between(float(os.environ.get("THINK_MIN", "1")), float(os.environ.get("THINK_MAX", "3")))

    def on_start(self):
        self.email, self.class_name, self.can_roster = random.choice(ACCOUNTS)
        if self.email not in _tokens:
            with self.client.post(
                "/auth/login", json={"email": self.email, "password": DEMO_PASSWORD}, name="/auth/login", catch_response=True
            ) as response:
                if response.status_code != 200:
                    response.failure(f"login failed: {response.status_code}")
                    return
                _tokens[self.email] = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {_tokens[self.email]}"}
        self.conversation_id: str | None = None
        self.sent = 0

    def say(self, text: str, name: str):
        if self.sent and self.sent % MESSAGES_PER_CONVERSATION == 0:
            self.conversation_id = None  # start a new conversation
        with self.client.post(
            "/chat", json={"message": text, "conversation_id": self.conversation_id}, headers=self.headers,
            name=f"/chat [{name}]", catch_response=True,
        ) as response:
            self.sent += 1
            if response.status_code != 200:
                response.failure(f"{response.status_code}: {response.text[:200]}")
                return
            body = response.json()
            self.conversation_id = body["conversation_id"]
            if body["meta"]["outcome"] == "error":  # the agent answered, but the request failed inside
                response.failure("agent outcome: error")

    @task(5)
    def show_class(self):
        if self.can_roster:
            self.say(f"Покажи список учеников {self.class_name}", "show class")
        else:
            self.say("Какие есть классы?", "list classes")

    @task(3)
    def search_student(self):
        self.say(f"Найди {random.choice(NAMES)}", "search")

    @task(2)
    def list_classes(self):
        self.say("Какие есть классы?", "list classes")

    @task(1)
    def off_topic(self):
        self.say("Привет! Как дела?", "off topic")
