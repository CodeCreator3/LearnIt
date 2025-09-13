import ollama

# Ask a question
response = ollama.chat(
    model="llama2",   # You can change to "llama2:13b", "llama2:70b", or other local models
    messages=[
        {"role": "user", "content": "Explain quantum computing simply."}
    ]
)

# Print the model's reply
print(response["message"]["content"])
