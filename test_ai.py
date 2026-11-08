from ollama import chat

print("Connecting NEXUS AI to Qwen3...")

response = chat(
    model="qwen3:1.7b",
    messages=[
        {
            "role": "user",
            "content": "Say: NEXUS AI connection successful."
        }
    ],
    think=False,
    options={"num_ctx": 2048, "num_predict": 80}
)

print(response.message.content)
