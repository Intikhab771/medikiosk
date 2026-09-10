from ai.extractor import AnswerExtractor


extractor = AnswerExtractor()

question = {
    "id": "CP_001a",
    "text": "Where does the pain spread?",
    "answer_type": "multiple_choice",
    "options": [
        "Left arm",
        "Right arm",
        "Neck/Jaw",
        "Back",
        "Nowhere",
    ],
    "item_fields": None,
    "required": True,
}

transcript = (
    "No, the pain doesnt spread anywhere."
)

result = extractor.extract(question, transcript)

print("Extracted answer:")
print(result)