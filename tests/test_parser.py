from src.llm.parser import infer_conversation_tags 

def test_tags(text: str):
    print(text)
    print(infer_conversation_tags(text))
    print()


test_tags("I need your help with my new business project.")
test_tags("You should not trust those rumors.")
test_tags("This price is too high.")
test_tags("Have you read any good books lately?")
test_tags("Why are you avoiding me?")
test_tags("How's your day going?")