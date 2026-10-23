import yaml
import json
import os
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app


def export_openapi(output_path: str = "openapi.yaml"):
    openapi_schema = app.openapi()
    # Ensure OpenAPI 3.1.0 version tag
    openapi_schema["openapi"] = "3.1.0"

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(openapi_schema, f, sort_keys=False, allow_unicode=True)

    print(f"Successfully exported OpenAPI 3.1 specification to {output_path}")


if __name__ == "__main__":
    export_openapi()
