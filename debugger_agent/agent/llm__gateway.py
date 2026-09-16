from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()


class LLMGateway:

    def __init__(self):
        self.llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.2,
            max_retries=6,
            timeout=30,
            max_tokens=4096,
        )

    def invoke(self, messages):
        return self.llm.invoke(messages)