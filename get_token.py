import requests

headers = {"Content-Type": "application/x-www-form-urlencoded"}
data = {
    "username":   "ims2170@columbia.edu",
    "password":   "Ms1994ms1994",
    "grant_type": "password",
    "client_id":  "acled",
    "scope":      "authenticated",
}
r = requests.post("https://acleddata.com/oauth/token", headers=headers, data=data)
token = r.json()["access_token"]
print(token)
