"""
Cloudflare Zero Trust GraphQL Analytics Probe
Checks if the Cloudflare API Token has Analytics:Read permission.
Note: Gateway locations & rules use the Zero Trust REST API (which is active & working).
"""

import os
import sys
import requests

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from core.store import HubStore
from core.cloudflare_bridge import get_cf_credentials

store = HubStore()
TOKEN, ACCOUNT_ID = get_cf_credentials(store)
HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}

def check_cf_permissions():
    if not TOKEN or not ACCOUNT_ID:
        print("[ERROR] Cloudflare credentials not found in settings or environment.")
        return

    print(">>> 1. Testing Cloudflare Zero Trust REST API (Rules & Locations)...")
    rest_url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/gateway/rules"
    try:
        r_rest = requests.get(rest_url, headers=HEADERS, timeout=8)
        if r_rest.status_code == 200 and r_rest.json().get("success"):
            rules = r_rest.json().get("result", [])
            print(f"    [OK] REST API connected! Total Gateway rules: {len(rules)}")
        else:
            print(f"    [FAIL] REST API error: {r_rest.text[:200]}")
    except Exception as e:
        print(f"    [ERROR] REST API exception: {e}")

    print(">>> 2. Testing Cloudflare GraphQL Analytics API...")
    query = """
    query GetAccountAnalytics($accountTag: string) {
      viewer {
        accounts(filter: { accountTag: $accountTag }) {
          gatewayRequestsAdaptiveGroups(limit: 5) {
            count
          }
        }
      }
    }
    """
    try:
        r_gql = requests.post(
            'https://api.cloudflare.com/client/v4/graphql',
            headers=HEADERS,
            json={'query': query, 'variables': {'accountTag': ACCOUNT_ID}},
            timeout=8
        )
        res = r_gql.json()
        if res.get("data") and not res.get("errors"):
            print("    [OK] GraphQL Analytics authorized!")
        else:
            err = res.get("errors", [{}])[0].get("message", "Not authorized")
            print(f"    [INFO] GraphQL Analytics: {err}")
            print("    [NOTE] Zero Trust protection, Kill Switch & Anycast DNS operate via REST API.")
    except Exception as e:
        print(f"    [ERROR] GraphQL exception: {e}")

if __name__ == "__main__":
    check_cf_permissions()
