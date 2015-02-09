import requests


def get(url):
    return requests.get(url).text
