import anaplan_sdk


def create_anaplan_client(user_email: str, password: str, workspace_id: str, model_id: str, timeout: int | None = None) -> anaplan_sdk.Client:
    """Create and return a configured Anaplan SDK client"""
    kwargs = {
        "user_email": user_email,
        "password": password,
        "workspace_id": workspace_id,
        "model_id": model_id
    }
    if timeout is not None:
        kwargs["timeout"] = timeout

    return anaplan_sdk.Client(**kwargs)
