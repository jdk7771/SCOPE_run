from openai import OpenAI

client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

try:
    r = client.chat.completions.create(
        model="llava:7b",
        messages=[{"role": "user", "content": "say hello"}],
        max_tokens=50,
    )
    print("11434 OK:", r.choices[0].message.content)
except Exception as e:
    print("11434 失败:", e)
    try:
        client2 = OpenAI(base_url="http://localhost:11435/v1", api_key="ollama")
        r2 = client2.chat.completions.create(
            model="llava:7b",
            messages=[{"role": "user", "content": "say hello"}],
            max_tokens=50,
        )
        print("11435 OK:", r2.choices[0].message.content)
    except Exception as e2:
        print("11435 也失败:", e2)