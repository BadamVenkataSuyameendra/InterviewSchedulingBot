from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file("oauth.json", ["https://www.googleapis.com/auth/calendar"])
creds = flow.run_local_server(port=0)

with open("token.json", "w") as token_file:
    token_file.write(creds.to_json())

print("Authentication successful! Token saved.")
