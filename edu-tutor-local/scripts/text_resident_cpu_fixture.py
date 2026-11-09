"""CPU-only protocol fixture. Never used by the production worker command."""
from pathlib import Path
import time
import uuid
from edu_tutor.models.text_session_worker import main


class FixtureEngine:
    def __init__(self, root, emit):
        self.emit, self.loads, self.identity = emit, 0, uuid.uuid4().hex
        self.model = None

    def process(self, payload):
        fresh = self.model is None
        if fresh:
            self.model = object()
            self.loads += 1
        print("CPU fixture library diagnostic, not a model")
        info = {"model_instance_id": self.identity, "model_python_id": id(self.model),
            "cumulative_model_load_count": self.loads, "request_model_load_count": int(fresh), "fixture_only": True}
        self.emit("model_ready", **info)
        content = payload["messages"][0]["content"]
        if content == "wait":
            while not Path(payload["cancel_path"]).exists():
                time.sleep(.01)
            raise RuntimeError("Fixture cancelled")
        if content == "foreign":
            self.emit("metadata", instance_id="foreign", fixture_only=True)
            return
        self.emit("delta", text="fixture response")
        self.emit("metadata", **info, kind="text", finish_reason="eos", text="fixture response", model_load_count=int(fresh))

    def close(self):
        self.model = None
        return {"model_resident": False, "fixture_only": True}


if __name__ == "__main__":
    main(engine_factory=FixtureEngine)
