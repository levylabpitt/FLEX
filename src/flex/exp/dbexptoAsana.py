import requests

def trigger_n8n_dbexptoAsana():
    webhook_url = "https://n8n.levylab.org/webhook/32be1239-a29b-4e69-bfec-74d312301c9b"

    data = {}
    response = requests.post(webhook_url, data=data)

    if response.status_code == 200:
        print("Workflow triggered successfully!")
    else:
        print(f"Failed to trigger workflow. Status code: {response.status_code}")