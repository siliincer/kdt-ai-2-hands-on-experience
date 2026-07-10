"""패키지 내부 경로 상수.

fin-ai 원본은 config 경로 상수가 3개 모듈(workflow_loader, workflow_matcher,
subgraph_builder)에 중복 정의되어 있었다. 포팅하면서 이 파일 하나로 일원화했다.
config/ 디렉터리는 패키지 안(src/agent/config)에 있으므로 실행 위치(cwd)와
무관하게 항상 같은 경로를 가리킨다.
"""

from __future__ import annotations

from pathlib import Path

CONFIG_DIR = Path(__file__).parent / "config"
WORKFLOWS_PATH = CONFIG_DIR / "workflows.yaml"
