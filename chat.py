import ollama

def ask_question(input: str) -> str:
    # Ask a question
    response = ollama.chat(
        model="llama2",   # You can change to "llama2:13b", "llama2:70b", or other local models
        messages=[
            {"role": "user", "content": input + " /n Please answer in markdown format."}
        ]
    )
    return response["message"]["content"]
