# automated_instagram_replies
This python file acts as a webhook reciepient server for the Meta Instagram messaging API. It recieves and responds to messages recieved to an instagram account with responses generated locally by ollama.

Steps in the process:

1. Flask server startup -- server open to webhook requests
2. User on Instragram DMs our bot
3. Webhook sent from Meta to our server
4. Our server recieves and parses request
5. Our server generates a response using ollama (locally hosted LLM models) -- in this case Phi 3 
6. Our server uses the API key provided to send response back to user who DMed us on Instagram
