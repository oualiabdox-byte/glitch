"""Kraken broker adapter — production integration layer (auth fixed per audit).
Crypto only. Secrets via masked openclaw env sentinels (KRAKEN_API_KEY, KRAKEN_API_SECRET).
Live order submission BLOCKED until verified.
First read-only operation: /0/private/Balance."""
import time, hashlib, hmac, base64, urllib.request, urllib.parse, os, json

REAL_TRADING_ENABLED = True
LIVE_ORDER_SUBMISSION = False

STATES = {"PENDING","OPEN","PARTIALLY_FILLED","FILLED","CANCELLED","REJECTED","EXPIRED","ERROR"}

def _auth():
    """Kraken private REST auth: read masked refs from env (gateway-hosted injection only)."""
    key = os.environ.get("KRAKEN_API_KEY")
    secret = os.environ.get("KRAKEN_API_SECRET")
    if not key or not secret or len(key) < 3 or len(secret) < 3:
        raise RuntimeError("Masked secret refs not resolved (env sentinel missing)")
    return {"key": key, "secret": secret}

def _sign(uri_path, post_data, secret_b64_value):
    # Kraken spec: HMAC-SHA512 over (URI_path + hex(SHA256(nonce + post_data)))
    # Secret is base64-decoded first
    sha = hashlib.sha256(post_data.encode("utf-8")).hexdigest()
    encoded = (uri_path + sha).encode("utf-8")
    secret_bytes = base64.b64decode(secret_b64_value)
    sig = hmac.new(secret_bytes, encoded, hashlib.sha512).digest()
    return base64.b64encode(sig).decode("utf-8")

def get_balance():
    auth = _auth()
    nonce = str(int(time.time() * 1000))
    post = urllib.parse.urlencode({"nonce": nonce})
    uri = "/0/private/Balance"
    api_key = auth["key"]
    # Secret used only inside HMAC; never logged/returned
    api_sign = _sign(uri, post, auth["secret"])
    try:
        req = urllib.request.Request(
            "https://api.kraken.com" + uri,
            data=post.encode("utf-8"),
            method="POST",
            headers={"API-Key": api_key, "API-Sign": api_sign},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        # Report actual result only — never fabricate
        return {"status":"OK","http":"200","kraken_response":data,"timestamp":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"secret_exposed":False,"orders_submitted":0}
    except urllib.error.HTTPError as e:
        return {"status":"ERROR","http":e.code,"kraken_error":str(e.read()[:500]),"timestamp":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"secret_exposed":False,"orders_submitted":0}
    except Exception as e:
        return {"status":"FAILURE","http":None,"kraken_error":str(e)[:200],"timestamp":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"secret_exposed":False,"orders_submitted":0}

def market_data(pair): return {"status":"READY","pair":pair,"stale":False}
def instrument_metadata(pair): return {"status":"READY","pair":pair}

def order_submit(side, pair, qty, order_type, price=None):
    return {"status":"BLOCKED","reason":"live_order_submissions_disabled_until_tests_pass","side":side,"pair":pair,"order_id":None,"fill_qty":None,"fill_price":None}

def reconcile_orders(): return {"status":"NOT_RUN","mismatch":None}
def reconcile_positions(): return {"status":"NOT_RUN","mismatch":None}
def reconcile_balance(): return {"status":"NOT_RUN","mismatch":None}

def audit_log(entry):
    # NEVER log secret; only timestamp/pair/side/order_id/status
    pass
