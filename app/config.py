import json
import os


if 'SERVER_ENV' in os.environ and os.environ['SERVER_ENV'] == 'production':
    print("Running on the server")
    with open("config.json", 'r') as f:
        config = json.load(f)
    APP_NAME = config["app"]["name"]
    API_KEY = os.environ['API_KEY']
    # database
    MONGODB_USER = config["database"]["user"]
    MONGODB_PASSWORD = os.environ['MONGODB_PASSWORD']
    MONGODB_HOST = config["database"]["host"]
    MONGODB_PORT = config["database"]["port"]
    MONGODB_NAME = config["database"]["name"]
else:
    print("Running locally")
    with open("config.dev.json", 'r') as f:
        config = json.load(f)
    APP_NAME = config["app"]["name"]
    API_KEY = config["app"]["api_key"]
    # database
    MONGODB_USER = config["database"]["user"]
    MONGODB_PASSWORD = config["database"]["password"]
    MONGODB_HOST = config["database"]["host"]
    MONGODB_PORT = config["database"]["port"]
    MONGODB_NAME = config["database"]["name"]