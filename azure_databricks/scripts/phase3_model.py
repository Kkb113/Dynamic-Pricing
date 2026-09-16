"""MLflow Models-from-Code entrypoint. No cloud operations at import time."""
import mlflow
from pricing_mlflow.pipeline import PricingPipeline


class PricingPythonModel(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        self.pipeline = PricingPipeline(context.artifacts["inference_release"])

    def predict(self, context, model_input, params=None):
        return self.pipeline.predict(model_input)


mlflow.models.set_model(PricingPythonModel())
