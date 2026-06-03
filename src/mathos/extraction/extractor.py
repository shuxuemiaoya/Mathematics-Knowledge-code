import os
import json
from openai import OpenAI

class DeepSeekExtractor:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY must be provided or set in environment variables.")
        self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com/v1")
        
    def extract(self, markdown_text: str) -> dict:
        system_prompt = (
            "You are a mathematical ontology extraction expert. "
            "Read the provided markdown text and extract mathematical entities such as Concept, MicroConcept, Formula, or Theorem. "
            "You must output a JSON object containing a 'candidates' array. "
            "Each candidate must have the following fields: 'type' (the type of entity), 'category' (must be exactly one of: 知识点, 题, 思维或技巧, 趣味知识, 数学历史, 定理公式), "
            "'name' (name of the entity), 'description' (a brief description), and 'prerequisites' (an array of strings representing dependencies or prerequisite knowledge). "
            "Ensure the output is strictly valid JSON."
        )
        
        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": markdown_text}
            ],
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        return json.loads(content)
