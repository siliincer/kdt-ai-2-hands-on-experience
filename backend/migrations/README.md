# Alembic 초기화 및 SQL 파일 위치 지정, 마이그레이션 실행 자동화

한 줄 요약)

적용하려면 alembic upgrade head

롤백하려면 alembic downgrade -1

자세한 건 https://github.com/siliincer/kdt-ai-2-hands-on-experience/wiki/Wiki_BE_Alembic 참조

1. Alembic 초기화 (완료)

$ cd backend
$ alembic init migrations

이 명령으로 migrations/env.py, migrations/alembic.ini, migrations/README, migrations/versions 폴더가 생성됩니다.

각 파일과 폴더의 역할은 다음과 같습니다.

1. 프로젝트 루트 파일

alembic.ini: Alembic의 메인 설정 파일입니다. 데이터베이스 접속 주소(sqlalchemy.url)나 로그 출력 형식 등 마이그레이션 도구 전체에 적용되는 설정을 관리합니다. (주의: 데이터베이스 비밀번호가 노출될 수 있으므로 Git 커밋 시 주의가 필요합니다.)

2. migrations/ 디렉토리 내부 파일

env.py: Alembic이 실행될 때 가장 먼저 구동되는 파이썬 스크립트입니다. SQLAlchemy 엔진을 구성하고 마이그레이션 파일들을 실행하는 핵심 로직이 들어있습니다. 테이블 스키마 자동 생성 기능(auto-generate)을 쓰려면 이 파일에서 프로젝트의 Base.metadata를 불러와 수정해야 합니다.

script.py.mako: 마이그레이션 버전 파일이 생성될 때 사용되는 템플릿 파일입니다. 새로운 마이그레이션 파일을 만들 때마다 이 mako 템플릿 구조를 기반으로 파이썬 파일이 작성됩니다. custom 포맷이 필요 없다면 수정할 일이 거의 없습니다.README: 마이그레이션 환경에 대한 간단한 설명서 파일입니다. 팀원들을 위해 자유롭게 가이드를 작성할 수 있습니다.

versions/ 폴더: 데이터베이스의 변경 이력이 담긴 마이그레이션 스크립트 파일들이 저장되는 곳입니다. alembic revision 명령을 실행할 때마다 이 폴더 안에 1a2b3c4d5e6f_description.py 형태의 고유 ID를 가진 파일이 쌓이게 됩니다

2. SQL 파일 위치 지정

migrations/versions 폴더 안에 raw SQL 파일을 생성하거나 복사합니다. 예:

migrations/versions/0001_create_table.sql
migrations/versions/0002_add_index.sql

3. migration 파일에 SQL 실행 코드 추가

migrations/versions/0001_create_table.py 예시:

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.

revision = '0001'
down_revision = None
branch_labels = None
dependent_on = None

def upgrade():
sql = open('migrations/versions/0001_create_table.sql', 'r', encoding='utf-8').read()
op.execute(sql)

def downgrade():
op.execute("DROP TABLE IF EXISTS users;")

migrations/versions/0002_add_index.py 예시:

from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
dependent_on = None

def upgrade():
sql = open('migrations/versions/0002_add_index.sql', 'r', encoding='utf-8').read()
op.execute(sql)

def downgrade():
op.execute("DROP INDEX IF EXISTS ix_users_email;")

4. FastAPI 실행 시 마이그레이션 자동 반영

앱 시작 코드에서 Alembic migration을 자동으로 적용하도록 설정합니다.

main.py 예시:

from fastapi import FastAPI
from alembic.config import Config
from alembic import command

app = FastAPI()

def run_migrations():
alembic_cfg = Config('migrations/alembic.ini')
command.upgrade(alembic_cfg, 'head')

@app.on_event('startup')
async def startup_event():
run_migrations()

@app.get('/')
def read_root():
return {'message': 'Hello'}

5. Docker PostgreSQL과 유지되도록 설정

docker-compose.yml 예시:

version: '3.8'
services:
db:
image: postgres:15
restart: always
env_file: - .env
volumes: - postgres_data:/var/lib/postgresql/data
ports: - '5432:5432'

backend:
build: .
command: uvicorn main:app --host 0.0.0.0 --port 8000
env_file: - .env
depends_on: - db
volumes: - .:/app
ports: - '8000:8000'

volumes:
postgres_data:

.env 예시:

POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=mydb
DATABASE_URL=postgresql+psycopg2://postgres:postgres@db:5432/mydb

6. Alembic 설정 변경

migrations/alembic.ini 에서 sqlalchemy.url을 주석 처리하고 어플리케이션에서 환경변수로 받도록 구성합니다.

sqlalchemy.url = driver://user:pass@localhost/dbname

migrations/env.py 에서 다음과 같이 DATABASE_URL을 사용합니다:

import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config
fileConfig(config.config_file_name)

target_metadata = None

def get_url():
return os.getenv('DATABASE_URL')

def run_migrations_offline():
url = get_url()
context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
with context.begin_transaction():
context.run_migrations()

def run_migrations_online():
connectable = engine_from_config(
config.get_section(config.config_ini_section),
prefix='sqlalchemy.',
poolclass=pool.NullPool,
)
with connectable.connect() as connection:
context.configure(connection=connection, target_metadata=target_metadata)
with context.begin_transaction():
context.run_migrations()

if context.is_offline_mode():
run_migrations_offline()
else:
run_migrations_online()

7. 사용법

- SQL 파일 생성 후 migration 스크립트 생성: alembic revision -m 'create users' --autogenerate (자동 생성 대신 수동 코드로 SQL 실행)
- FastAPI 시작 시 자동 migration: uvicorn main:app --reload
- Docker-compose로 실행: docker-compose up -d

이제 migrations/versions 폴더에 SQL 파일을 두고, migration 파일에서 op.execute로 SQL을 실행하며 FastAPI 시작 시 자동 반영하고, Docker PostgreSQL 데이터는 volumes를 통해 유지됩니다.
