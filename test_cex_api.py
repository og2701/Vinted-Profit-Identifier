import requests

query = "Hogwarts Legacy PS5"
url = f"https://wss2.cex.uk.webuy.io/v3/boxes?q={query}"
response = requests.get(url)
print(response.status_code)
if response.status_code == 200:
    data = response.json()
    boxes = data.get('response', {}).get('data', {}).get('boxes', [])
    for box in boxes[:2]:
        print(f"Name: {box.get('boxName')}")
        print(f"Cash price: £{box.get('cashPrice')}")
        print(f"Sell price: £{box.get('sellPrice')}")
