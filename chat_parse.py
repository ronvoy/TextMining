import json
import re
import sys


def clean_text(text):
    text = re.sub(r'\\n|\n', ' ', text)
    text = re.sub(r'[\u00a0\u2028\u2029\u200b\u200c\u200d\ufeff\u00ad\r\t]', ' ', text)
    text = text.replace('\u2019', "'").replace('\u2018', "'")
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u2013', '-').replace('\u2014', '-')
    text = text.replace('\u2026', '...')
    text = text.replace('\u00bd', '1/2').replace('\u00bc', '1/4').replace('\u00be', '3/4')
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()


def parse_chat(input_file="chat.json", output_file="chat_parse.json"):
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    parsed = []
    for chat in data:
        for entry in chat.get("history", []):
            if entry.get("role") == "assistant":
                parsed.append({
                    "content": clean_text(entry.get("content", "")),
                    "contexts": [clean_text(c) for c in entry.get("contexts", [])]
                })

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)

    print(f"Extracted {len(parsed)} assistant entries -> {output_file}")


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else "chat.json"
    output_file = sys.argv[2] if len(sys.argv) > 2 else "chat_parse.json"
    parse_chat(input_file, output_file)
