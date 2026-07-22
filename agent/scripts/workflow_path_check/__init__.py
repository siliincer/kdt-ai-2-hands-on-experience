"""auto_workflow_path_check.py가 쓰는 워크플로우별 경로 검증 시나리오 모음.

워크플로우 하나당 파일 하나(agent/src/agent/workflows/의 관례를 그대로 따름):
공통 Fixture와 범용 Resume 드라이버는 _shared.py에 있고, 각 파일은
자기 워크플로우 전용 드라이버 + SCENARIOS + run_scenario()만 갖는다.
"""
