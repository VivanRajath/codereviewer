import requests
import sys

def test_merge_endpoint():
    print("Testing Merge Endpoint...")
    try:
        # Send a request with missing data, expecting 400
        response = requests.post("http://127.0.0.1:8000/api/merge-pr", json={})
        if response.status_code == 400:
            print("SUCCESS: Merge endpoint exists and validated input.")
        else:
            print(f"FAILURE: Unexpected status code {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"FAILURE: Could not connect to server. Is it running? {e}")

if __name__ == "__main__":
    test_merge_endpoint()
