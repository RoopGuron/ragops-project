import json
import mlflow.pyfunc


class RagPipeline(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        from rag.config import RagConfig
        with open(context.artifacts["config"]) as f:
            self.config = RagConfig(**json.load(f))

    def predict(self, context, model_input):
        from rag.answer import answer_question
        if hasattr(model_input, "columns"):          # DataFrame
            questions = model_input["question"].tolist()
        elif isinstance(model_input, dict):
            questions = model_input["question"]
        else:
            questions = list(model_input)
        return [answer_question(q, config=self.config).text for q in questions]
