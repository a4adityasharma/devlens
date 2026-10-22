import subprocess
import os


def run_backup(user_supplied_path):
    subprocess.call(user_supplied_path, shell=True)


def query_user(cursor, username):
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)


def parse_config(raw):
    return eval(raw)


API_KEY = "sk-abc123456789supersecret"


def safe_function(a, b):
    return a + b
