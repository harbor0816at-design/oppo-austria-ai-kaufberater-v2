import asyncio

from app.services.faqs import FaqService


class FakePersistence:
    enabled = True

    async def acall(self, operation, data):
        assert operation == "faq_list"
        return [
            {
                "id": 1,
                "category": "warranty",
                "question_de": "Wie lange gilt die Garantie?",
                "answer_de": "Die Garantie beträgt drei Jahre.",
                "question_en": "How long is the warranty?",
                "answer_en": "The warranty is three years.",
                "question_zh": "保修多久？",
                "answer_zh": "保修三年。",
                "keywords": ["Garantie", "warranty", "保修"],
                "priority": 10,
                "is_active": True,
            }
        ]


def test_faq_matches_localized_keyword():
    service = FaqService(FakePersistence())
    item = asyncio.run(service.match("请问保修多久？", "zh"))
    assert item is not None
    assert item.id == 1
    assert service.answer_for(item, "zh") == "保修三年。"


def test_faq_does_not_match_unrelated_question():
    service = FaqService(FakePersistence())
    item = asyncio.run(service.match("Welche Kamera ist besser?", "de"))
    assert item is None
