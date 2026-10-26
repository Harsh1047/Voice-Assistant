import os
from pathlib import Path
from getpass import getpass
from dotenv import load_dotenv
from google import genai
from google.genai import types
from windows_tools import TOOLS

LANGUAGES = {
    "en-IN": "Indian English", "en-US": "American English",
    "en-GB": "British English", "hi-IN": "Hindi (Devanagari script)",
}
DEFAULT_MODEL = "gemini-2.5-flash"


class Conversation:
    def __init__(self):
        self._turns = []

    def add(self, question, answer):
        self._turns.append((question, answer))
        self._turns = self._turns[-5:]

    def snapshot(self):
        return list(self._turns)

    def clear(self):
        self._turns.clear()


def get_response(user_text, api_key, model=DEFAULT_MODEL, history=(), language="en-IN",
                 system_prompt=None, call=None, check_cancelled=None):
    if not api_key or api_key == "replace_with_your_own_key":
        raise ValueError("Set GEMINI_API_KEY in .env or the application settings.")
    if not user_text.strip():
        raise ValueError("The message is empty.")
    check = check_cancelled or (lambda: None)
    invoke = call or (lambda function: function())
    contents = []
    for user, answer in list(history)[-5:]:
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user)]))
        contents.append(types.Content(role="model", parts=[types.Part.from_text(text=answer)]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_text)]))
    config = types.GenerateContentConfig(
        system_instruction=system_prompt or (
            "Answer questions briefly and clearly for voice output. "
            f"Respond in {LANGUAGES.get(language, language)}. "
            "Use this response language even if earlier messages used another language. "
            "Use a tool only when the user explicitly requests its action. "
            "Requests for explanations should receive text answers. "
            "Never claim an action succeeded before execution."
        ),
        tools=list(TOOLS.values()),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    def generate():
        with genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=30000, retry_options=types.HttpRetryOptions(attempts=2)),
        ) as client:
            return client.models.generate_content(model=model or DEFAULT_MODEL, contents=contents, config=config)

    check()
    response = invoke(generate)
    check()
    outputs, used = [], []
    for function_call in response.function_calls or []:
        check()
        tool = TOOLS.get(function_call.name)
        if tool is None or function_call.args:
            outputs.append("That tool request is not supported.")
        else:
            outputs.append(tool())
            used.append(function_call.name)
    if outputs:
        if language == "hi-IN":
            translations = {'Notepad launched.': 'नोटपैड खोल दिया गया है।', 'Calculator launched.': 'कैलकुलेटर खोल दिया गया है।', 'Browser launch requested.': 'ब्राउज़र खोलने का अनुरोध भेज दिया गया है।', 'Could not launch browser.': 'ब्राउज़र नहीं खुल सका।', 'That tool request is not supported.': 'यह कार्य उपलब्ध नहीं है।'}
            outputs = [translations.get(output, output) for output in outputs]
        answer = " ".join(outputs)
    else:
        answer = (response.text or "").strip()
        if not answer:
            raise RuntimeError("Gemini returned no text. Please try again.")
    check()
    return answer, ", ".join(used) or "None"


def main():
    load_dotenv(Path(__file__).with_name(".env"))
    key = os.getenv("GEMINI_API_KEY", "").strip() or getpass("Gemini API key: ").strip()
    conversation = Conversation()
    while True:
        try:
            text = input("You: ").strip()
            if text.lower() in {"exit", "quit", "stop"}:
                break
            answer, _ = get_response(text, key, model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL), history=conversation.snapshot())
            conversation.add(text, answer)
            print("Assistant:", answer)
        except (KeyboardInterrupt, EOFError):
            break
        except Exception as error:
            print(str(error).replace(key, "[REDACTED]") if key else str(error))


if __name__ == "__main__":
    main()
