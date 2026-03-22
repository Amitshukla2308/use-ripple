from openai import OpenAI
import json

client = OpenAI(api_key="REDACTED", base_url="https://grid.ai.juspay.net")

# Test single embedding
resp = client.embeddings.create(
    model="gemini-embedding-001",
    input=["[haskell] service=euler-api-gateway  module=Euler.API.Gateway\nname=processPayment  kind=function\nsignature: PaymentRequest -> IO PaymentResponse"]
)

emb = resp.data[0].embedding
print("Model:     gemini-embedding-001")
print("Dimension:", len(emb))
print("Sample:   ", emb[:5])

# Test batch
resp2 = client.embeddings.create(
    model="gemini-embedding-001",
    input=["test one", "test two", "test three"]
)
print(f"\nBatch test: {len(resp2.data)} embeddings returned")
print(f"Usage: {resp2.usage}")
