from langfuse import observe

from backend.app.tracing import TRACING_ENABLED, langfuse


@observe(name="hello-repoguide")
def hello(x: int) -> int:
    return x * 2


print("tracing enabled:", TRACING_ENABLED)
print("auth ok:", langfuse.auth_check())
print("result:", hello(21))
langfuse.flush()   # send queued traces before the script exits
print("now open Langfuse -> your repoguide project -> Tracing")