from openai import OpenAI
import time

client = OpenAI(api_key="REDACTED", base_url="https://grid.ai.juspay.net")

# Test max batch size and speed
texts = ["test embedding text number " + str(i) for i in range(100)]

start = time.time()
resp = client.embeddings.create(model="gemini-embedding-001", input=texts)
elapsed = time.time() - start

print(f"Batch of 100: {elapsed:.2f}s  ({100/elapsed:.0f} texts/sec)")
print(f"Estimated time for 85k nodes at 100/batch: {85000/100 * elapsed / 60:.1f} min")

# Try batch of 250
texts2 = texts * 2 + texts[:50]  # 250
start = time.time()
try:
    resp2 = client.embeddings.create(model="gemini-embedding-001", input=texts2)
    elapsed2 = time.time() - start
    print(f"\nBatch of 250: {elapsed2:.2f}s  ({250/elapsed2:.0f} texts/sec)")
    print(f"Estimated time for 85k nodes at 250/batch: {85000/250 * elapsed2 / 60:.1f} min")
except Exception as e:
    print(f"\nBatch of 250 failed: {e}")
