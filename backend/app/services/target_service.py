import httpx


async def send_attack(
    target_url: str,
    api_key: str,
    model_name: str,
    prompt: str,
    system_context: str | None = None,
) -> str:

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    messages = []

    # Add system context if available
    if system_context:
        messages.append(
            {
                "role": "system",
                "content": system_context,
            }
        )

    # Add the actual attack prompt
    messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    payload = {
        "model": model_name,
        "messages": messages,
    }

    async with httpx.AsyncClient(timeout=180.0) as client:

        response = await client.post(
            target_url,
            headers=headers,
            json=payload,
        )

    if response.status_code >= 400:
        # Show the target's own error message (raise_for_status hides it).
        body = response.text[:400]
        if api_key:
            body = body.replace(api_key, "***")
        raise RuntimeError(f"HTTP {response.status_code} from target: {body}")

    data = response.json()

    content = data["choices"][0]["message"]["content"]

    # An empty reply is "no answer", not a refusal. Raising here keeps it out of the
    # judge (it would be scored as safe) and lists it in execution_errors instead.
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Target returned no content")

    return content