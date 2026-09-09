# rag/serving.py
import json
import mlflow

class RagPipeline(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        from rag.config import RagConfig
        with open(context.artifacts["config"]) as f:
            self.config = RagConfig(**json.load(f))

    def predict(self, context, model_input: list[str]) -> list[str]:
        from rag.answer import answer_question
        return [answer_question(q, config=self.config).text for q in model_input]
