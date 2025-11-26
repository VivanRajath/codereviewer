import requests
import json

url = "http://127.0.0.1:8000/api/chat"
payload = {
    "message": "add an h1 tag with title 'hello'",
    "context": {"code": "<html><body></body></html>", "filename": "index.html"},
    "history": []
}

try:
    response = requests.post(url, json=payload)
    print(f"Status Code: {response.status_code}")
    print(f"Raw Response: {response.content}")
    print(f"Response Text: {response.text}")
except Exception as e:
    print(f"Error: {e}")
