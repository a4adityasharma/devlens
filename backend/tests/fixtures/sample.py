import os
from typing import List


def generate_token(username):
    return username


class UserService:
    def authenticate(self, username, password):
        token = generate_token(username)
        return self.validate(token)

    def validate(self, token):
        return True

    def logout(self, session_id):
        pass


def top_level_helper(a, b=1, *args, **kwargs):
    svc = UserService()
    svc.authenticate("a", "b")
    return a + b
